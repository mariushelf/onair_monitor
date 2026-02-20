"""Tests for onair_monitor.monitor."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from onair_monitor import monitor

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class TestLoadConfig:
    def test_creates_default_config_and_exits(self, tmp_path):
        cfg = tmp_path / "config.json"
        with pytest.raises(SystemExit, match="1"):
            monitor.load_config(cfg)
        assert cfg.exists()
        data = json.loads(cfg.read_text())
        assert data == monitor.DEFAULT_CONFIG
        # File should be owner-only readable
        assert oct(cfg.stat().st_mode & 0o777) == "0o600"

    def test_loads_existing_config(self, tmp_path):
        cfg = tmp_path / "config.json"
        expected = {
            "ha_url": "http://ha:8123",
            "webhook_on": "on",
            "webhook_off": "off",
            "poll_interval": 1,
        }
        cfg.write_text(json.dumps(expected))
        result = monitor.load_config(cfg)
        assert result == expected


# ---------------------------------------------------------------------------
# Camera detection
# ---------------------------------------------------------------------------


class TestCameraInUse:
    def test_no_devices_returns_false(self):
        with mock.patch("onair_monitor.monitor.glob.glob", return_value=[]):
            assert monitor.camera_in_use("fuser") is False

    def test_fuser_returns_zero_means_in_use(self):
        with (
            mock.patch("onair_monitor.monitor.glob.glob", return_value=["/dev/video0"]),
            mock.patch(
                "onair_monitor.monitor.subprocess.run",
                return_value=mock.Mock(returncode=0),
            ),
        ):
            assert monitor.camera_in_use("fuser") is True

    def test_fuser_returns_nonzero_means_not_in_use(self):
        with (
            mock.patch("onair_monitor.monitor.glob.glob", return_value=["/dev/video0"]),
            mock.patch(
                "onair_monitor.monitor.subprocess.run",
                return_value=mock.Mock(returncode=1),
            ),
        ):
            assert monitor.camera_in_use("fuser") is False

    def test_oserror_returns_false(self):
        with (
            mock.patch("onair_monitor.monitor.glob.glob", return_value=["/dev/video0"]),
            mock.patch(
                "onair_monitor.monitor.subprocess.run",
                side_effect=OSError("no such file"),
            ),
        ):
            assert monitor.camera_in_use("fuser") is False


# ---------------------------------------------------------------------------
# HA notification
# ---------------------------------------------------------------------------


class TestNotifyHA:
    def test_successful_post(self):
        with mock.patch("onair_monitor.monitor.urllib.request.urlopen") as mock_open:
            mock_open.return_value.__enter__ = mock.Mock()
            mock_open.return_value.__exit__ = mock.Mock(return_value=False)
            monitor.notify_ha("http://ha:8123", "camera_on")
            mock_open.assert_called_once()
            req = mock_open.call_args[0][0]
            assert req.full_url == "http://ha:8123/api/webhook/camera_on"
            assert req.method == "POST"

    def test_trailing_slash_stripped(self):
        with mock.patch("onair_monitor.monitor.urllib.request.urlopen") as mock_open:
            mock_open.return_value.__enter__ = mock.Mock()
            mock_open.return_value.__exit__ = mock.Mock(return_value=False)
            monitor.notify_ha("http://ha:8123/", "camera_on")
            req = mock_open.call_args[0][0]
            assert req.full_url == "http://ha:8123/api/webhook/camera_on"

    def test_url_error_is_logged_not_raised(self):
        import urllib.error

        with mock.patch(
            "onair_monitor.monitor.urllib.request.urlopen",
            side_effect=urllib.error.URLError("fail"),
        ):
            # Should not raise
            monitor.notify_ha("http://ha:8123", "camera_on")


# ---------------------------------------------------------------------------
# Find tool
# ---------------------------------------------------------------------------


class TestFindTool:
    def test_fuser_found(self):
        with mock.patch(
            "onair_monitor.monitor.shutil.which",
            side_effect=lambda t: "/usr/bin/fuser" if t == "fuser" else None,
        ):
            assert monitor._find_tool() == "fuser"

    def test_lsof_fallback(self):
        with mock.patch(
            "onair_monitor.monitor.shutil.which",
            side_effect=lambda t: "/usr/bin/lsof" if t == "lsof" else None,
        ):
            assert monitor._find_tool() == "lsof"

    def test_nothing_found(self):
        with mock.patch("onair_monitor.monitor.shutil.which", return_value=None):
            assert monitor._find_tool() is None


# ---------------------------------------------------------------------------
# CLI parsing
# ---------------------------------------------------------------------------


class TestCLI:
    def test_headless_flag(self):
        args = monitor._build_parser().parse_args(["--headless"])
        assert args.headless is True

    def test_config_flag(self):
        args = monitor._build_parser().parse_args(["--config", "/tmp/c.json"])
        assert args.config == Path("/tmp/c.json")

    def test_version_flag(self):
        args = monitor._build_parser().parse_args(["--version"])
        assert args.version is True

    def test_install_flags(self):
        args = monitor._build_parser().parse_args(["--install-autostart"])
        assert args.install_autostart is True
        args = monitor._build_parser().parse_args(["--install-service"])
        assert args.install_service is True

    def test_uninstall_flag(self):
        args = monitor._build_parser().parse_args(["--uninstall"])
        assert args.uninstall is True

    def test_default_config_path(self):
        args = monitor._build_parser().parse_args([])
        assert args.config == monitor.CONFIG_FILE


# ---------------------------------------------------------------------------
# Install / uninstall
# ---------------------------------------------------------------------------


class TestInstallAutostart:
    def test_writes_desktop_file(self, tmp_path):
        desktop_file = tmp_path / "onair-monitor.desktop"
        with (
            mock.patch.object(monitor, "AUTOSTART_DIR", tmp_path),
            mock.patch.object(monitor, "AUTOSTART_FILE", desktop_file),
        ):
            monitor.install_autostart()
        assert desktop_file.exists()
        content = desktop_file.read_text()
        assert "[Desktop Entry]" in content
        assert "Exec=onair-monitor" in content


class TestUninstall:
    def test_removes_existing_files(self, tmp_path):
        autostart = tmp_path / "autostart" / "onair-monitor.desktop"
        autostart.parent.mkdir()
        autostart.write_text("test")

        systemd = tmp_path / "systemd" / "onair-monitor.service"
        systemd.parent.mkdir()
        systemd.write_text("test")

        config = tmp_path / "config.json"
        config.write_text("{}")

        with (
            mock.patch.object(monitor, "AUTOSTART_FILE", autostart),
            mock.patch.object(monitor, "SYSTEMD_FILE", systemd),
            mock.patch.object(monitor, "CONFIG_FILE", config),
            mock.patch("onair_monitor.monitor.subprocess.run"),
        ):
            monitor.uninstall()

        assert not autostart.exists()
        assert not systemd.exists()
        assert config.exists()  # config should be preserved
