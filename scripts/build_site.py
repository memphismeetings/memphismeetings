from __future__ import annotations

import argparse
import re
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

from datetime import date, timedelta

from common import load_json, sec_to_clock, slugify, split_turns


def compute_meeting_stats(sections: list[dict[str, Any]]) -> dict[str, Any]:
    tag_seconds: dict[str, float] = defaultdict(float)
    tag_labels: dict[str, str] = {}
    annotated = 0
    vote_tally: dict[str, int] = defaultdict(int)
    for section in sections:
        duration = max(0.0, float(section.get("end", 0)) - float(section.get("start", 0)))
        for slug, label in zip(section.get("tags", []), section.get("raw_tags", [])):
            tag_seconds[slug] += duration
            tag_labels[slug] = label
        if section.get("summary"):
            annotated += 1
        for vote in section.get("votes", []):
            v = vote.get("vote", "").lower()
            if v:
                vote_tally[v] += 1
    sorted_tags = sorted(tag_seconds.items(), key=lambda x: x[1], reverse=True)
    top_tags = [
        {"slug": slug, "label": tag_labels.get(slug, slug), "minutes": max(1, round(secs / 60))}
        for slug, secs in sorted_tags[:6]
        if secs > 0
    ]
    return {
        "top_tags": top_tags,
        "vote_tally": dict(vote_tally),
        "total_votes": sum(vote_tally.values()),
        "annotated_sections": annotated,
        "total_sections": len(sections),
    }


def compute_person_stats(
    tag_entries: list[dict[str, Any]],
    votes: list[dict[str, Any]],
    cutoff_date: str,
) -> dict[str, Any]:
    recent_tag_seconds: dict[str, float] = defaultdict(float)
    recent_tag_labels: dict[str, str] = {}
    recent_meeting_ids: set[str] = set()
    for entry in tag_entries:
        if entry.get("meeting_date", "") >= cutoff_date:
            recent_tag_seconds[entry["slug"]] += entry["seconds"]
            recent_tag_labels[entry["slug"]] = entry["label"]
            recent_meeting_ids.add(entry["meeting_id"])
    sorted_tags = sorted(recent_tag_seconds.items(), key=lambda x: x[1], reverse=True)
    top_tags = [
        {"slug": slug, "label": recent_tag_labels[slug], "minutes": max(1, round(secs / 60))}
        for slug, secs in sorted_tags[:3]
        if secs > 0
    ]
    vote_tally: dict[str, int] = defaultdict(int)
    for vote in votes:
        if vote.get("meeting_date", "") >= cutoff_date:
            v = vote.get("vote", "").lower()
            if v:
                vote_tally[v] += 1
    return {
        "top_tags_year": top_tags,
        "recent_meeting_count": len(recent_meeting_ids),
        "vote_tally_year": dict(vote_tally),
    }


def compute_site_stats(
    meetings: list[dict[str, Any]],
    tag_total_seconds: dict[str, tuple[float, str]],
) -> dict[str, Any]:
    total_duration = sum(float(m.get("duration") or 0) for m in meetings)
    sorted_tags = sorted(tag_total_seconds.items(), key=lambda x: x[1][0], reverse=True)
    top_tags = [
        {"slug": slug, "label": data[1], "minutes": max(1, round(data[0] / 60))}
        for slug, data in sorted_tags[:5]
        if data[0] > 0
    ]
    return {
        "total_meetings": len(meetings),
        "total_hours": round(total_duration / 3600, 1),
        "top_tags": top_tags,
    }


def format_display_text(raw_text: str, mode: str, override_text: str) -> str:
    override = (override_text or "").strip()
    if override:
        return override

    text = (raw_text or "").strip()
    if not text:
        return ""

    if mode == "compact":
        return re.sub(r"\s+", " ", text).strip()

    if mode == "sentences":
        return re.sub(r"\s*([.!?])\s+", r"\1\n", text).strip()

    return text


def normalize_person_name(name: str) -> str:
    return re.sub(r"\s+", " ", str(name or "").strip()).lower()


def merge_people_sources(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for group in groups:
        for person in group or []:
            person_id = str(person.get("id", "")).strip()
            person_name = str(person.get("name", "")).strip()
            if not person_id or not person_name:
                continue
            if person_id not in seen:
                seen[person_id] = {"id": person_id, "name": person_name}
    return sorted(seen.values(), key=lambda p: p["name"])


def add_custom_speakers_from_annotation(
    annotation: dict[str, Any],
    people: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged = [dict(p) for p in people]
    by_norm_name = {normalize_person_name(p["name"]): p["id"] for p in merged if p.get("name")}
    used_ids = {p["id"] for p in merged if p.get("id")}

    def upsert_name(name: str) -> None:
        clean = str(name or "").strip()
        if not clean:
            return
        norm = normalize_person_name(clean)
        if not norm or norm in by_norm_name:
            return

        base = f"speaker-{slugify(clean)}" or "speaker-unknown"
        next_id = base
        suffix = 2
        while next_id in used_ids:
            next_id = f"{base}-{suffix}"
            suffix += 1

        merged.append({"id": next_id, "name": clean})
        by_norm_name[norm] = next_id
        used_ids.add(next_id)

    for section in annotation.get("sections", []) or []:
        if not section.get("speaker_id"):
            upsert_name(section.get("speaker_name", ""))
        for line in section.get("lines", []) or []:
            if not line.get("speaker_id"):
                upsert_name(line.get("speaker_name", ""))

    return sorted(merged, key=lambda p: p["name"])


def args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build static meeting website")
    parser.add_argument("--config", default="config.yaml")
    return parser.parse_args()


def get_env(template_dir: Path) -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["clock"] = sec_to_clock
    env.filters["minutes"] = lambda s: f"{max(1, round(float(s or 0) / 60))} min"
    return env


def merge_sections(
    meeting: dict[str, Any],
    annotation: dict[str, Any],
    people_by_id: dict[str, dict[str, Any]],
    people_by_name: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    by_index = {
        int(section.get("chunk_index", -1)): section
        for section in annotation.get("sections", [])
    }
    merged: list[dict[str, Any]] = []
    for chunk in meeting.get("transcript", []):
        idx = int(chunk.get("chunk_index", -1))
        section = by_index.get(idx, {})
        mention_objs = [people_by_id[p] for p in section.get("mentions", []) if p in people_by_id]
        speaker_id = section.get("speaker_id", "")
        if not speaker_id and section.get("speaker_name"):
            person_match = people_by_name.get(normalize_person_name(section.get("speaker_name", "")), {})
            speaker_id = person_match.get("id", "")
        resolved_speaker = people_by_id.get(speaker_id, {}) if speaker_id else {}
        speaker_name = section.get("speaker_name", "") or resolved_speaker.get("name", "")

        # Resolve speaker names for each turn line; fall back to splitting raw text
        raw_lines = section.get("lines") or split_turns(chunk.get("text", ""))
        resolved_lines = []
        for line in raw_lines:
            lid = line.get("speaker_id", "")
            if not lid and line.get("speaker_name"):
                person_match = people_by_name.get(normalize_person_name(line.get("speaker_name", "")), {})
                lid = person_match.get("id", "")
            line_person = people_by_id.get(lid, {}) if lid else {}
            lname = line.get("speaker_name", "") or line_person.get("name", "")
            resolved_lines.append(
                {"text": line.get("text", ""), "speaker_id": lid, "speaker_name": lname}
            )

        # Build ordered unique speakers for display on the section header.
        speakers: list[dict[str, str]] = []
        seen_speakers: set[str] = set()
        for line in resolved_lines:
            lid = line.get("speaker_id", "")
            lname = line.get("speaker_name", "")
            key = lid or normalize_person_name(lname)
            if not key or key in seen_speakers or not lname:
                continue
            speakers.append({"id": lid, "name": lname})
            seen_speakers.add(key)
        if not speakers and speaker_name:
            speakers = [{"id": speaker_id, "name": speaker_name}]

        display_mode = section.get("display_mode", "raw")
        if resolved_lines:
            parts = [
                f"{line['speaker_name'] or chr(8212)}: {line['text'].strip()}"
                for line in resolved_lines
                if line["text"].strip()
            ]
            display_text = "\n".join(parts)
        else:
            display_text = format_display_text(
                chunk.get("text", ""),
                display_mode,
                section.get("display_text", ""),
            )
        votes = []
        for vote in section.get("votes", []):
            person_id = vote.get("person_id", "")
            person = people_by_id.get(person_id, {})
            votes.append(
                {
                    "motion": vote.get("motion", ""),
                    "person_id": person_id,
                    "person_name": person.get("name", person_id),
                    "vote": vote.get("vote", ""),
                }
            )
        merged.append(
            {
                "chunk_index": idx,
                "start": chunk.get("start", 0),
                "end": chunk.get("end", 0),
                "text": chunk.get("text", ""),
                "speaker_id": speaker_id,
                "speaker_name": speaker_name,
                "speakers": speakers,
                "lines": resolved_lines,
                "display_mode": display_mode,
                "display_text": display_text,
                "summary": section.get("summary", ""),
                "tags": [slugify(t) for t in section.get("tags", []) if t],
                "raw_tags": [t.strip() for t in section.get("tags", []) if t and t.strip()],
                "mentions": mention_objs,
                "roll_call": [
                    {
                        "person_id": rc.get("person_id", ""),
                        "person_name": people_by_id.get(rc.get("person_id", ""), {}).get("name", rc.get("person_name", rc.get("person_id", ""))),
                        "presence": rc.get("presence", ""),
                    }
                    for rc in section.get("roll_call", [])
                    if rc.get("person_id") or rc.get("person_name")
                ],
                "votes": votes,
                "notes": section.get("notes", ""),
            }
        )
    return merged


def group_consecutive_sections(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse consecutive sections with the same speaker into one display entry.

    All metadata from the first section is kept as the group header. Lines from
    subsequent sections are appended. Tags, mentions, roll_call, and votes are
    merged (tags/mentions deduped). The end timestamp extends to the last section.
    Sections without a speaker_id are never merged.
    """
    if not sections:
        return []

    grouped: list[dict[str, Any]] = []
    for section in sections:
        current_id = section.get("speaker_id", "")
        if (
            current_id
            and grouped
            and grouped[-1].get("speaker_id") == current_id
        ):
            prev = grouped[-1]
            prev["lines"].extend(section["lines"])
            prev["end"] = section["end"]
            # Merge summaries, skipping blanks
            existing_summary = prev.get("summary", "")
            new_summary = section.get("summary", "")
            if new_summary and new_summary != existing_summary:
                prev["summary"] = f"{existing_summary} {new_summary}".strip() if existing_summary else new_summary
            # Merge tags (preserve order, dedupe by slug)
            seen_tags = set(prev["tags"])
            for slug, label in zip(section["tags"], section["raw_tags"]):
                if slug not in seen_tags:
                    prev["tags"].append(slug)
                    prev["raw_tags"].append(label)
                    seen_tags.add(slug)
            # Merge mentions (dedupe by id)
            seen_mentions = {p["id"] for p in prev["mentions"]}
            for p in section["mentions"]:
                if p["id"] not in seen_mentions:
                    prev["mentions"].append(p)
                    seen_mentions.add(p["id"])
            # Merge speakers (dedupe by id, then name)
            seen_speakers = {sp.get("id") or normalize_person_name(sp.get("name", "")) for sp in prev.get("speakers", [])}
            for sp in section.get("speakers", []):
                key = sp.get("id") or normalize_person_name(sp.get("name", ""))
                if key and key not in seen_speakers:
                    prev.setdefault("speakers", []).append(sp)
                    seen_speakers.add(key)
            # Append roll_call and votes
            prev["roll_call"].extend(section["roll_call"])
            prev["votes"].extend(section["votes"])
        else:
            grouped.append(dict(section))

    return grouped


def merge_adjacent_speaking_turns(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge adjacent speaking entries into larger continuous turns.

    This reduces artificial split points from chunking (e.g. 2-minute transcript chunks)
    while preserving links to the first chunk where the turn starts.
    """
    if not turns:
        return []

    merged: list[dict[str, Any]] = []
    for turn in turns:
        current = dict(turn)
        current.setdefault("line_index", 0)
        current.setdefault("_last_chunk_index", int(current.get("chunk_index", 0)))
        current.setdefault("_last_line_index", int(current.get("line_index", 0)))

        if not merged:
            merged.append(current)
            continue

        prev = merged[-1]
        same_meeting = prev.get("meeting_id") == current.get("meeting_id")
        prev_chunk = int(prev.get("_last_chunk_index", prev.get("chunk_index", 0)))
        prev_line = int(prev.get("_last_line_index", 0))
        curr_chunk = int(current.get("chunk_index", 0))
        curr_line = int(current.get("line_index", 0))

        # Merge when the same person continues in immediately adjacent lines/chunks.
        is_continuation = same_meeting and (
            (curr_chunk == prev_chunk and curr_line == prev_line + 1)
            or (curr_chunk == prev_chunk + 1)
        )

        if is_continuation:
            prev_text = str(prev.get("text", "")).strip()
            curr_text = str(current.get("text", "")).strip()
            if curr_text:
                prev["text"] = f"{prev_text} {curr_text}".strip() if prev_text else curr_text
            prev["_last_chunk_index"] = curr_chunk
            prev["_last_line_index"] = curr_line
        else:
            merged.append(current)

    for item in merged:
        item.pop("_last_chunk_index", None)
        item.pop("_last_line_index", None)
        item.pop("line_index", None)
    return merged


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> None:
    parsed = args()
    root = Path(__file__).resolve().parent.parent
    cfg = yaml.safe_load((root / parsed.config).read_text(encoding="utf-8"))

    output_dir = root / cfg["site"].get("output_dir", "docs")
    template_dir = root / "site" / "templates"
    static_dir = root / "site" / "static"

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    shutil.copytree(static_dir, output_dir / "assets", dirs_exist_ok=True)

    env = get_env(template_dir)
    meeting_template = env.get_template("meeting.html")
    index_template = env.get_template("index.html")
    person_template = env.get_template("person.html")
    people_template = env.get_template("people.html")
    tag_template = env.get_template("tag.html")

    bodies = {body["id"]: body for body in cfg.get("bodies", [])}

    meetings: list[dict[str, Any]] = []
    people_mentions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    people_votes: dict[str, list[dict[str, Any]]] = defaultdict(list)
    people_speaking: dict[str, list[dict[str, Any]]] = defaultdict(list)
    tags_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
    people_tag_entries: dict[str, list[dict[str, Any]]] = defaultdict(list)
    tag_total_seconds: dict[str, tuple[float, str]] = {}
    all_people: dict[str, dict[str, Any]] = {}

    for meeting_path in sorted((root / "data" / "processed" / "meetings").glob("*.json")):
        meeting = load_json(meeting_path, {})
        if not meeting:
            continue

        annotation_path = root / "data" / "annotations" / "meetings" / f"{meeting['id']}.json"
        annotation = load_json(annotation_path, default={"sections": [], "global_tags": []})

        body = bodies.get(meeting["body_id"], {})
        people = merge_people_sources(
            body.get("councilpeople", []),
            meeting.get("councilpeople", []),
            annotation.get("councilpeople", []),
        )
        people = add_custom_speakers_from_annotation(annotation, people)
        people_by_id = {person["id"]: person for person in people}
        people_by_name = {normalize_person_name(person["name"]): person for person in people}
        all_people.update(people_by_id)

        sections = merge_sections(meeting, annotation, people_by_id, people_by_name)

        for section in sections:
            section_duration = max(0.0, float(section.get("end", 0)) - float(section.get("start", 0)))

            for label, slug in zip(section["raw_tags"], section["tags"]):
                tags_map[slug].append(
                    {
                        "label": label,
                        "meeting_id": meeting["id"],
                        "meeting_title": meeting["title"],
                        "start": section["start"],
                        "chunk_index": section["chunk_index"],
                        "summary": section["summary"],
                    }
                )
                prev_secs, _ = tag_total_seconds.get(slug, (0.0, label))
                tag_total_seconds[slug] = (prev_secs + section_duration, label)

            for person in section["mentions"]:
                people_mentions[person["id"]].append(
                    {
                        "meeting_id": meeting["id"],
                        "meeting_title": meeting["title"],
                        "start": section["start"],
                        "chunk_index": section["chunk_index"],
                        "summary": section["summary"],
                        "meeting_date": meeting["date"],
                    }
                )
                for label, slug in zip(section["raw_tags"], section["tags"]):
                    people_tag_entries[person["id"]].append(
                        {
                            "slug": slug,
                            "label": label,
                            "seconds": section_duration,
                            "meeting_date": meeting["date"],
                            "meeting_id": meeting["id"],
                        }
                    )

            for line_index, line in enumerate(section.get("lines", [])):
                pid = line.get("speaker_id", "")
                if not pid:
                    continue
                people_speaking[pid].append(
                    {
                        "meeting_id": meeting["id"],
                        "meeting_title": meeting["title"],
                        "start": section["start"],
                        "chunk_index": section["chunk_index"],
                        "line_index": line_index,
                        "text": line.get("text", ""),
                        "meeting_date": meeting["date"],
                    }
                )

            for vote in section["votes"]:
                pid = vote.get("person_id")
                if not pid:
                    continue
                people_votes[pid].append(
                    {
                        "meeting_id": meeting["id"],
                        "meeting_title": meeting["title"],
                        "motion": vote.get("motion", ""),
                        "vote": vote.get("vote", ""),
                        "start": section["start"],
                        "chunk_index": section["chunk_index"],
                        "meeting_date": meeting["date"],
                    }
                )

        # Aggregate roll call entries across all sections (first occurrence per person wins)
        roll_call_by_person: dict[str, dict] = {}
        for section in sections:
            for entry in section.get("roll_call", []):
                pid = entry.get("person_id") or entry.get("person_name", "")
                if pid and pid not in roll_call_by_person:
                    roll_call_by_person[pid] = entry
        meeting_roll_call = list(roll_call_by_person.values())

        meeting_record = {
            "id": meeting["id"],
            "title": meeting["title"],
            "date": meeting["date"],
            "duration": meeting.get("duration"),
            "body_name": meeting.get("body_name", body.get("name", "")),
            "youtube_url": meeting["youtube_url"],
            "summary": annotation.get("meeting_summary", ""),
            "sections": group_consecutive_sections(sections),
            "roll_call": meeting_roll_call,
            "global_tags": [slugify(tag) for tag in annotation.get("global_tags", []) if tag],
            "global_tag_labels": [tag.strip() for tag in annotation.get("global_tags", []) if tag and tag.strip()],
            "stats": compute_meeting_stats(sections),
        }
        meetings.append(meeting_record)

        html = meeting_template.render(site=cfg["site"], meeting=meeting_record)
        write(output_dir / "meetings" / f"{meeting['id']}.html", html)

    cutoff_date = (date.today() - timedelta(days=365)).isoformat()
    people_records: list[dict[str, Any]] = []
    for person in sorted(all_people.values(), key=lambda x: x["name"]):
        mentions = sorted(people_mentions.get(person["id"], []), key=lambda x: (x["meeting_id"], x["start"]))
        votes = sorted(people_votes.get(person["id"], []), key=lambda x: (x["meeting_id"], x["start"]))
        speaking_turns_raw = sorted(
            people_speaking.get(person["id"], []),
            key=lambda x: (x["meeting_id"], x["chunk_index"], x.get("line_index", 0), x["start"]),
        )
        speaking_turns = merge_adjacent_speaking_turns(speaking_turns_raw)
        person_stats = compute_person_stats(
            people_tag_entries.get(person["id"], []),
            people_votes.get(person["id"], []),
            cutoff_date,
        )
        person_html = person_template.render(
            site=cfg["site"],
            person=person,
            mentions=mentions,
            votes=votes,
            speaking_turns=speaking_turns,
            stats=person_stats,
        )
        write(output_dir / "people" / f"{person['id']}.html", person_html)
        people_records.append(
            {
                "id": person["id"],
                "name": person["name"],
                "district": person.get("district", ""),
                "mention_count": len(mentions),
                "vote_count": len(votes),
                "speaking_count": len(speaking_turns),
            }
        )

    for tag_slug, entries in sorted(tags_map.items()):
        if not entries:
            continue
        tag_label = entries[0]["label"]
        tag_html = tag_template.render(
            site=cfg["site"],
            tag_slug=tag_slug,
            tag_label=tag_label,
            entries=sorted(entries, key=lambda x: (x["meeting_id"], x["start"])),
        )
        write(output_dir / "tags" / f"{tag_slug}.html", tag_html)

    sorted_meetings = sorted(meetings, key=lambda x: x["date"], reverse=True)
    site_stats = compute_site_stats(sorted_meetings, tag_total_seconds)
    sorted_people = sorted(people_records, key=lambda x: x["name"])
    index_html = index_template.render(
        site=cfg["site"],
        meetings=sorted_meetings,
        tags=sorted(tags_map.keys()),
        stats=site_stats,
        people=sorted_people,
    )
    write(output_dir / "index.html", index_html)

    people_html = people_template.render(site=cfg["site"], people=sorted_people)
    write(output_dir / "people" / "index.html", people_html)

    print(f"Built static site in {output_dir.relative_to(root)}")


if __name__ == "__main__":
    main()
