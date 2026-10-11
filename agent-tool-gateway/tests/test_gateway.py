import unittest
from copy import deepcopy
from datetime import timedelta
from unittest.mock import patch

from server.gateway.service import handle_tool_call, handle_approval_decision
from server.tools.email import OUTBOX_DIR


class GatewayTests(unittest.TestCase):
    def test_read_note_is_allowed(self):
        call = {
            "call_id": "test_read_001",
            "tool_name": "read_note",
            "arguments": {"path": "todo.md"},
        }

        result = handle_tool_call(call,"user_001")

        self.assertEqual(result["decision"], "allow")
        self.assertEqual(result["status"], "executed")
        self.assertIn("content", result["result"])
    def test_email_waits_for_approval_and_denial_does_not_send(self):
        before = set(OUTBOX_DIR.glob("*.json"))

        call = {
            "call_id": "test_email_001",
            "tool_name": "send_email",
            "arguments": {
                "to": "mentor@example.com",
                "subject": "Test",
                "body": "Hello",
            },
        }

        pending = handle_tool_call(call,"user_001")

        self.assertEqual(pending["decision"], "require_approval")
        self.assertEqual(pending["status"], "pending")
        self.assertEqual(set(OUTBOX_DIR.glob("*.json")), before)

        denied = handle_approval_decision(pending["approval_id"], "deny", "user_001", call)

        self.assertEqual(denied["status"], "denied")
        self.assertEqual(set(OUTBOX_DIR.glob("*.json")), before)
    def test_email_approval_can_be_used_only_once(self):
        call = {
            "call_id": "test_email_once_001",
            "tool_name": "send_email",
            "arguments": {
                "to": "mentor@example.com",
                "subject": "Once",
                "body": "Hello",
            },
        }

        pending = handle_tool_call(call,"user_001")
        created_file = None

        try:
            first = handle_approval_decision(pending["approval_id"], "approve", "user_001", call)
            self.assertEqual(first["status"], "executed")

            message_id = first["result"]["message_id"]
            created_file = OUTBOX_DIR / f"{message_id}.json"
            self.assertTrue(created_file.is_file())

            second = handle_approval_decision(pending["approval_id"], "approve", "user_001", call)
            self.assertEqual(second["status"], "denied")
            self.assertTrue(created_file.is_file())
        finally:
            if created_file is not None:
                created_file.unlink(missing_ok=True)

    def test_other_user_cannot_consume_approval(self):
        before = set(OUTBOX_DIR.glob("*.json"))
        call = {
            "call_id": "test_wrong_user_001",
            "tool_name": "send_email",
            "arguments": {
                "to": "mentor@example.com",
                "subject": "Wrong user",
                "body": "Hello",
            },
        }

        pending = handle_tool_call(call, "user_001")
        approval_id = pending["approval_id"]

        wrong_user = handle_approval_decision(approval_id, "approve", "user_002", call)
        self.assertEqual(wrong_user["status"], "denied")
        self.assertEqual(wrong_user["reason"], "确认者不是原用户")
        self.assertEqual(set(OUTBOX_DIR.glob("*.json")), before)

        original_user = handle_approval_decision(approval_id, "deny", "user_001", call)
        self.assertEqual(original_user["status"], "denied")
        self.assertEqual(original_user["reason"], "用户拒绝")
        self.assertEqual(set(OUTBOX_DIR.glob("*.json")), before)

    def test_changed_confirmation_cannot_consume_approval(self):
        before = set(OUTBOX_DIR.glob("*.json"))
        call = {
            "call_id": "test_changed_confirmation_001",
            "tool_name": "send_email",
            "arguments": {
                "to": "mentor@example.com",
                "subject": "Original",
                "body": "Hello",
            },
        }
        pending = handle_tool_call(call, "user_001")
        approval_id = pending["approval_id"]

        changed_arguments = deepcopy(call)
        changed_arguments["arguments"]["to"] = "attacker@example.com"
        rejected = handle_approval_decision(
            approval_id, "approve", "user_001", changed_arguments
        )
        self.assertEqual(rejected["status"], "denied")
        self.assertEqual(rejected["reason"], "确认参数与待确认记录不一致")
        self.assertEqual(set(OUTBOX_DIR.glob("*.json")), before)

        for field, changed_value in (
            ("call_id", "different_call"),
            ("tool_name", "delete_note"),
        ):
            with self.subTest(field=field):
                changed_call = deepcopy(call)
                changed_call[field] = changed_value
                rejected = handle_approval_decision(
                    approval_id, "approve", "user_001", changed_call
                )
                self.assertEqual(rejected["status"], "denied")
                self.assertEqual(rejected["reason"], "确认调用与待确认记录不一致")
                self.assertEqual(set(OUTBOX_DIR.glob("*.json")), before)

        original_user = handle_approval_decision(approval_id, "deny", "user_001", call)
        self.assertEqual(original_user["reason"], "用户拒绝")
        self.assertEqual(set(OUTBOX_DIR.glob("*.json")), before)

    def test_expired_approval_cannot_send_email(self):
        before = set(OUTBOX_DIR.glob("*.json"))
        call = {
            "call_id": "test_expired_001",
            "tool_name": "send_email",
            "arguments": {
                "to": "mentor@example.com",
                "subject": "Expired",
                "body": "Hello",
            },
        }

        with patch("server.gateway.approvals.APPROVAL_TTL", timedelta(seconds=-1)):
            pending = handle_tool_call(call, "user_001")

        approval_id = pending["approval_id"]
        expired = handle_approval_decision(approval_id, "approve", "user_001", call)
        self.assertEqual(expired["status"], "denied")
        self.assertEqual(expired["reason"], "确认已过期")
        self.assertEqual(set(OUTBOX_DIR.glob("*.json")), before)

        repeated = handle_approval_decision(approval_id, "approve", "user_001", call)
        self.assertEqual(repeated["status"], "denied")
        self.assertEqual(set(OUTBOX_DIR.glob("*.json")), before)

    def test_missing_user_is_denied_before_creating_approval(self):
        before = set(OUTBOX_DIR.glob("*.json"))
        call = {
            "call_id": "test_missing_user_001",
            "tool_name": "send_email",
            "arguments": {
                "to": "mentor@example.com",
                "subject": "Missing user",
                "body": "Hello",
            },
        }

        for user_id in (None, "", "   "):
            with self.subTest(user_id=user_id):
                result = handle_tool_call(call, user_id)
                self.assertEqual(result["decision"], "deny")
                self.assertEqual(result["status"], "denied")
                self.assertEqual(result["reason"], "缺少用户身份")
                self.assertNotIn("approval_id", result)

        self.assertEqual(set(OUTBOX_DIR.glob("*.json")), before)

    def test_unknown_tool_is_denied(self):
        result = handle_tool_call({
            "call_id": "test_unknown_001",
            "tool_name": "unknown_tool",
            "arguments": {},
        },"user_001")
        self.assertEqual(result["decision"], "deny")

    def test_invalid_arguments_are_denied(self):
        result = handle_tool_call({
            "call_id": "test_invalid_001",
            "tool_name": "read_note",
            "arguments": {"path": 123},
        },"user_001")
        self.assertEqual(result["decision"], "deny")

    def test_path_traversal_is_denied(self):
        result = handle_tool_call({
            "call_id": "test_traversal_001",
            "tool_name": "delete_note",
            "arguments": {"path": "../../config.json"},
        },"user_001")
        self.assertEqual(result["decision"], "deny")
        self.assertNotIn("approval_id", result)
