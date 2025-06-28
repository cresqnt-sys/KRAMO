from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any

try:
    from zoneinfo import ZoneInfo
    TIMEZONE_AVAILABLE = True
except ImportError:

    TIMEZONE_AVAILABLE = False
    ZoneInfo = None

import psutil
import pyautogui
import requests
from pywinauto import Application
from PyQt6.QtCore import QThread, pyqtSignal, QTimer, QObject, QMutex, QMutexLocker
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QLineEdit, QSpinBox, QCheckBox, QPushButton,
    QMessageBox, QGroupBox, QTextEdit, QProgressBar, QStatusBar
)

class AppConstants:
    """Application constants and configuration."""

    ROBLOX_PROCESS = 'robloxplayerbeta.exe'
    ACCOUNT_MANAGER_PROCESS = 'Roblox Account Manager.exe'
    STRAP_SUFFIX = 'strap.exe'

    VERIFY_DELAY = 30
    MAX_RETRIES = 3
    WARNING_OFFSET = 60
    MONITOR_INTERVAL = 5
    COORD_CAPTURE_DELAY = 3000  

    WINDOW_WIDTH = 700
    WINDOW_HEIGHT = 500

    if TIMEZONE_AVAILABLE:
        try:
            TIMEZONE = ZoneInfo("America/New_York")
        except Exception:

            TIMEZONE = timezone(timedelta(hours=-5))
    else:

        TIMEZONE = timezone(timedelta(hours=-5))

class Status(Enum):
    """Application status enumeration."""
    IDLE = "Idle"
    RUNNING = "Running…"
    STOPPING = "Stopping…"
    STOPPED = "Stopped"
    FAILED = "Failed — stopped"
    ERROR = "Error"

@dataclass
class AppConfig:
    """Application configuration with validation."""
    interval_min: int = 28
    webhook1: str = ""
    webhook2: str = ""
    ping_id: str = ""
    limit_strap: bool = False
    button_coord: Optional[Tuple[int, int]] = None

    def __post_init__(self):
        """Validate configuration after initialization."""
        if self.interval_min < 1 or self.interval_min > 999:
            raise ValueError("Interval must be between 1 and 999 minutes")

        for webhook in [self.webhook1, self.webhook2]:
            if webhook and not self._is_valid_webhook_url(webhook):
                raise ValueError(f"Invalid webhook URL: {webhook}")

    @staticmethod
    def _is_valid_webhook_url(url: str) -> bool:
        """Validate Discord webhook URL format."""
        return (url.startswith("https://discord.com/api/webhooks/") or
                url.startswith("https://discordapp.com/api/webhooks/"))

    @property
    def webhooks(self) -> List[str]:
        """Get list of non-empty webhook URLs."""
        return [url for url in [self.webhook1, self.webhook2] if url.strip()]

    @property
    def has_valid_webhooks(self) -> bool:
        """Check if at least one valid webhook is configured."""
        return len(self.webhooks) > 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AppConfig':
        """Create instance from dictionary."""

        coord = data.get('button_coord')
        if coord and isinstance(coord, (list, tuple)) and len(coord) == 2:
            data['button_coord'] = tuple(coord)
        return cls(**data)

class ConfigManager:
    """Manages application configuration persistence."""

    def __init__(self):
        self.config_file = self._get_config_path()
        self.logger = logging.getLogger(__name__)

    def _get_config_path(self) -> Path:
        """Get configuration file path, compatible with PyInstaller."""
        if getattr(sys, 'frozen', False):

            base_dir = Path(sys.executable).parent
        else:

            base_dir = Path(__file__).parent

        return base_dir / 'kramo_config.json'

    def load_config(self) -> AppConfig:
        """Load configuration from file or return defaults."""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return AppConfig.from_dict(data)
        except Exception as e:
            self.logger.warning(f"Failed to load config: {e}")

        return AppConfig()  

    def save_config(self, config: AppConfig) -> None:
        """Save configuration to file."""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config.to_dict(), f, indent=2)
            self.logger.info(f"Configuration saved to {self.config_file}")
        except Exception as e:
            self.logger.error(f"Failed to save config: {e}")
            raise

def setup_logging() -> logging.Logger:
    """Set up application logging."""
    logger = logging.getLogger('KRAMO')
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return logger

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    log_file = Path(__file__).parent / 'kramo.log'
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger

class ProcessManager:
    """Manages Roblox and related processes."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def count_roblox_processes(self) -> int:
        """Count running Roblox processes."""
        try:
            count = 0
            for proc in psutil.process_iter(['name']):
                name = proc.info.get('name', '').lower()
                if name == AppConstants.ROBLOX_PROCESS:
                    count += 1
            return count
        except Exception as e:
            self.logger.error(f"Error counting Roblox processes: {e}")
            return 0

    def kill_target_processes(self) -> bool:
        """Kill Roblox and strap processes."""
        killed_count = 0
        try:
            for proc in psutil.process_iter(['name', 'pid']):
                name = proc.info.get('name', '').lower()
                if (name == AppConstants.ROBLOX_PROCESS or
                    name.endswith(AppConstants.STRAP_SUFFIX)):
                    try:
                        proc.kill()
                        killed_count += 1
                        self.logger.info(f"Killed process: {name} (PID: {proc.info['pid']})")
                    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                        self.logger.warning(f"Failed to kill process {name}: {e}")

            self.logger.info(f"Killed {killed_count} target processes")
            return True
        except Exception as e:
            self.logger.error(f"Error killing target processes: {e}")
            return False

    def limit_strap_processes(self) -> bool:
        """Limit strap helper processes to 1."""
        try:
            helpers = []
            for proc in psutil.process_iter(['name', 'create_time', 'pid']):
                name = proc.info.get('name', '').lower()
                if name.endswith(AppConstants.STRAP_SUFFIX):
                    helpers.append(proc)

            if len(helpers) <= 1:
                return True

            helpers.sort(key=lambda p: p.info['create_time'])
            killed_count = 0

            for proc in helpers[1:]:  
                try:
                    proc.kill()
                    killed_count += 1
                    self.logger.info(f"Killed excess strap process (PID: {proc.info['pid']})")
                except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                    self.logger.warning(f"Failed to kill strap process: {e}")

            self.logger.info(f"Limited strap processes: killed {killed_count} excess processes")
            return True
        except Exception as e:
            self.logger.error(f"Error limiting strap processes: {e}")
            return False

class WebhookManager:
    """Manages Discord webhook notifications."""

    def __init__(self, webhook_urls: List[str]):
        self.webhook_urls = [url for url in webhook_urls if url.strip()]
        self.logger = logging.getLogger(__name__)

    def send_notification(self, content: str) -> bool:
        """Send notification to all configured webhooks."""
        if not self.webhook_urls:
            self.logger.warning("No webhook URLs configured")
            return False

        payload = {'content': content}
        success_count = 0

        for url in self.webhook_urls:
            try:
                response = requests.post(url, json=payload, timeout=10)
                response.raise_for_status()
                success_count += 1
                self.logger.debug(f"Webhook notification sent successfully to {url[:50]}...")
            except requests.RequestException as e:
                self.logger.error(f"Failed to send webhook notification: {e}")

        self.logger.info(f"Sent notification to {success_count}/{len(self.webhook_urls)} webhooks")
        return success_count > 0

    def create_warning_message(self) -> str:
        """Create warning message for upcoming restart."""
        timestamp = int(time.time()) + AppConstants.WARNING_OFFSET
        restart_time = datetime.fromtimestamp(timestamp, AppConstants.TIMEZONE)
        time_str = restart_time.strftime("%I:%M %p ET")
        return f"⚠️ The macro will restart at **{time_str}** (<t:{timestamp}:R>)"

class UIAutomation:
    """Handles UI automation for clicking the Join Server button."""

    def __init__(self, manual_coord: Optional[Tuple[int, int]] = None):
        self.manual_coord = manual_coord
        self.logger = logging.getLogger(__name__)

    def click_join_server_button(self) -> bool:
        """Attempt to click the Join Server button using UI automation or manual coordinates."""

        if self._click_via_ui_automation():
            return True

        if self.manual_coord and self._click_via_coordinates():
            return True

        self.logger.error("Failed to click Join Server button via all methods")
        return False

    def _click_via_ui_automation(self) -> bool:
        """Try to click using pywinauto UI automation."""
        try:
            app = Application(backend='uia').connect(path=AppConstants.ACCOUNT_MANAGER_PROCESS)
            window = app.window(title_re='.*Roblox Account Manager.*')
            button = window.child_window(title='Join Server', control_type='Button')
            button.wait('enabled ready', timeout=10)
            button.invoke()
            self.logger.info("Successfully clicked Join Server button via UI automation")
            return True
        except Exception as e:
            self.logger.warning(f"UI automation failed: {e}")
            return False

    def _click_via_coordinates(self) -> bool:
        """Click using manual coordinates."""
        try:
            if not self.manual_coord:
                return False

            pyautogui.moveTo(*self.manual_coord, duration=0.2)
            pyautogui.click()
            self.logger.info(f"Clicked Join Server button at coordinates {self.manual_coord}")
            return True
        except Exception as e:
            self.logger.error(f"Coordinate-based clicking failed: {e}")
            return False

class WatchdogWorker(QThread):
    """Main watchdog thread for monitoring and restarting Roblox processes."""

    status_changed = pyqtSignal(str)
    progress_updated = pyqtSignal(int)  

    def __init__(self, config: AppConfig):
        super().__init__()
        self.config = config
        self.logger = logging.getLogger(__name__)
        self._stop_requested = False
        self._mutex = QMutex()

        self.process_manager = ProcessManager()
        self.webhook_manager = WebhookManager(config.webhooks)
        self.ui_automation = UIAutomation(config.button_coord)

    def stop(self):
        """Request the watchdog to stop."""
        with QMutexLocker(self._mutex):
            self._stop_requested = True
        self.logger.info("Stop requested for watchdog")

    def _is_stop_requested(self) -> bool:
        """Check if stop has been requested (thread-safe)."""
        with QMutexLocker(self._mutex):
            return self._stop_requested

    def _perform_restart(self, reason: str) -> bool:
        """Perform a complete restart sequence."""
        self.logger.info(f"Starting restart sequence: {reason}")

        self.webhook_manager.send_notification(reason)

        if not self.process_manager.kill_target_processes():
            self.logger.error("Failed to kill target processes")

        time.sleep(1)  

        for attempt in range(1, AppConstants.MAX_RETRIES + 1):
            self.logger.info(f"Restart attempt {attempt}/{AppConstants.MAX_RETRIES}")

            if not self.ui_automation.click_join_server_button():
                self.logger.warning(f"Failed to click Join Server button on attempt {attempt}")

            time.sleep(AppConstants.VERIFY_DELAY)

            roblox_count = self.process_manager.count_roblox_processes()
            if roblox_count > 0:
                self.logger.info(f"Restart successful: {roblox_count} Roblox processes running")

                if self.config.limit_strap:
                    self.process_manager.limit_strap_processes()

                return True

            if attempt < AppConstants.MAX_RETRIES:
                retry_msg = f"⚠️ Restart attempt {attempt} failed — retrying…"
                self.webhook_manager.send_notification(retry_msg)
                self.process_manager.kill_target_processes()
                time.sleep(1)

        failure_msg = f"❌ Restart failed after {AppConstants.MAX_RETRIES} attempts"
        if self.config.ping_id:
            failure_msg += f" <@{self.config.ping_id}>"

        self.webhook_manager.send_notification(failure_msg)
        self.logger.error("All restart attempts failed")
        return False

    def run(self):
        """Main watchdog loop."""
        self.logger.info("Watchdog started")
        self.status_changed.emit(Status.RUNNING.value)

        cycle_start = datetime.now()
        warning_sent = False
        last_roblox_count = self.process_manager.count_roblox_processes()

        while not self._is_stop_requested():
            time.sleep(AppConstants.MONITOR_INTERVAL)

            if self._is_stop_requested():
                break

            current_count = self.process_manager.count_roblox_processes()

            if current_count == 1 and last_roblox_count > 1:
                self.logger.warning("Detected Roblox crash")
                if not self._perform_restart("⏰ Abrupt Restart… (Game Crashed)"):
                    self.status_changed.emit(Status.FAILED.value)
                    return

                cycle_start = datetime.now()
                warning_sent = False

            last_roblox_count = current_count

            elapsed = (datetime.now() - cycle_start).total_seconds()
            interval_seconds = self.config.interval_min * 60

            progress = min(100, int((elapsed / interval_seconds) * 100))
            self.progress_updated.emit(progress)

            if not warning_sent and elapsed >= interval_seconds - AppConstants.WARNING_OFFSET:
                warning_msg = self.webhook_manager.create_warning_message()
                self.webhook_manager.send_notification(warning_msg)
                warning_sent = True
                self.logger.info("Warning notification sent")

            if elapsed >= interval_seconds:
                self.logger.info("Performing scheduled restart")
                if not self._perform_restart("⏰ Restarting now…"):
                    self.status_changed.emit(Status.FAILED.value)
                    return

                cycle_start = datetime.now()
                warning_sent = False

        self.logger.info("Watchdog stopped")
        self.status_changed.emit(Status.STOPPED.value)

class KramoMainWindow(QMainWindow):
    """Main application window with improved UI and error handling."""

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)

        self.config_manager = ConfigManager()
        self.config = self.config_manager.load_config()

        self.watchdog: Optional[WatchdogWorker] = None
        self.show_manual_coord = False

        self._setup_window()
        self._setup_ui()
        self._load_config_to_ui()

        self.logger.info("KRAMO application initialized")

    def _setup_window(self):
        """Configure main window properties."""
        self.setWindowTitle("KRAMO")
        self.setFixedSize(AppConstants.WINDOW_WIDTH, AppConstants.WINDOW_HEIGHT)

        icon_path = Path(__file__).parent / 'kramo.ico'
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    def _setup_ui(self):
        """Set up the user interface."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        settings_group = QGroupBox("Configuration")
        settings_layout = QGridLayout(settings_group)

        settings_layout.addWidget(QLabel("Restart Interval (minutes):"), 0, 0)
        self.interval_spinbox = QSpinBox()
        self.interval_spinbox.setRange(1, 999)
        self.interval_spinbox.setToolTip("Time between automatic restarts")
        settings_layout.addWidget(self.interval_spinbox, 0, 1)

        settings_layout.addWidget(QLabel("Discord Webhook #1:"), 1, 0)
        self.webhook1_edit = QLineEdit()
        self.webhook1_edit.setPlaceholderText("https://discord.com/api/webhooks/...")
        self.webhook1_edit.setMinimumWidth(400)
        self.webhook1_edit.textChanged.connect(self._validate_webhook)
        settings_layout.addWidget(self.webhook1_edit, 1, 1, 1, 2)

        settings_layout.addWidget(QLabel("Discord Webhook #2:"), 2, 0)
        self.webhook2_edit = QLineEdit()
        self.webhook2_edit.setPlaceholderText("https://discord.com/api/webhooks/... (optional)")
        self.webhook2_edit.textChanged.connect(self._validate_webhook)
        settings_layout.addWidget(self.webhook2_edit, 2, 1, 1, 2)

        settings_layout.addWidget(QLabel("Discord User ID:"), 3, 0)
        self.ping_id_edit = QLineEdit()
        self.ping_id_edit.setPlaceholderText("Your Discord user ID (for pings)")
        self.ping_id_edit.setMaximumWidth(200)
        settings_layout.addWidget(self.ping_id_edit, 3, 1)

        main_layout.addWidget(settings_group)

        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout(options_group)

        self.limit_strap_checkbox = QCheckBox("Limit -strap.exe processes to 1")
        self.limit_strap_checkbox.setToolTip("Automatically kill excess strap helper processes")
        options_layout.addWidget(self.limit_strap_checkbox)

        self.manual_coord_checkbox = QCheckBox("Enable Manual Button Coordinates")
        self.manual_coord_checkbox.setToolTip("Use manual coordinates if UI automation fails")
        self.manual_coord_checkbox.toggled.connect(self._toggle_manual_coord)
        options_layout.addWidget(self.manual_coord_checkbox)

        coord_layout = QHBoxLayout()
        self.coord_label = QLabel("Button coordinates:")
        self.coord_value_label = QLabel("Not set")
        self.coord_btn = QPushButton("Capture Coordinates")
        self.coord_btn.clicked.connect(self._capture_coordinates)

        coord_layout.addWidget(self.coord_label)
        coord_layout.addWidget(self.coord_value_label)
        coord_layout.addWidget(self.coord_btn)
        coord_layout.addStretch()

        self.coord_widget = QWidget()
        self.coord_widget.setLayout(coord_layout)
        options_layout.addWidget(self.coord_widget)

        main_layout.addWidget(options_group)

        status_group = QGroupBox("Status")
        status_layout = QVBoxLayout(status_group)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: blue; font-weight: bold;")
        status_layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        status_layout.addWidget(self.progress_bar)

        self.log_display = QTextEdit()
        self.log_display.setMaximumHeight(100)
        self.log_display.setReadOnly(True)
        status_layout.addWidget(self.log_display)

        main_layout.addWidget(status_group)

        control_layout = QHBoxLayout()

        self.start_btn = QPushButton("Start Monitoring")
        self.start_btn.clicked.connect(self._start_monitoring)
        self.start_btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-weight: bold; }")

        self.stop_btn = QPushButton("Stop Monitoring")
        self.stop_btn.clicked.connect(self._stop_monitoring)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("QPushButton { background-color: #f44336; color: white; font-weight: bold; }")

        control_layout.addWidget(self.start_btn)
        control_layout.addWidget(self.stop_btn)
        control_layout.addStretch()

        self.save_btn = QPushButton("Save Settings")
        self.save_btn.clicked.connect(self._save_settings)
        self.load_btn = QPushButton("Load Settings")
        self.load_btn.clicked.connect(self._load_settings)

        control_layout.addWidget(self.save_btn)
        control_layout.addWidget(self.load_btn)

        main_layout.addLayout(control_layout)

        self._toggle_manual_coord()

    def _load_config_to_ui(self):
        """Load configuration values into UI elements."""
        self.interval_spinbox.setValue(self.config.interval_min)
        self.webhook1_edit.setText(self.config.webhook1)
        self.webhook2_edit.setText(self.config.webhook2)
        self.ping_id_edit.setText(self.config.ping_id)
        self.limit_strap_checkbox.setChecked(self.config.limit_strap)

        if self.config.button_coord:
            self.manual_coord_checkbox.setChecked(True)
            self.coord_value_label.setText(str(self.config.button_coord))
        else:
            self.manual_coord_checkbox.setChecked(False)
            self.coord_value_label.setText("Not set")

    def _toggle_manual_coord(self):
        """Toggle visibility of manual coordinate controls."""
        is_enabled = self.manual_coord_checkbox.isChecked()
        self.coord_widget.setVisible(is_enabled)
        self.show_manual_coord = is_enabled

    def _validate_webhook(self):
        """Validate webhook URL format and provide visual feedback."""
        sender = self.sender()
        url = sender.text().strip()

        if url and not AppConfig._is_valid_webhook_url(url):
            sender.setStyleSheet("QLineEdit { border: 2px solid red; }")
            sender.setToolTip("Invalid Discord webhook URL format")
        else:
            sender.setStyleSheet("")
            sender.setToolTip("")

    def _collect_config(self) -> Optional[AppConfig]:
        """Collect configuration from UI elements with validation."""
        try:

            button_coord = None
            if self.manual_coord_checkbox.isChecked():
                coord_text = self.coord_value_label.text()
                if coord_text == "Not set":
                    QMessageBox.critical(
                        self, "Configuration Error",
                        "Please capture button coordinates before starting."
                    )
                    return None
                button_coord = self.config.button_coord

            config = AppConfig(
                interval_min=self.interval_spinbox.value(),
                webhook1=self.webhook1_edit.text().strip(),
                webhook2=self.webhook2_edit.text().strip(),
                ping_id=self.ping_id_edit.text().strip(),
                limit_strap=self.limit_strap_checkbox.isChecked(),
                button_coord=button_coord
            )

            if not config.has_valid_webhooks:
                QMessageBox.critical(
                    self, "Configuration Error",
                    "Please enter at least one valid Discord webhook URL."
                )
                return None

            return config

        except ValueError as e:
            QMessageBox.critical(self, "Configuration Error", str(e))
            return None

    def _start_monitoring(self):
        """Start the watchdog monitoring."""
        if self.watchdog and self.watchdog.isRunning():
            return

        config = self._collect_config()
        if not config:
            return

        try:
            self.config = config
            self.config_manager.save_config(config)
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save configuration: {e}")
            return

        self.watchdog = WatchdogWorker(config)
        self.watchdog.status_changed.connect(self._update_status)
        self.watchdog.progress_updated.connect(self._update_progress)
        self.watchdog.start()

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)

        self.logger.info("Monitoring started")
        self._log_message("Monitoring started")

    def _stop_monitoring(self):
        """Stop the watchdog monitoring."""
        if self.watchdog:
            self.status_label.setText("Stopping...")
            self.watchdog.stop()
            self.watchdog.wait(5000)  
            self.watchdog = None

        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.progress_bar.setValue(0)

        self.logger.info("Monitoring stopped")
        self._log_message("Monitoring stopped")
        self._update_status(Status.STOPPED.value)

    def _capture_coordinates(self):
        """Capture mouse coordinates for manual button clicking."""
        QMessageBox.information(
            self, "Coordinate Capture",
            f"Position your mouse over the 'Join Server' button and wait {AppConstants.COORD_CAPTURE_DELAY // 1000} seconds..."
        )

        QTimer.singleShot(AppConstants.COORD_CAPTURE_DELAY, self._do_capture_coordinates)

    def _do_capture_coordinates(self):
        """Actually capture the coordinates."""
        try:
            pos = pyautogui.position()
            coord = (pos.x, pos.y)
            self.config.button_coord = coord
            self.coord_value_label.setText(str(coord))
            self.logger.info(f"Captured coordinates: {coord}")
            self._log_message(f"Captured coordinates: {coord}")
        except Exception as e:
            self.logger.error(f"Failed to capture coordinates: {e}")
            QMessageBox.critical(self, "Capture Error", f"Failed to capture coordinates: {e}")

    def _save_settings(self):
        """Save current settings to file."""
        config = self._collect_config()
        if config:
            try:
                self.config = config
                self.config_manager.save_config(config)
                QMessageBox.information(self, "Settings Saved", "Configuration saved successfully.")
                self.logger.info("Settings saved")
            except Exception as e:
                QMessageBox.critical(self, "Save Error", f"Failed to save settings: {e}")

    def _load_settings(self):
        """Load settings from file."""
        try:
            self.config = self.config_manager.load_config()
            self._load_config_to_ui()
            QMessageBox.information(self, "Settings Loaded", "Configuration loaded successfully.")
            self.logger.info("Settings loaded")
        except Exception as e:
            QMessageBox.critical(self, "Load Error", f"Failed to load settings: {e}")

    def _update_status(self, status: str):
        """Update status label."""
        self.status_label.setText(status)
        self.status_bar.showMessage(status)

    def _update_progress(self, progress: int):
        """Update progress bar."""
        self.progress_bar.setValue(progress)

    def _log_message(self, message: str):
        """Add message to log display."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_display.append(f"[{timestamp}] {message}")

        if self.log_display.document().blockCount() > 100:
            cursor = self.log_display.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            cursor.select(cursor.SelectionType.BlockUnderCursor)
            cursor.removeSelectedText()

    def closeEvent(self, event):
        """Handle application close event."""
        if self.watchdog and self.watchdog.isRunning():
            reply = QMessageBox.question(
                self, "Confirm Exit",
                "Monitoring is still running. Are you sure you want to exit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return

            self._stop_monitoring()

        self.logger.info("Application closing")
        event.accept()

def main():
    """Main application entry point."""

    pyautogui.FAILSAFE = True

    logger = setup_logging()
    logger.info("Starting KRAMO 2 application")

    app = QApplication(sys.argv)
    app.setApplicationName("KRAMO 2")
    app.setApplicationVersion("2.0")
    app.setOrganizationName("KRAMO")

    try:

        window = KramoMainWindow()
        window.show()

        logger.info("Application window displayed")

        exit_code = app.exec()
        logger.info(f"Application exited with code: {exit_code}")
        return exit_code

    except Exception as e:
        logger.critical(f"Critical error in main application: {e}", exc_info=True)
        QMessageBox.critical(None, "Critical Error", f"A critical error occurred:\n{e}")
        return 1

if __name__ == '__main__':
    sys.exit(main())