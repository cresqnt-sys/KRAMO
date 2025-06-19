"""
roblox_macro_restart.py — GUI tool with persistent settings, robust restart logic,
UI Automation for clicking "Join Server", and optional manual coordinate override
"""
from __future__ import annotations
import sys, time, threading, datetime as dt, json, os
from zoneinfo import ZoneInfo
import tkinter as tk
from tkinter import ttk, messagebox
import psutil, requests, pyautogui
import ast
from pywinauto import Application
# ──────────────────────────────────────────────────────────────────────
# Configuration defaults and persistence
# ──────────────────────────────────────────────────────────────────────
# Determine config file path, compatible with PyInstaller
if getattr(sys, 'frozen', False):  # running in a bundle
    # For PyInstaller, write config next to the executable
    base_dir = os.path.dirname(sys.executable)
else:
    # Running as script
    base_dir = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(base_dir, 'watchdog_config.json')
DEFAULTS = {
    'interval_min': 28,
    'webhook1': '',
    'webhook2': '',
    'ping_id': '',
    'limit_strap': False,
    'button_coord': None
}

NY_TZ        = ZoneInfo("America/New_York")
ROB_LOX_PROC = 'robloxplayerbeta.exe'
ACC_MGR_PROC = 'Roblox Account Manager.exe'
STRAP_SUFFIX = 'strap.exe'
VERIFY_DELAY = 30
MAX_RETRIES  = 3
WARNING_OFFSET = 60

# ──────────────────────────────────────────────────────────────────────
# Load/save config
# ──────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if os.path.isfile(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)
            return {**DEFAULTS, **data}
        except:
            pass
    return DEFAULTS.copy()


def save_config(cfg: dict) -> None:
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        messagebox.showerror("Save Error", f"Failed to save config: {e}")

# ──────────────────────────────────────────────────────────────────────
# Helper functions
# ──────────────────────────────────────────────────────────────────────

def count_roblox() -> int:
    return sum(1 for p in psutil.process_iter(['name']) if (n := p.info['name']) and n.lower() == ROB_LOX_PROC)


def kill_targets() -> None:
    for p in psutil.process_iter(['name']):
        name = (p.info['name'] or '').lower()
        if name == ROB_LOX_PROC or name.endswith(STRAP_SUFFIX):
            try: p.kill()
            except: pass


def limit_strap_helpers() -> None:
    helpers = [p for p in psutil.process_iter(['name','create_time']) if (n:=p.info['name']) and n.lower().endswith(STRAP_SUFFIX)]
    if len(helpers) <= 1: return
    helpers.sort(key=lambda p: p.info['create_time'])
    for p in helpers[1:]:
        try: p.kill()
        except: pass


def send_webhooks(urls: list[str], content: str) -> None:
    payload = {'content': content}
    for url in urls:
        if url:
            try: requests.post(url, json=payload, timeout=10)
            except: pass


def make_warning_message() -> str:
    ts = int(time.time()) + WARNING_OFFSET
    t_str = dt.datetime.fromtimestamp(ts, NY_TZ).strftime("%I:%M %p ET")
    return f"⚠️ The macro will restart at **{t_str}** (<t:{ts}:R>)"

# ──────────────────────────────────────────────────────────────────────
# Watchdog thread
# ──────────────────────────────────────────────────────────────────────
class Watchdog(threading.Thread):
    def __init__(self, interval_min, webhooks, ping_id, button_coord, limit_strap, status_cb):
        super().__init__(daemon=True)
        self.interval = interval_min * 60
        self.webhooks = webhooks
        self.ping_id = ping_id
        self.button_coord = button_coord
        self.limit_strap = limit_strap
        self.status_cb = status_cb
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def _click_button(self):
        try:
            app = Application(backend='uia').connect(path=ACC_MGR_PROC)
            win = app.window(title_re='.*Roblox Account Manager.*')
            btn = win.child_window(title='Join Server', control_type='Button')
            btn.wait('enabled ready', timeout=10)
            btn.invoke()
            return
        except:
            pass
        if self.button_coord:
            pyautogui.moveTo(*self.button_coord, duration=0.2)
            pyautogui.click()

    def _perform_restart(self, message: str) -> bool:
        send_webhooks(self.webhooks, message)
        kill_targets(); time.sleep(1)
        self._click_button()
        for attempt in range(1, MAX_RETRIES+1):
            time.sleep(VERIFY_DELAY)
            if count_roblox() > 0:
                if self.limit_strap: limit_strap_helpers()
                return True
            if attempt < MAX_RETRIES:
                send_webhooks(self.webhooks, f"⚠️ Restart attempt {attempt} failed — retrying…")
                kill_targets(); time.sleep(1); self._click_button()
        final = f"❌ Restart failed after {MAX_RETRIES} attempts"
        if self.ping_id: final += f" <@{self.ping_id}>"
        send_webhooks(self.webhooks, final)
        return False

    def run(self):
        self.status_cb("Running…")
        cycle_start = dt.datetime.now()
        warning_sent = False
        last_count = count_roblox()
        while not self._stop.is_set():
            time.sleep(5)
            cur = count_roblox()
            if cur == 1 and last_count > 1:
                ok = self._perform_restart("⏰ Abrupt Restart… (Game Crashed)")
                if not ok:
                    self.status_cb("Failed — stopped")
                    return
                cycle_start, warning_sent = dt.datetime.now(), False
            last_count = cur
            elapsed = (dt.datetime.now() - cycle_start).total_seconds()
            if not warning_sent and elapsed >= self.interval - WARNING_OFFSET:
                send_webhooks(self.webhooks, make_warning_message()); warning_sent = True
            if elapsed >= self.interval:
                ok = self._perform_restart("⏰ Restarting now…")
                if not ok:
                    self.status_cb("Failed — stopped")
                    return
                cycle_start, warning_sent = dt.datetime.now(), False
        self.status_cb("Stopped")

# ──────────────────────────────────────────────────────────────────────
# GUI Application
# ──────────────────────────────────────────────────────────────────────
class MacroGUI(tk.Tk):
    def __init__(self):
        super().__init__(); self.title("KRAMO 2"); self.resizable(False, False)
        cfg = load_config()
        # Variables
        self.interval_var = tk.IntVar(value=cfg['interval_min'])
        self.web1_var = tk.StringVar(value=cfg['webhook1'])
        self.web2_var = tk.StringVar(value=cfg['webhook2'])
        self.ping_var = tk.StringVar(value=cfg['ping_id'])
        self.limit_var = tk.BooleanVar(value=cfg['limit_strap'])
        self.show_coord_var = tk.BooleanVar(value=False)
        self.coord_var = tk.StringVar(value=str(cfg['button_coord']))
        self.wd: Watchdog | None = None
        frm = ttk.Frame(self, padding=10); frm.grid()
        # Interval
        ttk.Label(frm, text="Restart Interval (min):").grid(row=0, column=0, sticky='e')
        ttk.Spinbox(frm, from_=1, to=999, width=6, textvariable=self.interval_var).grid(row=0, column=1)
        # Webhooks & Ping
        ttk.Label(frm, text="Webhook #1:").grid(row=1, column=0, sticky='e')
        ttk.Entry(frm, width=50, textvariable=self.web1_var).grid(row=1, column=1, columnspan=2)
        ttk.Label(frm, text="Webhook #2:").grid(row=2, column=0, sticky='e')
        ttk.Entry(frm, width=50, textvariable=self.web2_var).grid(row=2, column=1, columnspan=2)
        ttk.Label(frm, text="Your User ID:").grid(row=3, column=0, sticky='e')
        ttk.Entry(frm, width=20, textvariable=self.ping_var).grid(row=3, column=1, sticky='w')
        # Options
        ttk.Checkbutton(frm, text="Limit -strap.exe processes to 1", variable=self.limit_var).grid(row=4, column=0, columnspan=3, sticky='w')
        ttk.Checkbutton(frm, text="Enable Manual Button Alignment", variable=self.show_coord_var, command=self._toggle_coord).grid(row=5, column=0, columnspan=3, sticky='w', pady=(4,0))
        # Manual coord widgets (initially hidden)
        self.coord_label = ttk.Label(frm, text="Button coord:")
        self.coord_value = ttk.Label(frm, textvariable=self.coord_var)
        self.coord_btn = ttk.Button(frm, text="Set Coord", command=self.pick_coord)
        # Control row
        row = ttk.Frame(frm); row.grid(row=8, column=0, columnspan=3, pady=5)
        self.start_btn = ttk.Button(row, text="Start", command=self.start)
        self.stop_btn  = ttk.Button(row, text="Stop", command=self.stop, state='disabled')
        self.start_btn.pack(side='left', padx=4); self.stop_btn.pack(side='left', padx=4)
        # Save/Load
        self.save_btn = ttk.Button(frm, text="Save Settings", command=self.save)
        self.load_btn = ttk.Button(frm, text="Load Settings", command=self.load)
        self.save_btn.grid(row=9, column=0, pady=5); self.load_btn.grid(row=9, column=1, pady=5)
        # Status
        self.status_var = tk.StringVar(value='Idle')
        ttk.Label(frm, textvariable=self.status_var, foreground='blue').grid(row=10, column=0, columnspan=3)
        self.protocol('WM_DELETE_WINDOW', self.on_close)
        # initialize coord widget visibility
        self._toggle_coord()

    def _toggle_coord(self):
        if self.show_coord_var.get():
            self.coord_label.grid(row=6, column=0, sticky='e', pady=(6,0))
            self.coord_value.grid(row=6, column=1, sticky='w', pady=(6,0))
            self.coord_btn.grid(row=6, column=2, pady=(6,0))
        else:
            self.coord_label.grid_remove()
            self.coord_value.grid_remove()
            self.coord_btn.grid_remove()

    def collect(self) -> dict | None:
        # If manual override is on, ensure a coord is set
        if self.show_coord_var.get() and self.coord_var.get() in ('None', ''):
            messagebox.showerror("Error", "Please set the button coordinate before starting.")
            return None
        w1, w2 = self.web1_var.get().strip(), self.web2_var.get().strip()
        hooks = [u for u in (w1, w2) if u]
        if not hooks:
            messagebox.showerror("Error", "Enter at least one webhook URL.")
            return None
        return {
            'interval_min': self.interval_var.get(),
            'webhook1': w1,
            'webhook2': w2,
            'ping_id': self.ping_var.get().strip(),
            'limit_strap': self.limit_var.get(),
            'button_coord': None if not self.show_coord_var.get() or self.coord_var.get() in ('None','') else ast.literal_eval(self.coord_var.get())
        }

    def start(self):
        if self.wd: return
        cfg = self.collect();
        if not cfg: return
        save_config(cfg)
        self.wd = Watchdog(
            cfg['interval_min'], [cfg['webhook1'], cfg['webhook2']], cfg['ping_id'], cfg['button_coord'], cfg['limit_strap'], self.update_status
        )
        self.wd.start(); self.start_btn['state']='disabled'; self.stop_btn['state']='normal'

    def stop(self):
        if self.wd: self.wd.stop(); self.wd=None
        self.start_btn['state']='normal'; self.stop_btn['state']='disabled'; self.update_status('Stopped')

    def pick_coord(self):
        messagebox.showinfo("Set Coord", "Hover over Join Server Button in Account Manager for 3s.")
        time.sleep(3)
        pos = pyautogui.position()
        coord = (pos.x, pos.y)
        self.coord_var.set(str(coord))

    def save(self):
        cfg = self.collect()
        if cfg: save_config(cfg); messagebox.showinfo("Saved","Settings saved.")

    def load(self):
        cfg = load_config();
        self.interval_var.set(cfg['interval_min']); self.web1_var.set(cfg['webhook1']); self.web2_var.set(cfg['webhook2'])
        self.ping_var.set(cfg['ping_id']); self.limit_var.set(cfg['limit_strap']);
        self.coord_var.set(str(cfg['button_coord'])); messagebox.showinfo("Loaded","Settings loaded.")

    def update_status(self, txt: str):
        self.status_var.set(txt)

    def on_close(self):
        self.stop(); self.destroy()

if __name__ == '__main__':
    pyautogui.FAILSAFE = True
    app = MacroGUI(); app.mainloop()
