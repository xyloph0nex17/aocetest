from pathlib import Path

PAGE_URL = "https://example.test/injected-page"
PAGE_FILE = (
    Path(__file__).resolve().parents[2]
    / "sandbox"
    / "webpages"
    / "injected_page.html"
)


def read_webpage(url: str) -> str:
    if url != PAGE_URL:
        raise ValueError("未知的示例网页")
    return PAGE_FILE.read_text(encoding="utf-8")