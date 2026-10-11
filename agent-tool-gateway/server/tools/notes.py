from pathlib import Path

from server.gateway.validator import safe_note_path


NOTES_DIR = (Path(__file__).resolve().parents[2] / "sandbox" / "notes").resolve()


def read_note(raw_path: str) -> str:
    if not safe_note_path(raw_path):
        raise ValueError("目标路径超出 sandbox/notes")

    target = (NOTES_DIR / raw_path).resolve()
    return target.read_text(encoding="utf-8")