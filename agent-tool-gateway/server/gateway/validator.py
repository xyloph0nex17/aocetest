from jsonschema import ValidationError, validate
from pathlib import Path
from .registry import TOOLS

def safe_note_path(raw_path: str) -> bool:
    path = Path(raw_path)

    # 拒绝空路径、绝对路径、带盘符的路径和..
    if not raw_path or path.anchor or ".." in path.parts:
        return False

    notes_dir = (Path(__file__).resolve().parents[2] / "sandbox" / "notes").resolve()

    try:
        target = (notes_dir / path).resolve()
    except (OSError, ValueError):
        return False

    # resolve() 会跟随符号链接；目标必须仍在 notes 目录内
    return target != notes_dir and target.is_relative_to(notes_dir)

def validate_call(call: dict) -> tuple[str, str]:
    if not isinstance(call, dict):
        return "deny", "工具调用必须是对象"
    if not isinstance(call.get("call_id"), str) or not call["call_id"]:
        return "deny", "call_id 必须是非空字符串"

    tool_name = call.get("tool_name")
    if not isinstance(tool_name, str) or tool_name not in TOOLS:
        return "deny", "未知工具"

    tool = TOOLS[tool_name]
    try:
        validate(instance=call.get("arguments"), schema=tool["input_schema"])
    except ValidationError as exc:
        return "deny", f"参数不合法：{exc.message}"
    if tool_name in {"read_note", "delete_note"}:
        if not safe_note_path(call["arguments"]["path"]):
            return "deny", "目标路径超出 sandbox/notes"
    return tool["decision"], "工具名、参数格式和资源范围合法"
