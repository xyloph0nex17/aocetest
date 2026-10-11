from server.gateway.validator import validate_call
from server.tools.notes import read_note
from server.gateway.approvals import create_pending
from server.gateway.approvals import take_pending
from server.tools.email import send_email
from server.tools.notes import delete_note

def handle_tool_call(call,user_id: str | None):
    call_id = call.get("call_id") if isinstance(call, dict) else None
    if not isinstance(user_id, str) or not user_id.strip():
        return {
            "call_id": call_id,
            "decision": "deny",
            "status": "denied",
            "reason": "缺少用户身份",
        }
    decision, reason = validate_call(call)

    if decision == "deny":
        return {
            "call_id": call_id,
            "decision": "deny",
            "status": "denied",
            "reason": reason,
        }

    if decision == "require_approval":
        approval_id = create_pending(call,user_id)
        return {
            "call_id": call_id,
            "decision": "require_approval",
            "status": "pending",
            "reason": "需要用户确认",
            "approval_id": approval_id,
        }

    if call["tool_name"] != "read_note":
        return {
            "call_id": call_id,
            "decision": "deny",
            "status": "denied",
            "reason": "该工具尚未实现自动执行",
        }

    try:
        content = read_note(call["arguments"]["path"])
    except (OSError, ValueError) as exc:
        return {
            "call_id": call_id,
            "decision": "allow",
            "status": "failed",
            "reason": str(exc),
        }

    return {
        "call_id": call_id,
        "decision": "allow",
        "status": "executed",
        "result": {"content": content},
    }

def handle_approval_decision(
    approval_id: str,
    action: str,
    user_id: str | None,
    confirmation: dict | None = None,
):
    if action not in ("approve", "deny"):
        return {"status": "denied", "reason": "action 必须是 approve 或 deny"}

    record, error = take_pending(approval_id, user_id, confirmation)
    if record is None:
        return {"status": "denied", "reason": error}

    if action == "deny":
        return {
            "call_id": record["call_id"],
            "status": "denied",
            "reason": "用户拒绝",
        }

    try:
        if record["tool_name"] == "send_email":
            result = send_email(**record["arguments"])
        elif record["tool_name"] == "delete_note":
            result = delete_note(record["arguments"]["path"])
        else:
            return {
                "call_id": record["call_id"],
                "status": "failed",
                "reason": "未知的待确认工具",
            }
    except (OSError, ValueError) as exc:
        return {
            "call_id": record["call_id"],
            "status": "failed",
            "reason": str(exc),
        }

    return {
        "call_id": record["call_id"],
        "status": "executed",
        "result": result,
    }