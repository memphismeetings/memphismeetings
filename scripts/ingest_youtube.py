from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from yt_dlp import YoutubeDL
from youtube_transcript_api import YouTubeTranscriptApi

from common import chunk_transcript, dump_json, slugify, video_id_from_url, split_turns


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest a public meeting YouTube video and transcript")
    parser.add_argument("url", help="YouTube URL")
    parser.add_argument("--body-id", default="memphis-city-council", help="Body id from config.yaml")
    parser.add_argument("--date", help="Meeting date as YYYY-MM-DD")
    parser.add_argument("--meeting-id", help="Override meeting id")
    parser.add_argument("--chunk-seconds", type=int, default=120, help="Transcript chunk size in seconds")
    return parser.parse_args()


def fetch_video_info(url: str) -> dict[str, Any]:
    with YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
        info = ydl.extract_info(url, download=False)
    return {
        "title": info.get("title"),
        "description": info.get("description", ""),
        "uploader": info.get("uploader"),
        "upload_date": info.get("upload_date"),
        "duration": info.get("duration"),
    }


def fetch_transcript(video_id: str) -> list[dict[str, Any]]:
    api = YouTubeTranscriptApi()
    if hasattr(api, "fetch"):
        items = api.fetch(video_id)
    elif hasattr(YouTubeTranscriptApi, "get_transcript"):
        items = YouTubeTranscriptApi.get_transcript(video_id)
    else:
        raise RuntimeError("Unsupported youtube-transcript-api version: no transcript fetch method found")

    return [
        {
            "text": (row.get("text") if isinstance(row, dict) else getattr(row, "text", "")).replace("\n", " ").strip(),
            "start": round(float(row.get("start", 0) if isinstance(row, dict) else getattr(row, "start", 0)), 2),
            "duration": round(float(row.get("duration", 0) if isinstance(row, dict) else getattr(row, "duration", 0)), 2),
        }
        for row in items
    ]


def body_lookup(cfg: dict[str, Any], body_id: str) -> dict[str, Any]:
    for body in cfg.get("bodies", []):
        if body.get("id") == body_id:
            return body
    raise ValueError(f"Body id not found in config.yaml: {body_id}")


def main() -> None:
    args = get_args()
    root = Path(__file__).resolve().parent.parent

    cfg = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    body = body_lookup(cfg, args.body_id)

    video_id = video_id_from_url(args.url)
    info = fetch_video_info(args.url)
    transcript_rows = fetch_transcript(video_id)
    chunks = chunk_transcript(transcript_rows, chunk_seconds=args.chunk_seconds)

    meeting_date = args.date or date.today().isoformat()
    default_id = f"{meeting_date}-{slugify(body['id'])}"
    meeting_id = args.meeting_id or default_id

    raw_payload = {
        "meeting_id": meeting_id,
        "video_id": video_id,
        "url": args.url,
        "video": info,
        "transcript_rows": transcript_rows,
    }

    processed_payload = {
        "id": meeting_id,
        "title": info.get("title") or f"{body['name']} Meeting",
        "date": meeting_date,
        "body_id": body["id"],
        "body_name": body["name"],
        "youtube_url": args.url,
        "video_id": video_id,
        "duration": info.get("duration"),
        "description": info.get("description", ""),
        "councilpeople": body.get("councilpeople", []),
        "transcript": chunks,
    }

    raw_path = root / "data" / "raw" / f"{meeting_id}.json"
    processed_path = root / "data" / "processed" / "meetings" / f"{meeting_id}.json"
    annotation_path = root / "data" / "annotations" / "meetings" / f"{meeting_id}.json"

    dump_json(raw_path, raw_payload)
    dump_json(processed_path, processed_payload)

    if not annotation_path.exists():
        starter_annotation = {
            "meeting_id": meeting_id,
            "meeting_summary": "",
            "global_tags": [],
            "sections": [
                {
                    "chunk_index": chunk["chunk_index"],
                    "speaker_id": "",
                    "speaker_name": "",
                    "lines": split_turns(chunk.get("text", "")),
                    "display_mode": "raw",
                    "display_text": "",
                    "summary": "",
                    "tags": [],
                    "mentions": [],
                    "votes": [],
                    "notes": "",
                }
                for chunk in chunks
            ],
        }
        dump_json(annotation_path, starter_annotation)

    print(f"Wrote {raw_path.relative_to(root)}")
    print(f"Wrote {processed_path.relative_to(root)}")
    print(f"Annotation template: {annotation_path.relative_to(root)}")


if __name__ == "__main__":
    main()
