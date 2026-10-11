from server.gateway.validator import validate_call
from server.tools.notes import read_note
from server.gateway.approvals import create_pending
from server.gateway.approvals import take_pending
from server.tools.email import send_email
from server.tools.notes import delete_note

def handle_tool_call(call):
    call_id = call.get("call_id") if isinstance(call, dict) else None
    decision, reason = validate_call(call)

    if decision == "deny":
        return {
            "call_id": call_id,
            "decision": "deny",
            "status": "denied",
            "reason": reason,
        }

    if decision == "require_approval":
        approval_id = create_pending(call)
        return {
            "call_id": call_id,
            "decision": "require_approval",
            "status": "pending",
            "reason": "需要用户确认",
            "approval_id": approval_id,
        }

    # 当前只有 read_note 被允许自动执行。
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

def handle_approval_decision(approval_id: str, action: str):
    if action not in ("approve", "deny"):
        return {"status": "denied", "reason": "action 必须是 approve 或 deny"}

    record = take_pending(approval_id)
    if record is None:
        return {"status": "denied", "reason": "确认不存在或已经使用"}

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