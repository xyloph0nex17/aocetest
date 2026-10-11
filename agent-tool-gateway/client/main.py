import json
from pathlib import Path

import requests


CALL_FILE = Path(__file__).with_name("sample_call.json")
GATEWAY_URL = "http://127.0.0.1:8000/tool-calls"


def main():
    call = json.loads(CALL_FILE.read_text(encoding="utf-8"))

    response = requests.post(GATEWAY_URL, json=call, timeout=5)
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
        print("需要用户确认；当前确认流程尚未实现，工具没有执行。")


if __name__ == "__main__":
    main()