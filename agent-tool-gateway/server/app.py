from fastapi import FastAPI, Request

from server.gateway.service import handle_tool_call


app = FastAPI()


@app.post("/tool-calls")
async def tool_calls(request: Request):
    try:
        call = await request.json()
    except ValueError:
        call = None

    return handle_tool_call(call)