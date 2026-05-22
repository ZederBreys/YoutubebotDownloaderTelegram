import re
from pathlib import Path

CHANGELOG_FILE = Path(__file__).resolve().parent / "change_log.txt"
MAX_PAGE_CHARS = 3800
ENTRY_HEADER = re.compile(r"^(\d+\.\d+\.\d+v)\s*-\s*(.+?)\s*$", re.MULTILINE)

_changelog_cache: tuple[float, list[str]] | None = None


def _parse_entries(content: str) -> list[dict]:
    entries: list[dict] = []
    matches = list(ENTRY_HEADER.finditer(content))
    if not matches:
        return entries

    for index, match in enumerate(matches):
        body_start = match.end()
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        body = content[body_start:body_end].strip()
        entries.append(
            {
                "version": match.group(1),
                "date": match.group(2).strip(),
                "body": body,
            }
        )
    return entries


def _format_entry(entry: dict) -> str:
    lines = [f"<b>{entry['version']}</b> — {entry['date']}"]
    if entry["body"]:
        lines.append(entry["body"])
    return "\n".join(lines)


def _build_pages(entries: list[dict]) -> list[str]:
    if not entries:
        return []

    pages: list[str] = []
    current = "<b>📋 История обновлений бота</b>\n\n"

    for entry in entries:
        block = _format_entry(entry) + "\n\n"
        if len(current) + len(block) > MAX_PAGE_CHARS and current.strip():
            pages.append(current.rstrip())
            current = ""
        current += block

    if current.strip():
        pages.append(current.rstrip())

    return pages


def get_changelog_pages() -> list[str]:
    global _changelog_cache

    if not CHANGELOG_FILE.exists():
        return []

    mtime = CHANGELOG_FILE.stat().st_mtime
    if _changelog_cache and _changelog_cache[0] == mtime:
        return _changelog_cache[1]

    content = CHANGELOG_FILE.read_text(encoding="utf-8").strip()
    entries = _parse_entries(content)
    pages = _build_pages(entries)
    _changelog_cache = (mtime, pages)
    return pages
