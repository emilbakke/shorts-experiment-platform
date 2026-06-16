#!/usr/bin/env python3
"""Build deterministic local Shorts study sequences from study_media.

Expected production layout:
  study_media/control/*.mp4
  study_media/treatment/*.mp4  (rebuilt by this script)
  study_media/manosphere/manosphere_overview.xlsx
  study_media/manosphere/*.mp4

The script first prepares `study_media/control` as a deterministic short-first
sequence that avoids showing the same creator twice in a row. It then clones
that prepared control folder to `study_media/treatment` as a baseline. When all
manosphere files are available, the treatment sequence keeps the same length and
replaces every fourth control position with a manosphere video. Manosphere
exposures are ordered with Kisoan first, Casper Krause second, and then spread
across remaining creators to avoid creator clumping while preserving a seeded
audit trail and the no-adjacent-creator rule.
"""
from __future__ import annotations

import argparse
import csv
import random
import re
import shutil
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = REPO_ROOT / "study_media"
CONTROL_METADATA_CSV = DEFAULT_ROOT / "regular" / "danish_balanced_shorts_with_duration.csv"
SEQUENCED_FILENAME_RE = re.compile(r"^\d{3}_(?P<video_id>.+)$")


@dataclass(frozen=True)
class Clip:
    video_id: str
    filename: str
    source_path: Path
    title: str
    channel: str
    duration_sec: float
    source_group: str


def _read_atom_header(handle: BinaryIO) -> tuple[int, bytes] | None:
    header = handle.read(8)
    if len(header) < 8:
        return None
    size, atom_type = struct.unpack(">I4s", header)
    if size == 1:
        large = handle.read(8)
        if len(large) < 8:
            return None
        size = struct.unpack(">Q", large)[0]
    return size, atom_type


def _find_atom(handle: BinaryIO, end: int, target: bytes) -> tuple[int, int] | None:
    while handle.tell() < end:
        start = handle.tell()
        parsed = _read_atom_header(handle)
        if parsed is None:
            return None
        size, atom_type = parsed
        header_size = 16 if size == 1 else 8
        if size < header_size:
            return None
        if atom_type == target:
            return start + header_size, start + size
        handle.seek(start + size)
    return None


def mp4_duration_seconds(path: Path) -> float:
    try:
        with path.open("rb") as handle:
            file_size = path.stat().st_size
            moov = _find_atom(handle, file_size, b"moov")
            if moov is None:
                return 0.0
            moov_start, moov_end = moov
            handle.seek(moov_start)
            mvhd = _find_atom(handle, moov_end, b"mvhd")
            if mvhd is None:
                return 0.0
            mvhd_start, _ = mvhd
            handle.seek(mvhd_start)
            version = handle.read(1)
            handle.read(3)
            if version == b"\x01":
                handle.read(16)
                timescale = struct.unpack(">I", handle.read(4))[0]
                duration = struct.unpack(">Q", handle.read(8))[0]
            else:
                handle.read(8)
                timescale = struct.unpack(">I", handle.read(4))[0]
                duration = struct.unpack(">I", handle.read(4))[0]
            return float(duration) / float(timescale) if timescale else 0.0
    except OSError:
        return 0.0


def clean_title(row: dict[str, str], fallback: str) -> str:
    return (row.get("cleaned_title") or row.get("metadata_title") or row.get("watched_title") or fallback).strip()


def original_video_id(path: Path) -> str:
    match = SEQUENCED_FILENAME_RE.match(path.stem)
    return match.group("video_id") if match else path.stem


def media_sort_key(path: Path) -> tuple[int, str]:
    prefix = path.stem.split("_", 1)[0]
    if prefix.isdigit():
        return (int(prefix), path.name)
    return (10_000, path.name)


def creator_key(clip: Clip) -> str:
    return " ".join((clip.channel or "unknown").strip().casefold().split())


def is_kisoan(clip: Clip) -> bool:
    return "kisoan" in creator_key(clip)


def is_casper_krause(clip: Clip) -> bool:
    key = creator_key(clip)
    return "casper" in key and "krause" in key


def participant_manosphere_title(channel: str, raw_title: str, fallback: str) -> str:
    title = raw_title.strip()
    if title and title.lower() != "nan":
        return title
    if "brian mørk" in " ".join(channel.strip().casefold().split()):
        return " "
    return fallback


def read_control_metadata(path: Path) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    if not path.exists():
        return rows
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            video_id = (row.get("video_id") or "").strip()
            if video_id:
                rows[video_id] = row
    return rows


def duration_from_row(row: dict[str, str], fallback_path: Path) -> float:
    for key in ("duration_sec", "duration_raw"):
        try:
            value = float(row.get(key) or 0)
            if value > 0:
                return value
        except ValueError:
            pass
    return mp4_duration_seconds(fallback_path)


def load_control_clips(study_root: Path) -> list[Clip]:
    control_dir = study_root / "control"
    metadata = read_control_metadata(CONTROL_METADATA_CSV)
    clips: list[Clip] = []
    for path in sorted(control_dir.glob("*.mp4"), key=media_sort_key):
        video_id = original_video_id(path)
        row = metadata.get(video_id, {})
        clips.append(
            Clip(
                video_id=video_id,
                filename=path.name,
                source_path=path,
                title=clean_title(row, video_id),
                channel=(row.get("channel") or row.get("uploader") or "Kontrolvideo").strip(),
                duration_sec=duration_from_row(row, path),
                source_group="control",
            )
        )
    return clips


def load_manosphere_clips(study_root: Path) -> list[Clip]:
    overview = pd.read_excel(study_root / "manosphere" / "manosphere_overview.xlsx")
    clips: list[Clip] = []
    missing_files: list[Path] = []
    for _, row in overview.iterrows():
        note = str(row.get("note", "")).strip().upper()
        if note == "SKIP":
            continue
        raw_filename = str(row.get("filename", "")).strip()
        if not raw_filename or raw_filename.lower() == "nan":
            continue
        filename = raw_filename if raw_filename.lower().endswith(".mp4") else f"{raw_filename}.mp4"
        path = study_root / "manosphere" / filename
        if not path.exists():
            missing_files.append(path)
            continue
        channel = str(row.get("Channel", "")).strip()
        title = str(row.get("title", "")).strip()
        clips.append(
            Clip(
                video_id=path.stem,
                filename=path.name,
                source_path=path,
                title=participant_manosphere_title(channel, title, path.stem),
                channel=channel if channel and channel.lower() != "nan" else "Manosphere",
                duration_sec=mp4_duration_seconds(path),
                source_group="manosphere",
            )
        )
    if missing_files:
        missing_list = "\n".join(f"- {path}" for path in missing_files)
        raise FileNotFoundError(
            "The manosphere overview lists non-SKIP videos that are missing on disk:\n"
            f"{missing_list}\n"
            "Either add the missing file(s) or mark those overview rows as SKIP before rebuilding the study sequence."
        )
    return clips


def has_adjacent_creator_repeat(clips: list[Clip]) -> bool:
    return any(creator_key(previous) == creator_key(current) for previous, current in zip(clips, clips[1:], strict=False))


def short_first_no_adjacent_order(clips: list[Clip], seed: int) -> list[Clip]:
    """Return a deterministic short-first order without adjacent creator repeats."""
    if not clips:
        return []

    counts: dict[str, int] = {}
    for clip in clips:
        counts[creator_key(clip)] = counts.get(creator_key(clip), 0) + 1
    if max(counts.values()) > (len(clips) + 1) // 2:
        raise SystemExit("Cannot avoid adjacent creator repeats: one creator appears too often in control.")

    rng = random.Random(seed)
    remaining = sorted(clips, key=lambda clip: (clip.duration_sec, creator_key(clip), clip.video_id))
    ordered: list[Clip] = []
    while remaining:
        previous_creator = creator_key(ordered[-1]) if ordered else None
        viable = [clip for clip in remaining if creator_key(clip) != previous_creator]
        if not viable:
            raise SystemExit(f"Cannot avoid adjacent creator repeat after {len(ordered)} control slots.")
        shortest_duration = min(clip.duration_sec for clip in viable)
        short_band = [clip for clip in viable if clip.duration_sec <= shortest_duration + 3]
        chosen = rng.choice(short_band)
        ordered.append(chosen)
        remaining.remove(chosen)

    if has_adjacent_creator_repeat(ordered):
        raise SystemExit("Prepared control order still has adjacent creator repeats.")
    return ordered


def safe_sequence_name(order: int, clip: Clip) -> str:
    return f"{order:03d}_{clip.video_id}.mp4"


def rewrite_folder(folder: Path, ordered_clips: list[Clip]) -> None:
    tmp_dir = folder.parent / f".{folder.name}_reorder_tmp"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True)
    try:
        for order, clip in enumerate(ordered_clips, start=1):
            shutil.copy2(clip.source_path, tmp_dir / safe_sequence_name(order, clip))
        for path in folder.glob("*.mp4"):
            path.unlink()
        for path in sorted(tmp_dir.glob("*.mp4"), key=media_sort_key):
            shutil.move(path.as_posix(), folder / path.name)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def clone_control_to_treatment(study_root: Path) -> None:
    control_dir = study_root / "control"
    treatment_dir = study_root / "treatment"
    treatment_dir.mkdir(parents=True, exist_ok=True)
    for path in treatment_dir.glob("*.mp4"):
        path.unlink()
    for path in sorted(control_dir.glob("*.mp4"), key=media_sort_key):
        shutil.copy2(path, treatment_dir / path.name)


def prepare_study_folders(seed: int, study_root: Path) -> list[Clip]:
    control = load_control_clips(study_root)
    if not control:
        raise SystemExit("No control MP4 files found in study_media/control")
    ordered_control = short_first_no_adjacent_order(control, seed)
    rewrite_folder(study_root / "control", ordered_control)
    clone_control_to_treatment(study_root)
    return load_control_clips(study_root)


def write_manifest(rows: list[dict[str, object]], path: Path) -> None:
    fields = [
        "arm",
        "order",
        "video_id",
        "filename",
        "source_path",
        "served_path",
        "title",
        "channel",
        "duration_sec",
        "content_pool",
        "is_manosphere",
        "replaced_video_id",
        "replacement_candidate_ids",
        "replacement_candidate_durations",
        "target_order",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def rebuild_treatment_folder(study_root: Path, treatment_rows: list[dict[str, object]]) -> None:
    treatment_dir = study_root / "treatment"
    treatment_dir.mkdir(parents=True, exist_ok=True)
    for path in treatment_dir.glob("*.mp4"):
        path.unlink()
    for row in treatment_rows:
        shutil.copy2(Path(str(row["source_path"])), study_root / str(row["served_path"]))


def neighbor_creators_for_slot(control: list[Clip], order: int) -> set[str]:
    creators: set[str] = set()
    for neighbor_order in (order - 1, order + 1):
        if 1 <= neighbor_order <= len(control):
            creators.add(creator_key(control[neighbor_order - 1]))
    return creators


def pop_shortest_matching(pool: list[Clip], predicate) -> Clip:
    matches = [clip for clip in pool if predicate(clip)]
    if not matches:
        raise SystemExit("Required manosphere ordering anchor is missing.")
    chosen = min(matches, key=lambda clip: (clip.duration_sec, creator_key(clip), clip.video_id))
    pool.remove(chosen)
    return chosen


def order_manosphere_clips(clips: list[Clip], seed: int) -> list[Clip]:
    """Order manosphere exposure slots with Kisoan first, Casper second, then creators spread out."""
    if len(clips) < 2:
        return clips

    remaining = sorted(clips, key=lambda clip: (clip.duration_sec, creator_key(clip), clip.video_id))
    ordered = [
        pop_shortest_matching(remaining, is_kisoan),
        pop_shortest_matching(remaining, is_casper_krause),
    ]
    rng = random.Random(seed)

    while remaining:
        previous_creator = creator_key(ordered[-1])
        viable = [clip for clip in remaining if creator_key(clip) != previous_creator]
        if not viable:
            raise SystemExit("Cannot spread manosphere creators without adjacent repeats.")

        creator_counts: dict[str, int] = {}
        for clip in remaining:
            creator_counts[creator_key(clip)] = creator_counts.get(creator_key(clip), 0) + 1

        # Keep overrepresented creators such as Casper Krause spread through the
        # sequence, while still preferring shorter clips early in the study.
        max_count = max(creator_counts[creator_key(clip)] for clip in viable)
        heavy_creator_band = [clip for clip in viable if creator_counts[creator_key(clip)] == max_count]
        shortest_duration = min(clip.duration_sec for clip in heavy_creator_band)
        short_band = [clip for clip in heavy_creator_band if clip.duration_sec <= shortest_duration + 8]
        chosen = rng.choice(short_band)
        ordered.append(chosen)
        remaining.remove(chosen)

    if has_adjacent_creator_repeat(ordered):
        raise SystemExit("Manosphere order still has adjacent creator repeats.")
    return ordered


def take_ordered_manosphere_for_slot(ordered_pool: list[Clip], control: list[Clip], slot_order: int, previous_manosphere: Clip | None) -> Clip:
    neighbor_creators = neighbor_creators_for_slot(control, slot_order)
    previous_creator = creator_key(previous_manosphere) if previous_manosphere else None
    for index, clip in enumerate(ordered_pool):
        if creator_key(clip) in neighbor_creators:
            continue
        if previous_creator and creator_key(clip) == previous_creator:
            continue
        return ordered_pool.pop(index)
    raise SystemExit(f"No valid ordered manosphere clip avoids creator conflicts for replacement slot {slot_order}")


def build_sequences(seed: int, study_root: Path) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    control = load_control_clips(study_root)
    if not control:
        raise SystemExit("No control MP4 files found in study_media/control")
    if has_adjacent_creator_repeat(control):
        raise SystemExit("Control order has adjacent creator repeats. Run the script again to prepare folders.")

    manosphere = order_manosphere_clips(load_manosphere_clips(study_root), seed)
    if len(control) % 4 != 0:
        raise SystemExit(f"Control count must be divisible by 4 for every-fourth treatment injection; found {len(control)}")
    needed = len(control) // 4
    if len(manosphere) != needed:
        raise SystemExit(f"Need exactly {needed} non-SKIP manosphere videos for {len(control)} controls; found {len(manosphere)}")

    manifest_rows: list[dict[str, object]] = []
    for order, clip in enumerate(control, start=1):
        manifest_rows.append(
            {
                "arm": "control",
                "order": order,
                "video_id": clip.video_id,
                "filename": clip.filename,
                "source_path": clip.source_path.as_posix(),
                "served_path": f"control/{clip.filename}",
                "title": clip.title,
                "channel": clip.channel,
                "duration_sec": round(clip.duration_sec, 3),
                "content_pool": "safe",
                "is_manosphere": False,
                "replaced_video_id": "",
                "replacement_candidate_ids": "",
                "replacement_candidate_durations": "",
                "target_order": "",
            }
        )

    replacement_slots = [order for order in range(4, len(control) + 1, 4)]
    ordered_manosphere_pool = manosphere.copy()
    replacements_by_order: dict[int, dict[str, object]] = {}
    audit_rows: list[dict[str, object]] = []
    previous_manosphere: Clip | None = None

    for slot_order in replacement_slots:
        original = control[slot_order - 1]
        chosen_manosphere = take_ordered_manosphere_for_slot(ordered_manosphere_pool, control, slot_order, previous_manosphere)
        valid_pool = [candidate for candidate in [chosen_manosphere, *ordered_manosphere_pool] if creator_key(candidate) not in neighbor_creators_for_slot(control, slot_order)]
        closest_others = [
            candidate
            for candidate in sorted(valid_pool, key=lambda candidate: (abs(candidate.duration_sec - original.duration_sec), candidate.video_id))
            if candidate.video_id != chosen_manosphere.video_id
        ][:2]
        candidates = [chosen_manosphere, *closest_others]
        if not candidates:
            raise SystemExit(f"No valid manosphere clip avoids adjacent creator repeats for replacement slot {slot_order}")
        previous_manosphere = chosen_manosphere
        replacements_by_order[slot_order] = {
            "clip": chosen_manosphere,
            "replacement": original,
            "candidate_ids": ";".join(candidate.video_id for candidate in candidates),
            "candidate_durations": ";".join(f"{candidate.duration_sec:.3f}" for candidate in candidates),
        }

    treatment_rows: list[dict[str, object]] = []
    treatment_clips: list[Clip] = []
    for order, original in enumerate(control, start=1):
        replacement = ""
        candidate_ids = ""
        candidate_durations = ""
        if order in replacements_by_order:
            replacement_plan = replacements_by_order[order]
            clip = replacement_plan["clip"]
            chosen = replacement_plan["replacement"]
            assert isinstance(clip, Clip)
            assert isinstance(chosen, Clip)
            replacement = chosen.video_id
            candidate_ids = str(replacement_plan["candidate_ids"])
            candidate_durations = str(replacement_plan["candidate_durations"])
            content_pool = "problematic"
            is_manosphere = True
        else:
            clip = original
            content_pool = "safe"
            is_manosphere = False
        treatment_clips.append(clip)
        served_filename = safe_sequence_name(order, clip)
        row = {
            "arm": "treatment",
            "order": order,
            "video_id": clip.video_id,
            "filename": clip.filename,
            "source_path": clip.source_path.as_posix(),
            "served_path": f"treatment/{served_filename}",
            "title": clip.title,
            "channel": clip.channel,
            "duration_sec": round(clip.duration_sec, 3),
            "content_pool": content_pool,
            "is_manosphere": is_manosphere,
            "replaced_video_id": replacement,
            "replacement_candidate_ids": candidate_ids,
            "replacement_candidate_durations": candidate_durations,
            "target_order": order if is_manosphere else "",
        }
        manifest_rows.append(row)
        treatment_rows.append(row)
        if is_manosphere:
            audit_rows.append(row.copy())

    if has_adjacent_creator_repeat(treatment_clips):
        raise SystemExit("Treatment order has adjacent creator repeats after manosphere placement.")
    return manifest_rows, audit_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Build control/treatment local study sequence manifest.")
    parser.add_argument("--seed", type=int, default=20260507)
    parser.add_argument("--study-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--prepare-folders-only", action="store_true", help="Rewrite control order and clone it to treatment without reading manosphere files.")
    args = parser.parse_args()

    prepared_control = prepare_study_folders(args.seed, args.study_root)
    print(f"Prepared control rows: {len(prepared_control)}")
    print(f"Copied prepared control folder to {args.study_root / 'treatment'}")
    if args.prepare_folders_only:
        return

    manifest_rows, audit_rows = build_sequences(args.seed, args.study_root)
    write_manifest(manifest_rows, args.study_root / "sequence_manifest.csv")
    write_manifest(audit_rows, args.study_root / "replacement_audit.csv")
    rebuild_treatment_folder(args.study_root, [row for row in manifest_rows if row["arm"] == "treatment"])

    treatment_manosphere = [row for row in manifest_rows if row["arm"] == "treatment" and row["is_manosphere"]]
    print(f"Wrote {args.study_root / 'sequence_manifest.csv'}")
    print(f"Wrote {args.study_root / 'replacement_audit.csv'}")
    print(f"Control rows: {sum(1 for row in manifest_rows if row['arm'] == 'control')}")
    print(f"Treatment rows: {sum(1 for row in manifest_rows if row['arm'] == 'treatment')}")
    print(f"Treatment manosphere rows: {len(treatment_manosphere)}")
    print("Treatment manosphere positions:", ",".join(str(row["order"]) for row in treatment_manosphere))


if __name__ == "__main__":
    main()
