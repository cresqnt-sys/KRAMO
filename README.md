# KRAMO

**K**eep **R**oblox **A**ccounts **M**anaged & **O**rganized



## 🚀 Features

- **Bypasses Roblox's Multi Instance Limit**: Automatically restarts Roblox processes to bypass the multi-instance limit

## 📋 Requirements

- **Operating System**: Windows (required for Roblox and Account Manager integration)
- **Python**: 3.8 or higher
- **Roblox Account Manager**: Must be installed and configured
- **Dependencies**: See `requirements.txt` for Python package requirements

## 🛠️ Installation

1. **Clone or download this repository**
   ```bash
   git clone <repository-url>
   cd KRAMO-1
   ```

2. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Ensure Roblox Account Manager is installed** and accessible on your system

## 🎯 Usage

### Quick Start

1. **Launch Roblox Account Manager** first and configure your accounts
2. **Run KRAMO 2**:
   ```bash
   python KRAMO2.pyw
   ```
3. **Configure settings** in the GUI:
   - Set restart interval (in minutes)
   - Configure Discord webhook URL (optional)
   - Set ping ID for notifications (optional)
   - Enable/disable strap process limiting
   - Configure button coordinates if needed

4. **Start monitoring** by clicking the "Start" button


## ⚙️ Configuration

### Main Settings

- **Restart Interval**: Time between automatic restarts (in minutes)
- **Discord Webhook URL**: Optional webhook for notifications
- **Ping ID**: Discord user ID to ping on failures
- **Limit Strap**: Enable/disable strap process limiting
- **Button Coordinates**: Manual coordinates for join button (if auto-detection fails)

### Configuration File

Settings are automatically saved to `kramo_config.json` in the application directory.

## 🔧 Troubleshooting

### Common Issues

1. **Button clicking not working**
   - Ensure Roblox Account Manager is visible (not minimized)
   - Try using manual coordinate setting if auto-detection fails
   - Check that the "Join Server" button is visible and enabled

2. **Process detection issues**
   - Verify Roblox processes are running
   - Check Windows permissions for process monitoring
   - Review logs in `kramo.log` for detailed error information

3. **Discord notifications not working**
   - Verify webhook URL is correct and active
   - Check internet connection
   - Ensure Discord server permissions allow webhook messages

### Logs

Check `kramo.log` in the application directory for detailed logging information and error messages.

## 📄 License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit issues, feature requests, or pull requests.

## ⚠️ Disclaimer

This tool is designed for legitimate account management purposes. Users are responsible for ensuring compliance with Roblox's Terms of Service and any applicable regulations. The developers are not responsible for any misuse of this software.
