from copy import deepcopy
from uuid import uuid4
from threading import Lock

_APPROVALS_LOCK = Lock()
PENDING_APPROVALS = {}

def create_pending(call: dict) -> str:
    approval_id = f"approval_{uuid4().hex}"
    with _APPROVALS_LOCK:
        PENDING_APPROVALS[approval_id] = {
            "call_id": call["call_id"],
            "tool_name": call["tool_name"],
            "arguments": deepcopy(call["arguments"]),
        }
    return approval_id

def take_pending(approval_id: str) -> dict | None:
    with _APPROVALS_LOCK:
        return PENDING_APPROVALS.pop(approval_id, None)