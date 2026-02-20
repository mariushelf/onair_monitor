"""On-Air Monitor — detect camera usage and notify Home Assistant."""

from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import shutil
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

try:
    from importlib.resources import files as _resource_files
except ImportError:  # Python 3.8
    from importlib_resources import files as _resource_files  # type: ignore[no-redef]

import pystray
from PIL import Image, ImageDraw

logger = logging.getLogger("onair_monitor")

CONFIG_DIR = Path.home() / ".config" / "onair-monitor"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "ha_url": "http://homeassistant.local:8123",
    "webhook_on": "camera_on",
    "webhook_off": "camera_off",
    "poll_interval": 2,
}

AUTOSTART_DIR = Path.home() / ".config" / "autostart"
AUTOSTART_FILE = AUTOSTART_DIR / "onair-monitor.desktop"

SYSTEMD_DIR = Path.home() / ".config" / "systemd" / "user"
SYSTEMD_FILE = SYSTEMD_DIR / "onair-monitor.service"

SYSTEMD_UNIT = textwrap.dedent("""\
    [Unit]
    Description=On-Air Camera Monitor
    After=graphical-session.target

    [Service]
    ExecStart=%h/.local/bin/onair-monitor --headless
    Restart=on-failure
    RestartSec=5

    [Install]
    WantedBy=graphical-session.target
""")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def load_config(config_path: Path) -> dict:
    """Load config from *config_path*, creating a default if it doesn't exist."""
    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(DEFAULT_CONFIG, indent=2) + "\n")
        os.chmod(config_path, 0o600)
        print(
            f"Created default config at {config_path}\n"
            "Please edit it to set your Home Assistant URL and webhook IDs, "
            "then run onair-monitor again."
        )
        sys.exit(1)
    with open(config_path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Camera detection
# ---------------------------------------------------------------------------


def _find_tool() -> str | None:
    """Return 'fuser' or 'lsof', whichever is available."""
    for tool in ("fuser", "lsof"):
        if shutil.which(tool):
            return tool
    return None


def camera_in_use(tool: str) -> bool:
    """Return True if any /dev/video* device is in use."""
    devices = glob.glob("/dev/video*")
    if not devices:
        return False
    try:
        result = subprocess.run(  # noqa: S603
            [tool, *devices],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return result.returncode == 0
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Home Assistant notification
# ---------------------------------------------------------------------------


def notify_ha(ha_url: str, webhook_id: str) -> None:
    """POST to a Home Assistant webhook endpoint."""
    url = f"{ha_url.rstrip('/')}/api/webhook/{webhook_id}"
    req = urllib.request.Request(url, method="POST", data=b"")  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=5):  # noqa: S310
            logger.info("Notified HA: %s", webhook_id)
    except (urllib.error.URLError, OSError) as exc:
        logger.error("Failed to notify HA (%s): %s", webhook_id, exc)


# ---------------------------------------------------------------------------
# Tray icon
# ---------------------------------------------------------------------------


def _make_icon_image(active: bool) -> "Image.Image":
    """Create a 64x64 circle icon — red if active, gray if idle."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    color = (220, 40, 40, 255) if active else (140, 140, 140, 255)
    draw.ellipse([4, 4, 60, 60], fill=color)
    return img


# ---------------------------------------------------------------------------
# Install / uninstall helpers
# ---------------------------------------------------------------------------


def _desktop_file_content() -> str:
    """Return the .desktop file content from bundled resources."""
    ref = _resource_files("onair_monitor") / "resources" / "onair-monitor.desktop"
    return ref.read_text(encoding="utf-8")


def install_autostart() -> None:
    """Copy the .desktop file to ~/.config/autostart/."""
    AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
    AUTOSTART_FILE.write_text(_desktop_file_content())
    print(f"Installed autostart entry: {AUTOSTART_FILE}")


def install_service() -> None:
    """Write and enable a systemd user service."""
    SYSTEMD_DIR.mkdir(parents=True, exist_ok=True)
    SYSTEMD_FILE.write_text(SYSTEMD_UNIT)
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)  # noqa: S607
    subprocess.run(
        ["systemctl", "--user", "enable", "onair-monitor.service"],  # noqa: S607
        check=False,
    )
    print(f"Installed systemd user service: {SYSTEMD_FILE}")
    print("Start it with: systemctl --user start onair-monitor.service")


def uninstall() -> None:
    """Remove autostart and systemd service files."""
    removed = []
    if AUTOSTART_FILE.exists():
        AUTOSTART_FILE.unlink()
        removed.append(str(AUTOSTART_FILE))

    subprocess.run(
        ["systemctl", "--user", "disable", "--now", "onair-monitor.service"],  # noqa: S607
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if SYSTEMD_FILE.exists():
        SYSTEMD_FILE.unlink()
        removed.append(str(SYSTEMD_FILE))

    subprocess.run(
        ["systemctl", "--user", "daemon-reload"],  # noqa: S607
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if removed:
        print("Removed:\n  " + "\n  ".join(removed))
    else:
        print("Nothing to remove.")

    if CONFIG_FILE.exists():
        print(f"\nConfig file kept at {CONFIG_FILE} — remove it manually if desired.")


# ---------------------------------------------------------------------------
# Monitor loop
# ---------------------------------------------------------------------------


def monitor_loop(
    config: dict,
    tool: str,
    *,
    on_state_change: Callable[[bool], None] | None = None,
) -> None:
    """Poll cameras and notify HA on state transitions.

    *on_state_change* is an optional callback ``(active: bool) -> None``
    used by the tray icon to update its appearance.
    """
    was_active = False
    poll_interval = config.get("poll_interval", 2)

    while True:
        active = camera_in_use(tool)
        if active != was_active:
            webhook = config["webhook_on"] if active else config["webhook_off"]
            notify_ha(config["ha_url"], webhook)
            was_active = active
            if callable(on_state_change):
                on_state_change(active)
        time.sleep(poll_interval)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="onair-monitor",
        description="Detect camera usage and notify Home Assistant.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run without tray icon (for systemd / headless use).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=CONFIG_FILE,
        help=f"Path to config file (default: {CONFIG_FILE}).",
    )
    parser.add_argument(
        "--install-autostart",
        action="store_true",
        help="Install XDG autostart entry and exit.",
    )
    parser.add_argument(
        "--install-service",
        action="store_true",
        help="Install and enable systemd user service and exit.",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove autostart and systemd service entries and exit.",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print version and exit.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """Entry point."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.version:
        from onair_monitor import __version__

        print(f"onair-monitor {__version__}")
        return

    if args.install_autostart:
        install_autostart()
        return

    if args.install_service:
        install_service()
        return

    if args.uninstall:
        uninstall()
        return

    # --- Normal run ---
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    config = load_config(args.config)

    tool = _find_tool()
    if tool is None:
        print(
            "Error: neither 'fuser' nor 'lsof' found. "
            "Install psmisc (fuser) or lsof and try again.",
            file=sys.stderr,
        )
        sys.exit(1)

    headless = args.headless

    if headless:
        logger.info("Starting in headless mode (tool=%s)", tool)
        try:
            monitor_loop(config, tool)
        except KeyboardInterrupt:
            pass
    else:
        # Tray mode — icon on main thread, monitor on daemon thread
        import threading

        icon = pystray.Icon("onair-monitor")
        icon.icon = _make_icon_image(active=False)
        icon.title = "On-Air Monitor"
        icon.menu = pystray.Menu(
            pystray.MenuItem("On-Air Monitor", None, enabled=False),
            pystray.MenuItem("Quit", lambda: icon.stop()),
        )

        def _on_state_change(active: bool) -> None:
            icon.icon = _make_icon_image(active)
            icon.title = "ON AIR" if active else "On-Air Monitor"

        def _run_monitor() -> None:
            try:
                monitor_loop(config, tool, on_state_change=_on_state_change)
            except Exception:
                logger.exception("Monitor loop crashed")
                icon.stop()

        t = threading.Thread(target=_run_monitor, daemon=True)
        t.start()
        logger.info("Starting with tray icon (tool=%s)", tool)
        icon.run()


if __name__ == "__main__":
    main()
