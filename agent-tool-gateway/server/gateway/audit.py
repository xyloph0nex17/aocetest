import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock


LOG_FILE = Path(__file__).resolve().parents[2] / "sandbox" / "audit.jsonl"
_LOG_LOCK = Lock()


def write_audit(event: dict) -> None:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **event,
    }

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with _LOG_LOCK:
        with LOG_FILE.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")