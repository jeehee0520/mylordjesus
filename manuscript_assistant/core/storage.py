"""Local storage of pasted author guidelines (and the profile confirmed for them).

Everything is kept on this computer in ~/.manuscript_assistant/guidelines (or the folder
named by MA_DATA_DIR), one JSON file per guideline text, so a journal's rules can be
reused next time without pasting or confirming them again.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


def data_dir() -> Path:
    base = Path(os.environ.get("MA_DATA_DIR") or Path.home() / ".manuscript_assistant")
    path = base / "guidelines"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class SavedGuideline:
    id: str
    name: str
    text: str
    saved_at: str
    profile_json: str = ""  # the profile as last analysed or confirmed

    @property
    def label(self) -> str:
        confirmed = bool(self.profile_json) and json.loads(self.profile_json).get("confirmed")
        return f"{'✔️ 확정됨 · ' if confirmed else ''}{self.name} ({self.saved_at[:16].replace('T', ' ')})"


def text_id(text: str) -> str:
    normalized = " ".join(text.split())
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]


def save(text: str, name: str = "", profile_json: str = "") -> SavedGuideline:
    """Create or update the entry for this text (the same text is never stored twice)."""
    gid = text_id(text)
    old = load(gid)
    entry = SavedGuideline(
        id=gid,
        name=name or (old.name if old else "") or _default_name(text),
        text=text,
        saved_at=datetime.now().isoformat(timespec="seconds"),
        profile_json=profile_json or (old.profile_json if old else ""),
    )
    path = data_dir() / f"{gid}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(entry), ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)
    return entry


def load(gid: str) -> SavedGuideline | None:
    path = data_dir() / f"{gid}.json"
    if not path.exists():
        return None
    try:
        return SavedGuideline(**json.loads(path.read_text(encoding="utf-8")))
    except (ValueError, TypeError):
        return None


def list_saved() -> list[SavedGuideline]:
    items = [load(p.stem) for p in data_dir().glob("*.json")]
    return sorted((i for i in items if i), key=lambda i: i.saved_at, reverse=True)


def delete(gid: str) -> None:
    (data_dir() / f"{gid}.json").unlink(missing_ok=True)


def _default_name(text: str) -> str:
    first = next((line.strip() for line in text.splitlines() if line.strip()), "투고 규정")
    return first[:60]
