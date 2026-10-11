import json
from pathlib import Path
import requests
import sys

CALL_FILE = Path(__file__).with_name("read_note_call.json")
GATEWAY_BASE_URL = "http://127.0.0.1:8000"
GATEWAY_URL = f"{GATEWAY_BASE_URL}/tool-calls"
USER_ID = "user_001"
HEADERS = {"X-User-Id": USER_ID}

def main():
    call_file = Path(sys.argv[1]) if len(sys.argv) > 1 else CALL_FILE
    call = json.loads(call_file.read_text(encoding="utf-8"))
    
    response = requests.post(
        GATEWAY_URL, 
        json=call, 
        timeout=5,
        headers=HEADERS,
    )
    response.raise_for_status()
    result = response.json()

    if result["decision"] == "allow":
        if result["status"] == "executed":
            print("工具执行结果：", result["result"])
        else:
            print("工具执行失败：", result["reason"])
    elif result["decision"] == "deny":
        print("调用被拒绝：", result["reason"])
    elif result["decision"] == "require_approval":
        print("工具：", call["tool_name"])
        for name, value in call["arguments"].items():
            print(f"{name}:{value}")

        answer = input("输入 approve 确认执行；输入其他内容拒绝：").strip()
        action = "approve" if answer == "approve" else "deny"

        approval_url = (
            f"{GATEWAY_BASE_URL}/approvals/"
            f"{result['approval_id']}/decision"
        )
        approval_response = requests.post(
            approval_url,
            json={
                "action": action,
                "call_id": call["call_id"],
                "tool_name": call["tool_name"],
                "arguments": call["arguments"],
            },
            timeout=5,
            headers=HEADERS,
        )
        approval_response.raise_for_status()
        print("确认结果：", approval_response.json())


if __name__ == "__main__":
    main()
