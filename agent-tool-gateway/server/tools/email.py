import json
from pathlib import Path
from uuid import uuid4


PROJECT_DIR = Path(__file__).resolve().parents[2]
OUTBOX_DIR = PROJECT_DIR / "sandbox" / "outbox"


def send_email(to: str, subject: str, body: str) -> dict:
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)

    message_id = f"mail_{uuid4().hex}"
    path = OUTBOX_DIR / f"{message_id}.json"

    message = {"to": to, "subject": subject, "body": body}
    path.write_text(
        json.dumps(message, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "message_id": message_id,
        "stored_at": path.relative_to(PROJECT_DIR).as_posix(),
    }