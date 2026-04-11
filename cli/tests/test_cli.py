"""Tests for the NockCC CLI — config, client, and commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from cli.config import (
    clear_active_session,
    get_active_session,
    mask_api_key,
    set_active_session,
)
from cli.nockcc import cli


class TestActiveSessionFile:
    """Active session file management (write/read/clear)."""

    def test_set_and_get_active_session(self, tmp_path: Path) -> None:
        session_file = tmp_path / "active_session"
        with patch("cli.config.ACTIVE_SESSION_PATH", session_file), patch(
            "cli.config.NOCKCC_DIR", tmp_path
        ):
            set_active_session("42")
            assert get_active_session() == "42"

    def test_clear_active_session(self, tmp_path: Path) -> None:
        session_file = tmp_path / "active_session"
        session_file.write_text("42")
        with patch("cli.config.ACTIVE_SESSION_PATH", session_file):
            clear_active_session()
            assert not session_file.exists()
            assert get_active_session() is None

    def test_get_active_session_missing_file(self, tmp_path: Path) -> None:
        session_file = tmp_path / "active_session"
        with patch("cli.config.ACTIVE_SESSION_PATH", session_file):
            assert get_active_session() is None


class TestMaskApiKey:
    def test_mask_long_key(self) -> None:
        assert mask_api_key("nockcc-kw-2026-875") == "nockcc-k****-875"

    def test_mask_short_key(self) -> None:
        assert mask_api_key("short") == "****"

    def test_mask_empty_key(self) -> None:
        assert mask_api_key("") == "****"


class TestConfigInit:
    def test_config_init_creates_file(self) -> None:
        with (
            patch("cli.nockcc.load_config", return_value={"api_url": "http://localhost:8001", "api_key": ""}),
            patch("cli.nockcc.save_config") as mock_save,
        ):
            runner = CliRunner()
            result = runner.invoke(cli, ["config", "init"], input="http://localhost:8001\ntest-key\n")
            assert result.exit_code == 0
            assert "Config saved" in result.output
            mock_save.assert_called_once()
            saved = mock_save.call_args[0][0]
            assert saved["api_url"] == "http://localhost:8001"
            assert saved["api_key"] == "test-key"


class TestSessionStart:
    def test_session_start_hits_api(self) -> None:
        mock_response = {
            "success": True,
            "message": "Session created",
            "data": {
                "id": 1,
                "agent": "claude_code",
                "agent_display": "Claude Code",
                "machine": "mac",
                "machine_display": "Mac Secondary",
                "status": "active",
                "branch": "feature/test",
            },
        }
        with (
            patch("cli.nockcc.NockCCClient") as MockClient,
            patch("cli.nockcc.set_active_session") as mock_set,
        ):
            MockClient.return_value.create_session.return_value = mock_response
            runner = CliRunner()
            result = runner.invoke(
                cli,
                ["session", "start", "--agent", "claude-code", "--branch", "feature/test"],
            )
            assert result.exit_code == 0
            assert "Session started" in result.output
            mock_set.assert_called_once_with("1")
            MockClient.return_value.create_session.assert_called_once_with(
                agent="claude_code", machine="mac", branch="feature/test", repo="", task=""
            )


class TestSessionEnd:
    def test_session_end_hits_api(self) -> None:
        mock_response = {
            "success": True,
            "message": "Session ended",
            "data": {
                "id": 1,
                "status": "completed",
                "started_at": "2026-03-14T10:00:00+00:00",
                "ended_at": "2026-03-14T12:00:00+00:00",
            },
        }
        with (
            patch("cli.nockcc.NockCCClient") as MockClient,
            patch("cli.nockcc.get_active_session", return_value="1"),
            patch("cli.nockcc.clear_active_session") as mock_clear,
        ):
            MockClient.return_value.end_session.return_value = mock_response
            runner = CliRunner()
            result = runner.invoke(cli, ["session", "end", "--notes", "Done"])
            assert result.exit_code == 0
            assert "Session ended" in result.output
            mock_clear.assert_called_once()


    def test_session_end_explicit_id_preserves_active(self) -> None:
        mock_response = {
            "success": True,
            "message": "Session ended",
            "data": {
                "id": 2,
                "status": "completed",
                "started_at": "2026-03-14T10:00:00+00:00",
                "ended_at": "2026-03-14T12:00:00+00:00",
            },
        }
        with (
            patch("cli.nockcc.NockCCClient") as MockClient,
            patch("cli.nockcc.get_active_session", return_value="1"),
            patch("cli.nockcc.clear_active_session") as mock_clear,
        ):
            MockClient.return_value.end_session.return_value = mock_response
            runner = CliRunner()
            result = runner.invoke(cli, ["session", "end", "--session-id", "2", "--notes", "Done"])
            assert result.exit_code == 0
            assert "Session ended" in result.output
            MockClient.return_value.end_session.assert_called_once_with("2", status="completed", notes="Done")
            mock_clear.assert_not_called()


class TestSessionList:
    def test_session_list_renders_table(self) -> None:
        mock_response = {
            "success": True,
            "message": "ok",
            "data": {
                "total": 2,
                "sessions": [
                    {
                        "id": 1,
                        "agent": "claude_code",
                        "agent_display": "Claude Code",
                        "machine": "mac",
                        "machine_display": "Mac Secondary",
                        "status": "active",
                        "branch": "feature/a",
                        "started_at": "2026-03-14T10:00:00+00:00",
                        "ended_at": None,
                    },
                    {
                        "id": 2,
                        "agent": "copilot",
                        "agent_display": "GitHub Copilot",
                        "machine": "windows",
                        "machine_display": "Windows Primary",
                        "status": "completed",
                        "branch": "feature/b",
                        "started_at": "2026-03-14T08:00:00+00:00",
                        "ended_at": "2026-03-14T09:30:00+00:00",
                    },
                ],
            },
        }
        with patch("cli.nockcc.NockCCClient") as MockClient:
            MockClient.return_value.list_sessions.return_value = mock_response
            runner = CliRunner()
            result = runner.invoke(cli, ["session", "list"])
            assert result.exit_code == 0
            assert "Sessions" in result.output
            assert "feature/a" in result.output
            assert "feature/b" in result.output


class TestStatusCommand:
    def test_status_renders_panel(self) -> None:
        mock_response = {
            "success": True,
            "message": "ok",
            "data": {
                "active_sessions": 2,
                "open_prs": 3,
                "failed_ci": 1,
                "merged_this_week": 5,
                "todays_spend": "Not available",
            },
        }
        with patch("cli.nockcc.NockCCClient") as MockClient:
            MockClient.return_value.dashboard_summary.return_value = mock_response
            runner = CliRunner()
            result = runner.invoke(cli, ["status"])
            assert result.exit_code == 0
            assert "NockCC Status" in result.output


class TestWrapCommand:
    def test_wrap_starts_and_ends_session(self) -> None:
        create_resp = {
            "success": True,
            "message": "Session created",
            "data": {"id": 99, "agent": "claude_code", "status": "active"},
        }
        end_resp = {
            "success": True,
            "message": "Session ended",
            "data": {"id": 99, "status": "completed"},
        }
        with (
            patch("cli.nockcc.NockCCClient") as MockClient,
            patch("cli.nockcc.set_active_session") as mock_set,
            patch("cli.nockcc.get_active_session", return_value="99"),
            patch("cli.nockcc.clear_active_session") as mock_clear,
            patch("cli.nockcc._detect_git_info", return_value=("main", "nock-command-center")),
            patch("subprocess.run") as mock_run,
        ):
            MockClient.return_value.create_session.return_value = create_resp
            MockClient.return_value.end_session.return_value = end_resp
            mock_run.return_value.returncode = 0

            runner = CliRunner()
            result = runner.invoke(cli, ["wrap", "--", "echo", "hello"])
            assert result.exit_code == 0
            assert "Session 99 started" in result.output
            assert "Session 99 ended" in result.output
            mock_set.assert_called_once_with("99")
            mock_clear.assert_called_once()
            MockClient.return_value.end_session.assert_called_once_with("99", status="completed")

    def test_wrap_detects_agent_from_command(self) -> None:
        from cli.nockcc import _detect_agent
        assert _detect_agent("claude") == "claude_code"
        assert _detect_agent("/usr/local/bin/claude") == "claude_code"
        assert _detect_agent("codex") == "codex"
        assert _detect_agent("copilot") == "copilot"
        assert _detect_agent("unknown-tool") == "other"

    def test_wrap_extracts_track_from_command_args(self) -> None:
        """When --track lands after -- (e.g. via alias), it should be extracted."""
        with (
            patch("cli.nockcc.NockCCClient"),
            patch("cli.nockcc.set_active_session"),
            patch("cli.nockcc.get_active_session", return_value="77"),
            patch("cli.nockcc.clear_active_session"),
            patch("cli.nockcc._detect_git_info", return_value=("main", "repo")),
            patch("cli.nockcc._run_tracked") as mock_tracked,
        ):
            mock_tracked.return_value = 0
            runner = CliRunner()
            # Simulates: alias cc='nockcc wrap -- claude --dangerously-skip-permissions'
            # User runs: cc --track -p "fix"
            result = runner.invoke(
                cli, ["wrap", "--", "claude", "--dangerously-skip-permissions", "--track", "-p", "fix"]
            )
            assert result.exit_code == 0
            mock_tracked.assert_called_once()
            # --track should NOT be in the command passed to _run_tracked
            call_kwargs = mock_tracked.call_args
            cmd = call_kwargs.kwargs.get("command") or call_kwargs[1].get("command")
            assert "--track" not in cmd

    def test_wrap_failed_command_ends_as_failed(self) -> None:
        create_resp = {
            "success": True,
            "message": "Session created",
            "data": {"id": 50, "agent": "claude_code", "status": "active"},
        }
        with (
            patch("cli.nockcc.NockCCClient") as MockClient,
            patch("cli.nockcc.set_active_session"),
            patch("cli.nockcc.get_active_session", return_value="50"),
            patch("cli.nockcc.clear_active_session"),
            patch("cli.nockcc._detect_git_info", return_value=("feature/x", "repo")),
            patch("subprocess.run") as mock_run,
        ):
            MockClient.return_value.create_session.return_value = create_resp
            MockClient.return_value.end_session.return_value = {"success": True, "data": {}}
            mock_run.return_value.returncode = 1

            runner = CliRunner()
            result = runner.invoke(cli, ["wrap", "--", "false"])
            assert result.exit_code == 1
            MockClient.return_value.end_session.assert_called_once_with("50", status="failed")
