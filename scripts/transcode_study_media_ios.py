#!/usr/bin/env python3
"""Audit/transcode ViewTube study MP4s to iOS-safe H.264/AAC.

Default mode is a dry run. Use --apply to write converted files and replace the
originals after successful conversion. Originals are backed up before replace.
"""
from __future__ import annotations

import argparse
import datetime as dt
import shutil
import subprocess
import sys
from pathlib import Path

CONTAINER_BOXES = {"moov", "trak", "mdia", "minf", "stbl"}
IOS_VIDEO_CODECS = {"avc1"}
IOS_AUDIO_CODECS = {"mp4a"}


def mp4_codecs(path: Path) -> list[str]:
    data = memoryview(path.read_bytes())
    codecs: list[str] = []

    def walk(start: int, end: int) -> None:
        pos = start
        while pos + 8 <= end:
            size = int.from_bytes(data[pos : pos + 4], "big")
            typ = bytes(data[pos + 4 : pos + 8]).decode("latin1")
            header = 8
            if size == 1:
                if pos + 16 > end:
                    break
                size = int.from_bytes(data[pos + 8 : pos + 16], "big")
                header = 16
            elif size == 0:
                size = end - pos
            if size < header or pos + size > end:
                break
            content = pos + header
            if typ in CONTAINER_BOXES:
                walk(content, pos + size)
            elif typ == "stsd" and content + 8 <= pos + size:
                entry_count = int.from_bytes(data[content + 4 : content + 8], "big")
                entry_pos = content + 8
                for _ in range(entry_count):
                    if entry_pos + 8 > pos + size:
                        break
                    entry_size = int.from_bytes(data[entry_pos : entry_pos + 4], "big")
                    entry_type = bytes(data[entry_pos + 4 : entry_pos + 8]).decode("latin1")
                    codecs.append(entry_type)
                    entry_pos += entry_size if entry_size else 8
            pos += size

    walk(0, len(data))
    return codecs


def is_ios_safe(codecs: list[str]) -> bool:
    has_video = any(codec in IOS_VIDEO_CODECS for codec in codecs)
    audio_codecs = [codec for codec in codecs if codec not in IOS_VIDEO_CODECS]
    has_only_ios_audio = all(codec in IOS_AUDIO_CODECS for codec in audio_codecs) if audio_codecs else True
    return has_video and has_only_ios_audio


def ffmpeg_executable() -> str:
    try:
        import imageio_ffmpeg  # type: ignore
    except ImportError:
        print("ERROR: Missing imageio-ffmpeg. Install it in the venv with:", file=sys.stderr)
        print("  python -m pip install imageio-ffmpeg", file=sys.stderr)
        raise SystemExit(1)
    return imageio_ffmpeg.get_ffmpeg_exe()


def transcode(ffmpeg: str, source: Path, target: Path, *, fast_ios: bool = False, loglevel: str = "error") -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        loglevel,
    ]
    if fast_ios:
        cmd.extend(["-err_detect", "ignore_err", "-fflags", "+discardcorrupt"])
    cmd.extend([
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
    ])
    if fast_ios:
        cmd.extend([
            "-vf",
            "scale='min(720,iw)':-2",
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "24",
            "-profile:v",
            "baseline",
            "-level",
            "3.1",
        ])
    else:
        cmd.extend([
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "22",
            "-profile:v",
            "main",
            "-level",
            "4.0",
        ])
    cmd.extend([
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(target),
    ])
    subprocess.run(cmd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--media-root", default="study_media", type=Path)
    parser.add_argument("--folders", nargs="+", default=["control", "treatment"], help="Folders under media-root to audit/transcode.")
    parser.add_argument("--apply", action="store_true", help="Actually transcode and replace files. Without this, only audit.")
    parser.add_argument("--force", action="store_true", help="Transcode even files already detected as iOS-safe.")
    parser.add_argument("--backup-dir", type=Path, default=None, help="Backup location. Defaults to study_media/.ios-backup-<timestamp>.")
    parser.add_argument("--fast-ios", action="store_true", help="Use faster iPhone-safe settings: discard corrupt packets, max 720px width, 30fps, H.264 baseline, ultrafast preset, CRF 24.")
    parser.add_argument("--ffmpeg-loglevel", default="error", choices=["quiet", "panic", "fatal", "error", "warning", "info", "verbose"], help="ffmpeg log level. Use info to see progress details.")
    args = parser.parse_args()

    media_root = args.media_root.resolve()
    paths: list[Path] = []
    for folder in args.folders:
      folder_path = (media_root / folder).resolve()
      if not folder_path.is_dir():
          print(f"ERROR: Missing media folder: {folder_path}", file=sys.stderr)
          return 1
      paths.extend(sorted(folder_path.glob("*.mp4")))

    rows: list[tuple[Path, list[str], bool]] = []
    for path in paths:
        codecs = mp4_codecs(path)
        rows.append((path, codecs, is_ios_safe(codecs)))

    unsafe = [(path, codecs) for path, codecs, safe in rows if not safe]
    print(f"Audited {len(rows)} MP4 files under {media_root}")
    print(f"iOS-safe H.264/AAC files: {len(rows) - len(unsafe)}")
    print(f"Needs transcode: {len(unsafe)}")
    for path, codecs in unsafe[:25]:
        print(f"  {path.relative_to(media_root)}: {','.join(codecs) or 'unknown'}")
    if len(unsafe) > 25:
        print(f"  ... plus {len(unsafe) - 25} more")

    targets = paths if args.force else [path for path, _codecs in unsafe]
    if not args.apply:
        print("Dry run only. Re-run with --apply to transcode/replace files.")
        return 0 if not unsafe else 2

    if not targets:
        print("Nothing to transcode.")
        return 0

    backup_dir = args.backup_dir or (media_root / f".ios-backup-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}")
    backup_dir = backup_dir.resolve()
    tmp_dir = media_root / ".ios-transcode-tmp"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True)

    ffmpeg = ffmpeg_executable()
    print(f"Using ffmpeg: {ffmpeg}")
    print(f"Backing up originals to: {backup_dir}")
    if args.fast_ios:
        print("Using fast iOS mode: max 720px width, 30fps, H.264 baseline, ultrafast CRF 24, AAC audio.")

    converted: list[tuple[Path, Path, Path]] = []
    try:
        for index, source in enumerate(targets, start=1):
            rel = source.relative_to(media_root)
            tmp_target = tmp_dir / rel
            backup_target = backup_dir / rel
            print(f"[{index}/{len(targets)}] Transcoding {rel}")
            transcode(ffmpeg, source, tmp_target, fast_ios=args.fast_ios, loglevel=args.ffmpeg_loglevel)
            new_codecs = mp4_codecs(tmp_target)
            if not is_ios_safe(new_codecs):
                raise RuntimeError(f"Transcoded file is still not iOS-safe: {rel} codecs={new_codecs}")
            backup_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, backup_target)
            converted.append((source, tmp_target, backup_target))

        for source, tmp_target, _backup_target in converted:
            shutil.move(str(tmp_target), str(source))
        print(f"Replaced {len(converted)} MP4 files with iOS-safe H.264/AAC versions.")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # Final audit should pass.
    remaining_unsafe = []
    for path in paths:
        codecs = mp4_codecs(path)
        if not is_ios_safe(codecs):
            remaining_unsafe.append((path, codecs))
    if remaining_unsafe:
        print("ERROR: Some files are still not iOS-safe:", file=sys.stderr)
        for path, codecs in remaining_unsafe[:20]:
            print(f"  {path.relative_to(media_root)}: {','.join(codecs)}", file=sys.stderr)
        return 1
    print("Final audit passed: all selected files are H.264/AAC-compatible for iOS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
