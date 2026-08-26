"""Focused liveness checks for stdio MCP child processes."""

from unittest.mock import patch

from tools.mcp_tool import MCPServerTask


def _task_with_pids(pids):
    task = object.__new__(MCPServerTask)
    task._stdio_child_pids = pids
    task._config = {"command": "example"}
    return task


def test_live_child_is_not_reported_dead():
    with patch("psutil.pid_exists", return_value=True):
        assert _task_with_pids([123])._stdio_children_dead() is False


def test_all_dead_children_are_reported_dead():
    with patch("psutil.pid_exists", return_value=False):
        assert _task_with_pids([123, 456])._stdio_children_dead() is True


def test_probe_failure_is_unknown_not_dead():
    with patch("psutil.pid_exists", side_effect=OSError("probe failed")):
        assert _task_with_pids([123])._stdio_children_dead() is False
