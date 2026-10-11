import unittest
from server.gateway.service import handle_tool_call, handle_approval_decision
from server.tools.email import OUTBOX_DIR


class GatewayTests(unittest.TestCase):
    def test_read_note_is_allowed(self):
        call = {
            "call_id": "test_read_001",
            "tool_name": "read_note",
            "arguments": {"path": "todo.md"},
        }

        result = handle_tool_call(call)

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

        pending = handle_tool_call(call)

        self.assertEqual(pending["decision"], "require_approval")
        self.assertEqual(pending["status"], "pending")
        self.assertEqual(set(OUTBOX_DIR.glob("*.json")), before)

        denied = handle_approval_decision(pending["approval_id"], "deny")

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

        pending = handle_tool_call(call)
        created_file = None

        try:
            first = handle_approval_decision(pending["approval_id"], "approve")
            self.assertEqual(first["status"], "executed")

            message_id = first["result"]["message_id"]
            created_file = OUTBOX_DIR / f"{message_id}.json"
            self.assertTrue(created_file.is_file())

            second = handle_approval_decision(pending["approval_id"], "approve")
            self.assertEqual(second["status"], "denied")
            self.assertTrue(created_file.is_file())
        finally:
            if created_file is not None:
                created_file.unlink(missing_ok=True)
    def test_unknown_tool_is_denied(self):
        result = handle_tool_call({
            "call_id": "test_unknown_001",
            "tool_name": "unknown_tool",
            "arguments": {},
        })
        self.assertEqual(result["decision"], "deny")

    def test_invalid_arguments_are_denied(self):
        result = handle_tool_call({
            "call_id": "test_invalid_001",
            "tool_name": "read_note",
            "arguments": {"path": 123},
        })
        self.assertEqual(result["decision"], "deny")

    def test_path_traversal_is_denied(self):
        result = handle_tool_call({
            "call_id": "test_traversal_001",
            "tool_name": "delete_note",
            "arguments": {"path": "../../config.json"},
        })
        self.assertEqual(result["decision"], "deny")
        self.assertNotIn("approval_id", result)