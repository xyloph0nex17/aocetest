from server.gateway.validator import validate_call
from server.tools.notes import read_note
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
        return {
            "call_id": call_id,
            "decision": "require_approval",
            "status": "unavailable",
            "reason": "确认流程尚未实现；工具未执行",
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
