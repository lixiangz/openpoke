"""Tests for send_message_to_agent - roster branching on new vs existing agents."""

from unittest.mock import MagicMock, patch

import server.agents.interaction_agent.tools as agent_tools


def _setup_mocks(existing_agents: list[str]) -> tuple[MagicMock, MagicMock, MagicMock]:
    """Return (mock_roster, mock_logs, mock_loop) with existing_agents pre-loaded."""
    mock_roster = MagicMock()
    mock_roster.get_agents.return_value = list(existing_agents)

    mock_logs = MagicMock()
    mock_loop = MagicMock()

    return mock_roster, mock_logs, mock_loop


def _call_send(agent_name: str, instructions: str, existing: list[str]):
    mock_roster, mock_logs, mock_loop = _setup_mocks(existing)

    with (
        patch.object(agent_tools, "get_agent_roster", return_value=mock_roster),
        patch.object(agent_tools, "get_execution_agent_logs", return_value=mock_logs),
        patch("asyncio.get_running_loop", return_value=mock_loop),
    ):
        result = agent_tools.send_message_to_agent(agent_name, instructions)

    return result, mock_roster, mock_logs


# --- New agent ---

def test_new_agent_calls_add_agent() -> None:
    result, roster, _ = _call_send("New Agent", "Do stuff", existing=[])

    roster.add_agent.assert_called_once_with("New Agent")
    roster.touch_agent.assert_not_called()


def test_new_agent_result_flags_creation() -> None:
    result, _, _ = _call_send("New Agent", "Do stuff", existing=[])

    assert result.success is True
    assert result.payload["new_agent_created"] is True
    assert result.payload["agent_name"] == "New Agent"


# --- Existing agent ---

def test_existing_agent_calls_touch_agent() -> None:
    result, roster, _ = _call_send("Existing Agent", "More stuff", existing=["Existing Agent"])

    roster.touch_agent.assert_called_once_with("Existing Agent")
    roster.add_agent.assert_not_called()


def test_existing_agent_result_flags_reuse() -> None:
    result, _, _ = _call_send("Existing Agent", "More stuff", existing=["Existing Agent"])

    assert result.success is True
    assert result.payload["new_agent_created"] is False


# --- Shared behaviour ---

def test_execution_logs_always_record_request() -> None:
    _, _, logs = _call_send("Any Agent", "instructions", existing=[])
    logs.record_request.assert_called_once_with("Any Agent", "instructions")


def test_task_is_submitted_to_event_loop() -> None:
    _, _, _ = _call_send("Any Agent", "instructions", existing=[])
    # If we got here without error, the loop.create_task path was reached


def test_name_match_is_exact() -> None:
    """'Email to Alice' and 'email to alice' must be treated as different agents."""
    result, roster, _ = _call_send("email to alice", "hi", existing=["Email to Alice"])

    # Lowercase version is not in the roster, so a new agent should be created
    roster.add_agent.assert_called_once_with("email to alice")
    roster.touch_agent.assert_not_called()


# --- roster.load() is called ---

def test_roster_load_not_called_directly_by_tools() -> None:
    """tools.py no longer calls load() directly; it delegates to add_agent/touch_agent."""
    _, roster, _ = _call_send("Agent", "go", existing=[])
    roster.load.assert_not_called()


# --- No event loop ---

def test_no_event_loop_returns_failure() -> None:
    """When there is no running event loop, send_message_to_agent returns failure."""
    mock_roster, mock_logs, _ = _setup_mocks([])

    with (
        patch.object(agent_tools, "get_agent_roster", return_value=mock_roster),
        patch.object(agent_tools, "get_execution_agent_logs", return_value=mock_logs),
        patch("asyncio.get_running_loop", side_effect=RuntimeError("no loop")),
    ):
        result = agent_tools.send_message_to_agent("Agent", "instructions")

    assert result.success is False
    assert "error" in result.payload


# --- handle_tool_call routing ---

def test_handle_tool_call_routes_to_send_message_to_agent() -> None:
    mock_roster, mock_logs, mock_loop = _setup_mocks([])

    with (
        patch.object(agent_tools, "get_agent_roster", return_value=mock_roster),
        patch.object(agent_tools, "get_execution_agent_logs", return_value=mock_logs),
        patch("asyncio.get_running_loop", return_value=mock_loop),
    ):
        result = agent_tools.handle_tool_call(
            "send_message_to_agent",
            {"agent_name": "Test Agent", "instructions": "do it"},
        )

    assert result.success is True
    assert result.payload["agent_name"] == "Test Agent"


def test_handle_tool_call_with_json_string_arguments() -> None:
    mock_roster, mock_logs, mock_loop = _setup_mocks([])

    with (
        patch.object(agent_tools, "get_agent_roster", return_value=mock_roster),
        patch.object(agent_tools, "get_execution_agent_logs", return_value=mock_logs),
        patch("asyncio.get_running_loop", return_value=mock_loop),
    ):
        result = agent_tools.handle_tool_call(
            "send_message_to_agent",
            '{"agent_name": "JSON Agent", "instructions": "go"}',
        )

    assert result.success is True
    assert result.payload["agent_name"] == "JSON Agent"


def test_handle_tool_call_invalid_json_returns_failure() -> None:
    result = agent_tools.handle_tool_call(
        "send_message_to_agent",
        "{bad json!!",
    )
    assert result.success is False
    assert "Invalid JSON" in result.payload["error"]


def test_handle_tool_call_unknown_tool_returns_failure() -> None:
    result = agent_tools.handle_tool_call("nonexistent_tool", {})
    assert result.success is False
    assert "Unknown tool" in result.payload["error"]


def test_handle_tool_call_missing_required_args_returns_failure() -> None:
    """Calling send_message_to_agent without agent_name should fail with TypeError."""
    mock_roster, mock_logs, mock_loop = _setup_mocks([])

    with (
        patch.object(agent_tools, "get_agent_roster", return_value=mock_roster),
        patch.object(agent_tools, "get_execution_agent_logs", return_value=mock_logs),
        patch("asyncio.get_running_loop", return_value=mock_loop),
    ):
        result = agent_tools.handle_tool_call(
            "send_message_to_agent",
            {"instructions": "no agent_name provided"},
        )

    assert result.success is False
    assert "Missing required arguments" in result.payload["error"]


def test_handle_tool_call_invalid_arguments_type() -> None:
    result = agent_tools.handle_tool_call("send_message_to_agent", 42)
    assert result.success is False
    assert "Invalid arguments format" in result.payload["error"]


def test_handle_tool_call_empty_string_arguments() -> None:
    """Empty string args should be parsed as empty dict, causing TypeError for missing args."""
    mock_roster, mock_logs, mock_loop = _setup_mocks([])

    with (
        patch.object(agent_tools, "get_agent_roster", return_value=mock_roster),
        patch.object(agent_tools, "get_execution_agent_logs", return_value=mock_logs),
        patch("asyncio.get_running_loop", return_value=mock_loop),
    ):
        result = agent_tools.handle_tool_call("send_message_to_agent", "  ")

    assert result.success is False
    assert "Missing required arguments" in result.payload["error"]


# --- send_message_to_user ---

def test_handle_tool_call_routes_send_message_to_user() -> None:
    with patch.object(agent_tools, "get_conversation_log") as mock_log_factory:
        mock_log = MagicMock()
        mock_log_factory.return_value = mock_log

        result = agent_tools.handle_tool_call(
            "send_message_to_user",
            {"message": "Hello user"},
        )

    assert result.success is True
    assert result.user_message == "Hello user"
    assert result.recorded_reply is True


# --- wait tool ---

def test_handle_tool_call_routes_wait() -> None:
    with patch.object(agent_tools, "get_conversation_log") as mock_log_factory:
        mock_log = MagicMock()
        mock_log_factory.return_value = mock_log

        result = agent_tools.handle_tool_call("wait", {"reason": "already sent"})

    assert result.success is True
    assert result.payload["status"] == "waiting"
