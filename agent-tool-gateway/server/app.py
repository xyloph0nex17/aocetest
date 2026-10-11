from fastapi import FastAPI, Request

from server.gateway.service import handle_tool_call
from server.gateway.service import handle_approval_decision
from server.gateway.audit import write_audit
app = FastAPI()


@app.post("/tool-calls")
async def tool_calls(request: Request):
    try:
        call = await request.json()
    except ValueError:
        call = None

    result = handle_tool_call(call)
    write_audit({
        "event": "tool_call",
        "call_id": result.get("call_id"),
        "tool_name": call.get("tool_name") if isinstance(call, dict) else None,
        "decision": result.get("decision"),
        "status": result.get("status"),
        "reason": result.get("reason"),
        "approval_id": result.get("approval_id"),
        "execution_result": result.get("result"),
    })

    return result

@app.post("/approvals/{approval_id}/decision")
async def approval_decision(approval_id: str, request: Request):
    try:
        body = await request.json()
    except ValueError:
        body = None

    action = body.get("action") if isinstance(body, dict) else None
    result = handle_approval_decision(approval_id, action)

    write_audit({
        "event": "approval_decision",
        "approval_id": approval_id,
        "action": action,
        "call_id": result.get("call_id"),
        "status": result.get("status"),
        "reason": result.get("reason"),
        "execution_result": result.get("result"),
    })

    return result