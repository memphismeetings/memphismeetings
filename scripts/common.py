from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9\s-]", "", value)
    value = re.sub(r"[\s_-]+", "-", value)
    return value.strip("-")


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def sec_to_clock(seconds: float | int) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def split_turns(text: str) -> list[dict[str, Any]]:
    """Split a transcript chunk on '>>'' speaker-change markers into individual turns."""
    parts = re.split(r"\s*>>\s*", text or "")
    return [
        {"text": t.strip(), "speaker_id": "", "speaker_name": ""}
        for t in parts
        if t.strip()
    ]


def video_id_from_url(url: str) -> str:
    patterns = [
        r"(?:v=)([A-Za-z0-9_-]{11})",
        r"youtu\.be/([A-Za-z0-9_-]{11})",
        r"youtube\.com/embed/([A-Za-z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError(f"Could not extract a YouTube video id from: {url}")


def chunk_transcript(
    transcript_rows: list[dict[str, Any]],
    chunk_seconds: int = 120,
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    if not transcript_rows:
        return chunks

    start = float(transcript_rows[0].get("start", 0))
    current_chunk_end = start + chunk_seconds
    buffer: list[dict[str, Any]] = []

    def flush(chunk_index: int, rows: list[dict[str, Any]]) -> dict[str, Any]:
        chunk_start = float(rows[0].get("start", 0))
        last = rows[-1]
        chunk_end = float(last.get("start", 0)) + float(last.get("duration", 0))
        text = " ".join((r.get("text") or "").strip() for r in rows).strip()
        return {
            "chunk_index": chunk_index,
            "start": round(chunk_start, 2),
            "end": round(chunk_end, 2),
            "text": text,
        }

    for row in transcript_rows:
        row_start = float(row.get("start", 0))
        if buffer and row_start > current_chunk_end:
            chunks.append(flush(len(chunks), buffer))
            buffer = []
            current_chunk_end = row_start + chunk_seconds
        buffer.append(row)

    if buffer:
        chunks.append(flush(len(chunks), buffer))

    return chunks
