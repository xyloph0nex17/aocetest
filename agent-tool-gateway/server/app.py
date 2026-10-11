from fastapi import FastAPI, Request

from server.gateway.service import handle_tool_call
from server.gateway.service import handle_approval_decision

app = FastAPI()


@app.post("/tool-calls")
async def tool_calls(request: Request):
    try:
        call = await request.json()
    except ValueError:
        call = None

    return handle_tool_call(call)

@app.post("/approvals/{approval_id}/decision")
async def approval_decision(approval_id: str, request: Request):
    try:
        body = await request.json()
    except ValueError:
        body = None

    action = body.get("action") if isinstance(body, dict) else None
    return handle_approval_decision(approval_id, action)