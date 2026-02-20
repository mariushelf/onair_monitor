# onair-monitor

A tiny Linux daemon that detects camera usage and notifies
[Home Assistant](https://www.home-assistant.io/) via webhooks.
Optionally shows a system-tray icon that turns red when a camera is active.

## Install

```bash
uv tool install onair-monitor
```

### Tray icon support

To enable the system-tray icon, install the `tray` extra and the required
system libraries:

**1. System libraries (needed to build PyGObject):**

Debian / Ubuntu:

```bash
sudo apt install libgirepository-2.0-dev libcairo2-dev
```

Fedora:

```bash
sudo dnf install gobject-introspection-devel cairo-devel
```

Arch Linux:

```bash
sudo pacman -S gobject-introspection cairo
```

**2. Install with the tray extra:**

```bash
uv tool install onair-monitor --with tray
```

> **GNOME users:** the tray icon requires the
> [AppIndicator](https://extensions.gnome.org/extension/615/appindicator-support/)
> extension.

## Configure

On first run, a default config is created at
`~/.config/onair-monitor/config.json`. Edit it to point at your
Home Assistant instance:

```json
{
  "ha_url": "http://homeassistant.local:8123",
  "webhook_on": "camera_on",
  "webhook_off": "camera_off",
  "poll_interval": 2
}
```

The monitor POSTs to `{ha_url}/api/webhook/{webhook_on|off}`.

### Setting up webhooks in Home Assistant

1. Go to **Settings > Automations & Scenes > Create Automation**.
2. Add a **Webhook** trigger and note the webhook ID.
3. Create one automation for `camera_on` and one for `camera_off`.
4. Use the webhook IDs in your config file.

## Run

```bash
# run directly (tray icon if available, otherwise headless)
onair-monitor

# force headless mode
onair-monitor --headless
```

### Autostart (desktop session)

```bash
onair-monitor --install-autostart
```

### Systemd user service

```bash
onair-monitor --install-service
systemctl --user start onair-monitor.service
```

## Uninstall

```bash
onair-monitor --uninstall
uv tool uninstall onair-monitor
```

The config file at `~/.config/onair-monitor/config.json` is kept — remove
it manually if you no longer need it.

## License

MIT
