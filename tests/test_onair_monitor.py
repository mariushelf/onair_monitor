"""Tests for onair_monitor.monitor."""

from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar
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
            mock.patch("shutil.which", return_value="/usr/local/bin/onair-monitor"),
        ):
            monitor.install_autostart()
        assert desktop_file.exists()
        content = desktop_file.read_text()
        assert "[Desktop Entry]" in content
        assert "Exec=/usr/local/bin/onair-monitor" in content


# ---------------------------------------------------------------------------
# Monitor loop (debounce)
# ---------------------------------------------------------------------------


class TestMonitorLoopDebounce:
    """Verify that brief camera-active blips are ignored (debounced)."""

    _BASE_CONFIG: ClassVar[dict[str, object]] = {
        "ha_url": "http://ha:8123",
        "webhook_on": "on",
        "webhook_off": "off",
        "poll_interval": 0,
        "debounce_count": 3,
    }

    def _run_loop(self, active_sequence: list[bool], config: dict | None = None):
        """Run the monitor loop for *len(active_sequence)* iterations.

        Returns (notify_calls, state_changes) where each entry is a list of
        recorded arguments.
        """
        config = config or dict(self._BASE_CONFIG)
        it = iter(active_sequence)
        call_count = 0

        state_changes: list[bool] = []

        def fake_camera(_tool):
            nonlocal call_count
            call_count += 1
            try:
                return next(it)
            except StopIteration:
                raise _Stop

        class _Stop(Exception):
            pass

        with (
            mock.patch("onair_monitor.monitor.camera_in_use", side_effect=fake_camera),
            mock.patch("onair_monitor.monitor.notify_ha") as mock_notify,
            mock.patch("onair_monitor.monitor.time.sleep"),
        ):
            try:
                monitor.monitor_loop(
                    config,
                    "fuser",
                    on_state_change=state_changes.append,
                )
            except _Stop:
                pass
        return mock_notify.call_args_list, state_changes

    def test_brief_blip_ignored(self):
        """Two consecutive active polls (< debounce_count=3) should not trigger."""
        #                    active active idle idle idle
        seq = [True, True, False, False, False]
        calls, changes = self._run_loop(seq)
        assert calls == []
        assert changes == []

    def test_sustained_active_triggers(self):
        """Three consecutive active polls should trigger the 'on' webhook."""
        seq = [True, True, True]
        calls, changes = self._run_loop(seq)
        assert len(calls) == 1
        assert calls[0] == mock.call("http://ha:8123", "on")
        assert changes == [True]

    def test_sustained_then_off(self):
        """Camera on for 3+ polls then off should trigger on then off."""
        seq = [True, True, True, True, False]
        calls, changes = self._run_loop(seq)
        assert len(calls) == 2
        assert calls[0] == mock.call("http://ha:8123", "on")
        assert calls[1] == mock.call("http://ha:8123", "off")
        assert changes == [True, False]

    def test_interrupted_active_resets_count(self):
        """A single False in the middle resets the consecutive count."""
        seq = [True, True, False, True, True, False]
        calls, _ = self._run_loop(seq)
        assert calls == []

    def test_debounce_count_1_behaves_like_no_debounce(self):
        """With debounce_count=1, any single active poll triggers."""
        config = {**self._BASE_CONFIG, "debounce_count": 1}
        seq = [True, False]
        calls, changes = self._run_loop(seq, config)
        assert len(calls) == 2
        assert changes == [True, False]


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
