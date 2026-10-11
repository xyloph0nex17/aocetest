from copy import deepcopy
from uuid import uuid4
from threading import Lock
import hashlib
import json
from datetime import datetime, timedelta, timezone

APPROVAL_TTL = timedelta(minutes=5)
_APPROVALS_LOCK = Lock()
PENDING_APPROVALS = {}
def hash_arguments(arguments: dict) -> str:
    canonical = json.dumps(
        arguments,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

def create_pending(call: dict,user_id:str) -> str:
    approval_id = f"approval_{uuid4().hex}"
    arguments = deepcopy(call["arguments"])
    with _APPROVALS_LOCK:
        PENDING_APPROVALS[approval_id] = {
            "approval_id": approval_id,
            "call_id": call["call_id"],
            "tool_name": call["tool_name"],
            "arguments": arguments,
            "argument_hash": hash_arguments(arguments),
            "user_id": user_id,
            "expires_at": datetime.now(timezone.utc) + APPROVAL_TTL,
            "used": False,
        }
    return approval_id

def take_pending(
    approval_id: str,
    user_id: str | None,
    confirmation: dict | None,
) -> tuple[dict | None, str | None]:
    with _APPROVALS_LOCK:
        record = PENDING_APPROVALS.get(approval_id)

        if record is None:
            return None, "确认不存在或已经使用"

        if not user_id or record["user_id"] != user_id:
            return None, "确认者不是原用户"
        if record["used"]:
            return None, "确认已经使用"
        if datetime.now(timezone.utc) >= record["expires_at"]:
            PENDING_APPROVALS.pop(approval_id)
            return None, "确认已过期"
        if not isinstance(confirmation, dict):
            return None, "确认请求缺少调用信息"

        if (
            confirmation.get("call_id") != record["call_id"]
            or confirmation.get("tool_name") != record["tool_name"]
        ):
            return None, "确认调用与待确认记录不一致"

        arguments = confirmation.get("arguments")
        if not isinstance(arguments, dict):
            return None, "确认参数不合法"

        if hash_arguments(record["arguments"]) != record["argument_hash"]:
            return None, "待确认参数已变化"

        if hash_arguments(arguments) != record["argument_hash"]:
            return None, "确认参数与待确认记录不一致"
        record["used"] = True
        return deepcopy(record), None

def get_approval_audit_context(approval_id: str) -> dict | None:
    with _APPROVALS_LOCK:
        record = PENDING_APPROVALS.get(approval_id)
        if record is None:
            return None
        return {
            "call_id": record["call_id"],
            "tool_name": record["tool_name"],
        }
