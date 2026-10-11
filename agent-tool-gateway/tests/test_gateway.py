import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from threading import Barrier
from tempfile import TemporaryDirectory
from unittest.mock import patch
# from uuid import uuid4

from server.app import approval_decision, tool_calls
from server.gateway.service import handle_tool_call, handle_approval_decision
from server.tools.email import OUTBOX_DIR
from server.tools.notes import NOTES_DIR


class GatewayTests(unittest.TestCase):
    def test_http_flow_writes_audit_records(self):
        class FakeRequest:
            headers = {"X-User-Id": "user_001"}

            def __init__(self, body: dict):
                self.body = body

            async def json(self):
                return self.body

        def run_endpoint(coroutine):
            try:
                coroutine.send(None)
            except StopIteration as completed:
                return completed.value
            coroutine.close()
            raise AssertionError("接口出现未预期的异步等待")

        call = {
            "call_id": "test_audit_001",
            "tool_name": "send_email",
            "arguments": {
                "to": "mentor@example.com",
                "subject": "Audit test",
                "body": "Hello",
            },
        }
        created_file = None

        try:
            with TemporaryDirectory(dir=NOTES_DIR.parent) as temp_dir:
                log_file = Path(temp_dir) / "audit.jsonl"
                with patch("server.gateway.audit.LOG_FILE", log_file):
                    pending = run_endpoint(tool_calls(FakeRequest(call)))
                    confirmation = {"action": "approve", **call}
                    approved = run_endpoint(
                        approval_decision(
                            pending["approval_id"], FakeRequest(confirmation)
                        )
                    )

                    denied_call = deepcopy(call)
                    denied_call["call_id"] = "test_audit_denied_001"
                    denied_pending = run_endpoint(tool_calls(FakeRequest(denied_call)))
                    denied = run_endpoint(
                        approval_decision(
                            denied_pending["approval_id"],
                            FakeRequest({"action": "deny", **denied_call}),
                        )
                    )

                    tampered_call = deepcopy(call)
                    tampered_call["call_id"] = "test_audit_tampered_001"
                    tampered_pending = run_endpoint(tool_calls(FakeRequest(tampered_call)))
                    tampered_confirmation = deepcopy(tampered_call)
                    tampered_confirmation["arguments"]["to"] = "attacker@example.com"
                    rejected = run_endpoint(
                        approval_decision(
                            tampered_pending["approval_id"],
                            FakeRequest({"action": "approve", **tampered_confirmation}),
                        )
                    )

                created_file = OUTBOX_DIR / f"{approved['result']['message_id']}.json"
                records = [
                    json.loads(line)
                    for line in log_file.read_text(encoding="utf-8").splitlines()
                ]

                self.assertEqual(len(records), 6)
                self.assertEqual(records[0]["event"], "tool_call")
                self.assertEqual(records[0]["user_id"], "user_001")
                self.assertEqual(records[0]["tool_name"], "send_email")
                self.assertEqual(records[0]["decision"], "require_approval")
                self.assertEqual(records[0]["approval_id"], pending["approval_id"])
                self.assertEqual(records[1]["event"], "approval_decision")
                self.assertEqual(records[1]["user_id"], "user_001")
                self.assertEqual(records[1]["call_id"], call["call_id"])
                self.assertEqual(records[1]["tool_name"], "send_email")
                self.assertEqual(records[1]["action"], "approve")
                self.assertEqual(records[1]["decision"], "allow")
                self.assertEqual(records[1]["status"], "executed")
                self.assertEqual(records[1]["execution_result"], approved["result"])
                self.assertEqual(denied["status"], "denied")
                self.assertEqual(records[2]["decision"], "require_approval")
                self.assertEqual(records[3]["event"], "approval_decision")
                self.assertEqual(records[3]["user_id"], "user_001")
                self.assertEqual(records[3]["call_id"], denied_call["call_id"])
                self.assertEqual(records[3]["tool_name"], "send_email")
                self.assertEqual(records[3]["action"], "deny")
                self.assertEqual(records[3]["decision"], "deny")
                self.assertEqual(records[3]["status"], "denied")
                self.assertIsNone(records[3]["execution_result"])
                self.assertEqual(rejected["status"], "denied")
                self.assertNotIn("call_id", rejected)
                self.assertNotIn("tool_name", rejected)
                self.assertEqual(records[4]["decision"], "require_approval")
                self.assertEqual(records[5]["event"], "approval_decision")
                self.assertEqual(records[5]["call_id"], tampered_call["call_id"])
                self.assertEqual(records[5]["tool_name"], "send_email")
                self.assertEqual(records[5]["decision"], "deny")
                self.assertEqual(records[5]["status"], "denied")
                self.assertIsNone(records[5]["execution_result"])
        finally:
            if created_file is not None:
                created_file.unlink(missing_ok=True)

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

        repeated = handle_approval_decision(
            pending["approval_id"], "approve", "user_001", call
        )
        self.assertEqual(repeated["status"], "denied")
        self.assertEqual(repeated["reason"], "确认已经使用")
        self.assertEqual(set(OUTBOX_DIR.glob("*.json")), before)

    def test_approved_tool_failure_is_allowed_but_failed(self):
        call = {
            "call_id": "test_email_failure_001",
            "tool_name": "send_email",
            "arguments": {
                "to": "mentor@example.com",
                "subject": "Failure test",
                "body": "Hello",
            },
        }
        pending = handle_tool_call(call, "user_001")

        with patch("server.gateway.service.send_email", side_effect=OSError("模拟写入失败")):
            result = handle_approval_decision(
                pending["approval_id"], "approve", "user_001", call
            )

        self.assertEqual(result["decision"], "allow")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "模拟写入失败")
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

    def test_concurrent_approval_executes_only_once(self):
        call = {
            "call_id": "test_concurrent_001",
            "tool_name": "send_email",
            "arguments": {
                "to": "mentor@example.com",
                "subject": "Concurrent approval",
                "body": "Hello",
            },
        }
        pending = handle_tool_call(call, "user_001")
        approval_id = pending["approval_id"]
        barrier = Barrier(3)
        results = []

        def approve_at_same_time():
            barrier.wait(timeout=5)
            return handle_approval_decision(approval_id, "approve", "user_001", call)

        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(approve_at_same_time) for _ in range(2)]
                barrier.wait(timeout=5)
                results = [future.result(timeout=5) for future in futures]

            self.assertCountEqual(
                [result["status"] for result in results],
                ["executed", "denied"],
            )
            executed = next(result for result in results if result["status"] == "executed")
            path = OUTBOX_DIR / f"{executed['result']['message_id']}.json"
            self.assertTrue(path.is_file())
        finally:
            for result in results:
                if result.get("status") == "executed":
                    path = OUTBOX_DIR / f"{result['result']['message_id']}.json"
                    path.unlink(missing_ok=True)

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

    def test_absolute_note_path_is_denied(self):
        absolute_path = str(NOTES_DIR / "todo.md")
        for tool_name in ("read_note", "delete_note"):
            with self.subTest(tool_name=tool_name):
                result = handle_tool_call({
                    "call_id": f"test_absolute_{tool_name}",
                    "tool_name": tool_name,
                    "arguments": {"path": absolute_path},
                }, "user_001")
                self.assertEqual(result["decision"], "deny")
                self.assertNotIn("approval_id", result)

    # def test_symlink_cannot_escape_notes(self):
    #     with TemporaryDirectory(dir=NOTES_DIR.parent) as outside_dir:
    #         outside_file = Path(outside_dir) / "outside.txt"
    #         outside_file.write_text("outside content", encoding="utf-8")
    #         link = NOTES_DIR / f"test_link_{uuid4().hex}.txt"
    #
    #         try:
    #             link.symlink_to(outside_file)
    #         except (OSError, NotImplementedError) as exc:
    #             self.skipTest(f"此环境不能创建符号链接：{exc}")
    #
    #         try:
    #             for tool_name in ("read_note", "delete_note"):
    #                 with self.subTest(tool_name=tool_name):
    #                     result = handle_tool_call({
    #                         "call_id": f"test_symlink_{tool_name}",
    #                         "tool_name": tool_name,
    #                         "arguments": {"path": link.name},
    #                     }, "user_001")
    #                     self.assertEqual(result["decision"], "deny")
    #                     self.assertNotIn("approval_id", result)
    #
    #             self.assertEqual(
    #                 outside_file.read_text(encoding="utf-8"), "outside content"
    #             )
    #         finally:
    #             link.unlink(missing_ok=True)
