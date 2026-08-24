"""Channel administration coverage salvaged from upstream Discord PRs."""

import json
from unittest.mock import patch

from tools.discord_tool import (
    _ADMIN_ACTIONS,
    _available_actions,
    _request_destructive_approval,
    _reset_capability_cache,
    discord_admin_handler,
    get_dynamic_schema_admin,
)


def _config(actions="", guilds=("111",)):
    return {
        "discord": {
            "admin_guild_ids": list(guilds),
            "server_actions": actions,
        }
    }


class TestChannelCrud:
    @patch("tools.discord_tool._discord_request")
    def test_create_text_channel(self, request, monkeypatch):
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")
        monkeypatch.setattr("hermes_cli.config.load_config", lambda: _config())
        request.return_value = {
            "id": "900",
            "name": "agent-lab",
            "type": 0,
            "guild_id": "111",
            "topic": "Hermes experiments",
            "parent_id": "10",
            "position": 3,
        }

        result = json.loads(discord_admin_handler(
            action="create_channel",
            guild_id="111",
            name="agent-lab",
            channel_type="text",
            parent_id="10",
            topic="Hermes experiments",
            position=3,
        ))

        assert result["success"] is True
        assert result["channel"]["id"] == "900"
        request.assert_called_once_with(
            "POST",
            "/guilds/111/channels",
            "test-token",
            body={
                "name": "agent-lab",
                "type": 0,
                "parent_id": "10",
                "topic": "Hermes experiments",
                "position": 3,
            },
        )

    @patch("tools.discord_tool._discord_request")
    def test_create_category(self, request, monkeypatch):
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")
        monkeypatch.setattr("hermes_cli.config.load_config", lambda: _config())
        request.return_value = {
            "id": "10", "name": "AGENTS", "type": 4, "guild_id": "111",
        }

        result = json.loads(discord_admin_handler(
            action="create_category", guild_id="111", name="AGENTS",
        ))

        assert result["channel"]["type"] == "category"
        request.assert_called_once_with(
            "POST", "/guilds/111/channels", "test-token",
            body={"name": "AGENTS", "type": 4},
        )

    @patch("tools.discord_tool._discord_request")
    def test_create_uncategorized_channel_omits_unset_parent(self, request, monkeypatch):
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")
        monkeypatch.setattr("hermes_cli.config.load_config", lambda: _config())
        request.return_value = {
            "id": "901", "name": "standalone", "type": 0, "guild_id": "111",
        }

        result = json.loads(discord_admin_handler(
            action="create_channel", guild_id="111", name="standalone",
        ))

        assert result["success"] is True
        request.assert_called_once_with(
            "POST", "/guilds/111/channels", "test-token",
            body={"name": "standalone", "type": 0},
        )

    @patch("tools.discord_tool._discord_request")
    def test_update_channel_verifies_guild_and_clears_parent(self, request, monkeypatch):
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")
        monkeypatch.setattr("hermes_cli.config.load_config", lambda: _config())
        request.side_effect = [
            {"id": "900", "name": "old", "type": 0, "guild_id": "111"},
            {"id": "900", "name": "new", "type": 0, "guild_id": "111", "parent_id": None},
        ]

        result = json.loads(discord_admin_handler(
            action="update_channel",
            channel_id="900",
            name="new",
            parent_id=None,
            topic="Updated topic",
        ))

        assert result["success"] is True
        assert request.call_args_list[0].args == ("GET", "/channels/900", "test-token")
        assert request.call_args_list[1].args == ("PATCH", "/channels/900", "test-token")
        assert request.call_args_list[1].kwargs["body"] == {
            "name": "new", "parent_id": None, "topic": "Updated topic",
        }

    @patch("tools.discord_tool._discord_request")
    def test_mutation_outside_configured_guild_is_blocked(self, request, monkeypatch):
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")
        monkeypatch.setattr("hermes_cli.config.load_config", lambda: _config())
        request.return_value = {"id": "900", "name": "elsewhere", "type": 0, "guild_id": "222"}

        result = json.loads(discord_admin_handler(
            action="update_channel", channel_id="900", name="blocked",
        ))

        assert "outside discord.admin_guild_ids" in result["error"]
        assert request.call_count == 1


class TestDestructiveApproval:
    @patch("tools.approval.request_tool_approval")
    def test_discord_config_can_disable_destructive_prompts(self, approval, monkeypatch):
        monkeypatch.setattr(
            "hermes_cli.config.load_config",
            lambda: {"discord": {"require_destructive_approval": False}},
        )

        assert _request_destructive_approval("delete_channel", "900", "delete it") is None
        approval.assert_not_called()

    @patch("tools.discord_tool._discord_request")
    def test_delete_channel_requires_config_opt_in(self, request, monkeypatch):
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")
        monkeypatch.setattr("hermes_cli.config.load_config", lambda: _config())

        result = json.loads(discord_admin_handler(action="delete_channel", channel_id="900"))

        assert "requires explicit opt-in" in result["error"]
        request.assert_not_called()

    @patch("tools.discord_tool._request_destructive_approval")
    @patch("tools.discord_tool._discord_request")
    def test_delete_channel_runs_after_approval(self, request, approval, monkeypatch):
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")
        monkeypatch.setattr(
            "hermes_cli.config.load_config",
            lambda: _config(actions=["delete_channel"]),
        )
        approval.return_value = None
        request.side_effect = [
            {"id": "900", "name": "temporary", "type": 0, "guild_id": "111"},
            {"id": "900", "name": "temporary", "type": 0, "guild_id": "111"},
        ]

        result = json.loads(discord_admin_handler(action="delete_channel", channel_id="900"))

        assert result["success"] is True
        approval.assert_called_once()
        assert request.call_args_list[1].args == ("DELETE", "/channels/900", "test-token")

    @patch("tools.discord_tool._request_destructive_approval")
    @patch("tools.discord_tool._discord_request")
    def test_delete_channel_stops_when_approval_denied(self, request, approval, monkeypatch):
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")
        monkeypatch.setattr(
            "hermes_cli.config.load_config",
            lambda: _config(actions=["delete_channel"]),
        )
        approval.return_value = json.dumps({"error": "denied"})
        request.return_value = {"id": "900", "name": "keep", "type": 0, "guild_id": "111"}

        result = json.loads(discord_admin_handler(action="delete_channel", channel_id="900"))

        assert result["error"] == "denied"
        assert request.call_count == 1


class TestPermissionOverwrites:
    @patch("tools.discord_tool._discord_request")
    def test_set_member_permission_overwrite(self, request, monkeypatch):
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")
        monkeypatch.setattr("hermes_cli.config.load_config", lambda: _config())
        request.side_effect = [
            {"id": "900", "name": "private", "type": 0, "guild_id": "111"},
            None,
        ]

        result = json.loads(discord_admin_handler(
            action="set_channel_permission",
            channel_id="900",
            overwrite_id="42",
            target_type="member",
            allow="1024",
            deny=0,
        ))

        assert result["success"] is True
        request.assert_any_call(
            "PUT", "/channels/900/permissions/42", "test-token",
            body={"allow": "1024", "deny": "0", "type": 1},
        )


class TestSchemaGates:
    def setup_method(self):
        _reset_capability_cache()

    def teardown_method(self):
        _reset_capability_cache()

    def test_destructive_actions_hidden_without_allowlist(self):
        actions = _available_actions(
            {"detected": True, "has_members_intent": True, "has_message_content": True},
            None,
        )
        assert "create_channel" in actions
        assert "update_channel" in actions
        assert "delete_channel" not in actions
        assert "delete_channel_permission" not in actions

    @patch("tools.discord_tool._discord_request")
    def test_dynamic_schema_exposes_explicit_destructive_actions(self, request, monkeypatch):
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")
        monkeypatch.setattr(
            "hermes_cli.config.load_config",
            lambda: _config(actions=["delete_channel", "delete_channel_permission"]),
        )
        request.return_value = {"flags": (1 << 14) | (1 << 18)}

        schema = get_dynamic_schema_admin()
        actions = schema["parameters"]["properties"]["action"]["enum"]

        assert actions == ["delete_channel", "delete_channel_permission"]
        assert set(actions).issubset(_ADMIN_ACTIONS)
