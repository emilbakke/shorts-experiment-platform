#!/usr/bin/env python3
"""Idempotently ingest real YouTube videos into the platform database.

Run from the repository root:

    PYTHONPATH=.python_deps:. API_KEY_YOUTUBE=... python3 scripts/ingest_youtube.py

Defaults are tuned for this experiment's Danish participant population: searches
use ``regionCode=DK`` and ``relevanceLanguage=da`` with many Danish-language
queries plus Danish-popular global topics. The script paginates through YouTube
search results in a round-robin way until each query is exhausted or the global
candidate cap is reached. Existing rows are matched by ``youtube_id`` and
updated in place; no videos are deleted.
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import math
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app import models  # noqa: E402
from backend.app.database import Base, ContentSessionLocal, content_engine  # noqa: E402
from backend.app.schema_compat import ensure_experimental_schema  # noqa: E402


YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
YOUTUBE_CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
YOUTUBE_PLAYLIST_ITEMS_URL = "https://www.googleapis.com/youtube/v3/playlistItems"
DEFAULT_MAX_DURATION_SECONDS = 7_200  # 2 hours; avoids very long streams while keeping Danish podcasts/news.
SHORT_MAX_SECONDS = 60
MEDIUM_SHORT_MAX_SECONDS = 180
MEDIUM_SHORT_PUBLISHED_AFTER = datetime(2024, 10, 15, tzinfo=timezone.utc)
DETAILS_CHUNK_SIZE = 50


@dataclass(frozen=True)
class TopicSpec:
    query: str
    topic: str
    content_pool: str = "safe"
    order: str = "relevance"
    prefer_short: bool = False
    creator_slug: str | None = None
    channel_id: str | None = None
    ingest_source_type: str = "search_discovery"
    ingest_query: str | None = None
    review_group: str | None = None


@dataclass(frozen=True)
class CreatorSource:
    slug: str
    display_name_internal: str
    channel_ids: tuple[str, ...]
    handles: tuple[str, ...]
    query_aliases: tuple[str, ...]
    review_group: str
    default_content_pool: str
    topic: str
    priority: str = "medium"
    manual_review_required: bool = False


# The default set intentionally avoids broad US-centric queries like "sports"
# and uses Danish terms/channels/events where possible. YouTube still chooses
# the final ranking, but regionCode=DK + relevanceLanguage=da + these queries
# gives a corpus much closer to what Danish users normally see.
DK_SAFE_TOPICS: tuple[TopicSpec, ...] = (
    TopicSpec("danske nyheder i dag", "nyheder", "safe", "date"),
    TopicSpec("TV 2 News Danmark", "nyheder", "safe", "date"),
    TopicSpec("DR Nyheder dansk", "nyheder", "safe", "date"),
    TopicSpec("dansk politik forklaret", "politik", "safe", "relevance"),
    TopicSpec("Folketinget debat Danmark", "politik", "safe", "date"),
    TopicSpec("København vlog dansk", "livsstil", "safe", "relevance"),
    TopicSpec("dansk vlog hverdag", "livsstil", "safe", "relevance"),
    TopicSpec("dansk comedy standup", "underholdning", "safe", "viewCount"),
    TopicSpec("dansk podcast klip", "podcast", "safe", "viewCount"),
    TopicSpec("dansk musik 2026", "musik", "safe", "date"),
    TopicSpec("dansk musik video", "musik", "safe", "viewCount"),
    TopicSpec("MGP dansk musik", "musik", "safe", "viewCount"),
    TopicSpec("Superliga highlights dansk", "fodbold", "safe", "date"),
    TopicSpec("Danmark fodbold highlights", "fodbold", "safe", "date"),
    TopicSpec("håndbold Danmark highlights", "håndbold", "safe", "date"),
    TopicSpec("Tour de France dansk", "cykling", "safe", "date"),
    TopicSpec("dansk gaming", "gaming", "safe", "viewCount"),
    TopicSpec("Minecraft dansk", "gaming", "safe", "viewCount"),
    TopicSpec("Fortnite dansk", "gaming", "safe", "viewCount"),
    TopicSpec("dansk mad opskrift", "mad", "safe", "viewCount"),
    TopicSpec("aftensmad opskrift dansk", "mad", "safe", "relevance"),
    TopicSpec("boligindretning dansk", "bolig", "safe", "relevance"),
    TopicSpec("renovering hus dansk", "bolig", "safe", "relevance"),
    TopicSpec("træning dansk begynder", "fitness", "safe", "relevance"),
    TopicSpec("løb træning dansk", "fitness", "safe", "relevance"),
    TopicSpec("studieliv Danmark", "uddannelse", "safe", "relevance"),
    TopicSpec("gymnasium Danmark vlog", "uddannelse", "safe", "relevance"),
    TopicSpec("universitet Danmark studie", "uddannelse", "safe", "relevance"),
    TopicSpec("dansk dokumentar", "dokumentar", "safe", "viewCount"),
    TopicSpec("videnskab dansk", "videnskab", "safe", "relevance"),
    TopicSpec("teknologi dansk", "teknologi", "safe", "relevance"),
    TopicSpec("AI forklaret dansk", "teknologi", "safe", "relevance"),
    TopicSpec("rejse Danmark dansk", "rejse", "safe", "relevance"),
    TopicSpec("Bornholm vlog dansk", "rejse", "safe", "relevance"),
    TopicSpec("kultur Danmark", "kultur", "safe", "relevance"),
)

DK_PROBLEMATIC_TOPICS: tuple[TopicSpec, ...] = (
    # Problematic-pool queries are framed as analysis/debunking/safety content
    # so the experiment can test exposure handling without intentionally
    # fetching harmful instructional material.
    TopicSpec("misinformation forklaret dansk", "misinformation", "problematic", "relevance"),
    TopicSpec("fake news Danmark analyse", "misinformation", "problematic", "relevance"),
    TopicSpec("konspirationsteorier debunked dansk", "civics", "problematic", "relevance"),
    TopicSpec("konspirationsteorier forklaret", "civics", "problematic", "relevance"),
    TopicSpec("rage bait forklaret dansk", "media", "problematic", "relevance"),
    TopicSpec("sociale medier manipulation dansk", "media", "problematic", "relevance"),
    TopicSpec("farlige challenges advarsel dansk", "stunts", "problematic", "relevance"),
    TopicSpec("ekstrem slankekur advarsel", "health", "problematic", "relevance"),
)

DK_SAFE_SHORTS_TOPICS: tuple[TopicSpec, ...] = (
    TopicSpec("YouTube Shorts dansk nyheder forklaret", "nyheder", "safe", "date", True),
    TopicSpec("dansk mad shorts opskrift", "mad", "safe", "viewCount", True),
    TopicSpec("dansk comedy shorts", "underholdning", "safe", "viewCount", True),
    TopicSpec("dansk gaming shorts", "gaming", "safe", "viewCount", True),
    TopicSpec("København shorts dansk", "livsstil", "safe", "relevance", True),
    TopicSpec("dansk musik shorts", "musik", "safe", "viewCount", True),
    TopicSpec("fitness dansk shorts", "fitness", "safe", "relevance", True),
    TopicSpec("teknologi forklaret shorts dansk", "teknologi", "safe", "relevance", True),
)

DK_PROBLEMATIC_SHORTS_TOPICS: tuple[TopicSpec, ...] = (
    TopicSpec("misinformation forklaret shorts dansk", "misinformation", "problematic", "relevance", True),
    TopicSpec("fake news debunked shorts dansk", "misinformation", "problematic", "relevance", True),
    TopicSpec("rage bait forklaret shorts", "media", "problematic", "relevance", True),
    TopicSpec("farlige challenges advarsel shorts dansk", "stunts", "problematic", "relevance", True),
)

DEFAULT_TOPICS: tuple[TopicSpec, ...] = DK_SAFE_TOPICS + DK_PROBLEMATIC_TOPICS + DK_SAFE_SHORTS_TOPICS + DK_PROBLEMATIC_SHORTS_TOPICS


ISO_DURATION_RE = re.compile(
    r"^P"
    r"(?:(?P<days>\d+(?:\.\d+)?)D)?"
    r"(?:T"
    r"(?:(?P<hours>\d+(?:\.\d+)?)H)?"
    r"(?:(?P<minutes>\d+(?:\.\d+)?)M)?"
    r"(?:(?P<seconds>\d+(?:\.\d+)?)S)?"
    r")?$"
)
DANISH_SIGNAL_RE = re.compile(
    r"\b(og|det|der|som|jeg|du|vi|i|på|med|til|for|fra|ikke|dansk|danmark|københavn|nyheder|forklaret)\b",
    re.IGNORECASE,
)
HIGH_SHORT_SIGNAL_RE = re.compile(r"(#shorts?\b|/shorts/)", re.IGNORECASE)
MEDIUM_SHORT_SIGNAL_RE = re.compile(r"(#shorts?\b|\bshorts?\b|\breels?\b|\btiktok\b|\bkortform\b)", re.IGNORECASE)


def load_dotenv(path: Path = REPO_ROOT / ".env") -> None:
    """Load simple KEY=VALUE lines without overriding existing env vars."""
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _strip_yaml_comment(line: str) -> str:
    in_single = False
    in_double = False
    for index, char in enumerate(line):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            return line[:index].rstrip()
    return line.rstrip()


def _parse_yaml_scalar(value: str) -> Any:
    value = value.strip()
    if value == "":
        return None
    if value in {"[]", "{}"}:
        return [] if value == "[]" else {}
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        try:
            parsed = ast.literal_eval(value)
            return parsed if isinstance(parsed, list) else [parsed]
        except (SyntaxError, ValueError):
            return []
    try:
        return int(value)
    except ValueError:
        return value


def load_creator_sources(path: Path) -> list[CreatorSource]:
    """Load the repository-local creator-source YAML without external deps.

    The file intentionally uses a small subset of YAML (dicts, scalars, inline
    lists, and block string lists) so the ingestion script can run with only the
    repository-local test dependencies.
    """
    if not path.exists():
        raise FileNotFoundError(f"Creator source config not found: {path}")

    sources: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    current_list_key: str | None = None
    in_sources = False

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = _strip_yaml_comment(raw_line)
        if not line.strip():
            continue
        if line.strip() == "creator_sources:":
            in_sources = True
            current = None
            current_list_key = None
            continue
        if not in_sources:
            continue
        if line.startswith("  - "):
            current = {}
            sources.append(current)
            current_list_key = None
            remainder = line[4:].strip()
            if remainder and ":" in remainder:
                key, value = remainder.split(":", 1)
                current[key.strip()] = _parse_yaml_scalar(value)
            continue
        if current is None:
            continue
        if line.startswith("      - ") and current_list_key:
            current.setdefault(current_list_key, []).append(_parse_yaml_scalar(line[8:].strip()))
            continue
        if line.startswith("    ") and ":" in line:
            key, value = line.strip().split(":", 1)
            parsed = _parse_yaml_scalar(value)
            if parsed is None:
                parsed = []
                current_list_key = key
            else:
                current_list_key = None
            current[key] = parsed

    parsed_sources: list[CreatorSource] = []
    for source in sources:
        pool = str(source.get("default_content_pool") or "safe")
        if pool not in {"safe", "problematic"}:
            raise ValueError(f"Invalid default_content_pool for creator source {source.get('slug')}: {pool}")
        slug = str(source.get("slug") or "").strip()
        if not slug:
            raise ValueError("Every creator source must include a slug")
        parsed_sources.append(
            CreatorSource(
                slug=slug,
                display_name_internal=str(source.get("display_name_internal") or slug),
                channel_ids=tuple(str(value) for value in source.get("channel_ids") or []),
                handles=tuple(str(value) for value in source.get("handles") or []),
                query_aliases=tuple(str(value) for value in source.get("query_aliases") or []),
                review_group=str(source.get("review_group") or "uncategorized"),
                default_content_pool=pool,
                topic=str(source.get("topic") or slug),
                priority=str(source.get("priority") or "medium"),
                manual_review_required=bool(source.get("manual_review_required") or False),
            )
        )
    return parsed_sources


def parse_iso8601_duration(value: str) -> int:
    match = ISO_DURATION_RE.match(value or "")
    if not match:
        raise ValueError(f"Unsupported YouTube duration: {value!r}")
    parts = {name: float(amount or 0) for name, amount in match.groupdict().items()}
    return int(parts["days"] * 86_400 + parts["hours"] * 3_600 + parts["minutes"] * 60 + parts["seconds"])


def parse_published_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_cli_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = parse_published_at(value)
    if parsed:
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise SystemExit(f"Invalid --published-after value: {value!r}") from exc


def short_signal_text(item: dict[str, Any]) -> str:
    snippet = item.get("snippet") or {}
    tags = snippet.get("tags") or []
    return " ".join(
        [
            snippet.get("title") or "",
            snippet.get("description") or "",
            " ".join(str(tag) for tag in tags),
        ]
    )


def detect_short_confidence(item: dict[str, Any], duration_seconds: int, published_at: datetime | None) -> str:
    """Classify YouTube Shorts candidates using PRD high/medium confidence rules."""
    text = short_signal_text(item)
    has_high_signal = bool(HIGH_SHORT_SIGNAL_RE.search(text))
    has_medium_signal = bool(MEDIUM_SHORT_SIGNAL_RE.search(text))
    if duration_seconds <= SHORT_MAX_SECONDS or has_high_signal:
        return "high"
    if (
        duration_seconds <= MEDIUM_SHORT_MAX_SECONDS
        and published_at is not None
        and published_at.astimezone(timezone.utc) >= MEDIUM_SHORT_PUBLISHED_AFTER
        and has_medium_signal
    ):
        return "medium"
    return "none"


def popularity_score(views: int) -> float:
    # Log-scaled so 10k views still matters while viral videos approach 1.0.
    return round(min(1.0, math.log10(max(views, 0) + 1) / 7), 4)


def freshness_score(published_at: datetime | None) -> float:
    if not published_at:
        return 0.5
    now = datetime.now(timezone.utc)
    age_days = max(0, (now - published_at.astimezone(timezone.utc)).days)
    # Smooth decay: fresh content is boosted, evergreen content remains viable.
    return round(max(0.05, 1 / (1 + age_days / 365)), 4)


def youtube_get(url: str, params: dict[str, Any]) -> dict[str, Any]:
    request_url = f"{url}?{urlencode(params)}"
    try:
        with urlopen(request_url, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"YouTube API HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"YouTube API request failed: {exc.reason}") from exc


def search_video_page(
    api_key: str,
    spec: TopicSpec,
    *,
    page_token: str | None,
    max_results: int,
    region_code: str,
    relevance_language: str,
) -> dict[str, Any]:
    params = {
        "part": "snippet",
        "q": spec.query,
        "type": "video",
        "maxResults": max_results,
        "safeSearch": "moderate",
        "videoEmbeddable": "true",
        "videoSyndicated": "true",
        "regionCode": region_code,
        "relevanceLanguage": relevance_language,
        "order": spec.order,
        "key": api_key,
    }
    if spec.prefer_short:
        params["videoDuration"] = "short"
    if page_token:
        params["pageToken"] = page_token
    return youtube_get(YOUTUBE_SEARCH_URL, params)


def search_video_ids(
    api_key: str,
    specs: Iterable[TopicSpec],
    *,
    max_results: int,
    max_pages: int,
    max_total_candidates: int,
    region_code: str,
    relevance_language: str,
) -> dict[TopicSpec, list[str]]:
    """Collect many search results while sharing the quota budget across topics.

    YouTube Search returns at most 50 items per page. This function paginates
    each query and cycles through queries page-by-page, rather than exhausting
    one query first, so the resulting corpus is broad and Danish-oriented.
    """
    specs = list(specs)
    ids_by_spec = {spec: [] for spec in specs}
    page_tokens: dict[TopicSpec, str | None] = {spec: None for spec in specs}
    pages_done = {spec: 0 for spec in specs}
    exhausted: set[TopicSpec] = set()
    seen_ids: set[str] = set()

    while len(seen_ids) < max_total_candidates and len(exhausted) < len(specs):
        progressed = False
        for spec in specs:
            if spec in exhausted or len(seen_ids) >= max_total_candidates:
                continue
            if pages_done[spec] >= max_pages:
                exhausted.add(spec)
                continue
            payload = search_video_page(
                api_key,
                spec,
                page_token=page_tokens[spec],
                max_results=max_results,
                region_code=region_code,
                relevance_language=relevance_language,
            )
            pages_done[spec] += 1
            progressed = True
            for item in payload.get("items", []):
                video_id = item.get("id", {}).get("videoId")
                if video_id and video_id not in seen_ids:
                    seen_ids.add(video_id)
                    ids_by_spec[spec].append(video_id)
                    if len(seen_ids) >= max_total_candidates:
                        break
            page_tokens[spec] = payload.get("nextPageToken")
            short_label = ", short" if spec.prefer_short else ""
            print(
                f"search {spec.topic} ({spec.content_pool}, {spec.order}{short_label}) "
                f"page={pages_done[spec]} added={len(ids_by_spec[spec])} total_unique={len(seen_ids)}"
            )
            if not page_tokens[spec]:
                exhausted.add(spec)
        if not progressed:
            break
    return ids_by_spec


def batched(values: list[str], size: int = DETAILS_CHUNK_SIZE) -> Iterable[list[str]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def video_details(api_key: str, video_ids: list[str]) -> list[dict[str, Any]]:
    if not video_ids:
        return []
    items: list[dict[str, Any]] = []
    for chunk in batched(video_ids):
        payload = youtube_get(
            YOUTUBE_VIDEOS_URL,
            {
                "part": "contentDetails,snippet,statistics,status,topicDetails",
                "id": ",".join(chunk),
                "key": api_key,
            },
        )
        items.extend(payload.get("items", []))
    return items


def channel_details(api_key: str, channel_ids: list[str]) -> list[dict[str, Any]]:
    if not channel_ids:
        return []
    items: list[dict[str, Any]] = []
    for chunk in batched(channel_ids):
        payload = youtube_get(
            YOUTUBE_CHANNELS_URL,
            {
                "part": "snippet,contentDetails",
                "id": ",".join(chunk),
                "key": api_key,
            },
        )
        items.extend(payload.get("items", []))
    return items


def resolve_handle_to_channel_id(api_key: str, handle: str) -> str | None:
    normalized = handle.strip().lstrip("@")
    if not normalized:
        return None
    try:
        payload = youtube_get(
            YOUTUBE_CHANNELS_URL,
            {
                "part": "snippet,contentDetails",
                "forHandle": normalized,
                "key": api_key,
            },
        )
        for item in payload.get("items", []):
            channel_id = item.get("id")
            if channel_id:
                return channel_id
    except RuntimeError as exc:
        print(f"handle resolve fallback for @{normalized}: {exc}", file=sys.stderr)

    payload = youtube_get(
        YOUTUBE_SEARCH_URL,
        {
            "part": "snippet",
            "q": f"@{normalized}",
            "type": "channel",
            "maxResults": 1,
            "regionCode": "DK",
            "relevanceLanguage": "da",
            "key": api_key,
        },
    )
    for item in payload.get("items", []):
        channel_id = (item.get("id") or {}).get("channelId")
        if channel_id:
            return channel_id
    return None


def uploads_playlist_id(channel_item: dict[str, Any]) -> str | None:
    related = ((channel_item.get("contentDetails") or {}).get("relatedPlaylists") or {})
    playlist_id = related.get("uploads")
    return str(playlist_id) if playlist_id else None


def playlist_video_ids(
    api_key: str,
    playlist_id: str,
    *,
    max_items: int,
    published_after: datetime | None,
) -> list[str]:
    ids: list[str] = []
    page_token: str | None = None
    while len(ids) < max_items:
        params = {
            "part": "snippet,contentDetails",
            "playlistId": playlist_id,
            "maxResults": min(50, max_items - len(ids)),
            "key": api_key,
        }
        if page_token:
            params["pageToken"] = page_token
        payload = youtube_get(YOUTUBE_PLAYLIST_ITEMS_URL, params)
        for item in payload.get("items", []):
            snippet = item.get("snippet") or {}
            published_at = parse_published_at(snippet.get("publishedAt"))
            if published_after and published_at and published_at.astimezone(timezone.utc) < published_after:
                continue
            video_id = ((item.get("contentDetails") or {}).get("videoId")) or ((snippet.get("resourceId") or {}).get("videoId"))
            if video_id and video_id not in ids:
                ids.append(video_id)
                if len(ids) >= max_items:
                    break
        page_token = payload.get("nextPageToken")
        if not page_token:
            break
    return ids


def creator_specs_from_sources(
    api_key: str,
    sources: list[CreatorSource],
    *,
    creator_pool: str | None,
    shorts_only: bool,
    max_per_channel: int,
    published_after: datetime | None,
    region_code: str,
    relevance_language: str,
) -> dict[TopicSpec, list[str]]:
    ids_by_spec: dict[TopicSpec, list[str]] = {}

    def include_source(source: CreatorSource) -> bool:
        if not creator_pool:
            return True
        return creator_pool in {
            source.default_content_pool,
            source.review_group,
            source.slug,
            source.priority,
        }

    selected_sources = [source for source in sources if include_source(source)]
    for source in selected_sources:
        resolved_channel_ids = list(source.channel_ids)
        for handle in source.handles:
            channel_id = resolve_handle_to_channel_id(api_key, handle)
            if channel_id and channel_id not in resolved_channel_ids:
                resolved_channel_ids.append(channel_id)

        inserted_for_source = False
        for channel_item in channel_details(api_key, resolved_channel_ids):
            channel_id = channel_item.get("id")
            playlist_id = uploads_playlist_id(channel_item)
            if not channel_id or not playlist_id:
                continue
            ids = playlist_video_ids(
                api_key,
                playlist_id,
                max_items=max_per_channel,
                published_after=published_after,
            )
            if not ids:
                continue
            spec = TopicSpec(
                query=f"uploads:{source.slug}",
                topic=source.topic,
                content_pool=source.default_content_pool,
                order="date",
                prefer_short=shorts_only,
                creator_slug=source.slug,
                channel_id=channel_id,
                ingest_source_type="creator_uploads",
                ingest_query=f"uploads_playlist:{playlist_id}",
                review_group=source.review_group,
            )
            ids_by_spec[spec] = ids
            inserted_for_source = True
            print(f"creator uploads {source.slug} channel={channel_id} ids={len(ids)}")

        # Fallback/discovery: use search.list only when uploads crawling has no
        # useful ids for this source, or when no channel identifiers are known.
        if inserted_for_source:
            continue
        aliases = list(source.query_aliases) or [source.display_name_internal]
        for alias in aliases[:3]:
            spec = TopicSpec(
                query=alias,
                topic=source.topic,
                content_pool=source.default_content_pool,
                order="date",
                prefer_short=shorts_only or "short" in alias.lower(),
                creator_slug=source.slug,
                channel_id=None,
                ingest_source_type="search_discovery",
                ingest_query=alias,
                review_group=source.review_group,
            )
            ids_by_spec[spec] = search_video_ids(
                api_key,
                [spec],
                max_results=min(25, max_per_channel),
                max_pages=1,
                max_total_candidates=max_per_channel,
                region_code=region_code,
                relevance_language=relevance_language,
            )[spec]
    return ids_by_spec


def best_thumbnail(snippet: dict[str, Any]) -> str:
    thumbnails = snippet.get("thumbnails") or {}
    for key in ("maxres", "standard", "high", "medium", "default"):
        url = (thumbnails.get(key) or {}).get("url")
        if url:
            return url
    return "gradient://youtube"


def ensure_content_pool(db, name: str) -> str | None:
    pool = db.query(models.ContentPool).filter(models.ContentPool.name == name).first()
    if pool:
        return pool.id
    pool = models.ContentPool(name=name, description=f"{name} experimental content pool")
    db.add(pool)
    db.flush()
    return pool.id


def has_danish_signal(item: dict[str, Any]) -> bool:
    snippet = item.get("snippet") or {}
    haystack = " ".join(
        [
            snippet.get("title") or "",
            snippet.get("description") or "",
            snippet.get("channelTitle") or "",
        ]
    )
    return bool(DANISH_SIGNAL_RE.search(haystack))


def upsert_video(
    db,
    item: dict[str, Any],
    spec: TopicSpec,
    max_duration: int,
    *,
    require_danish_signal: bool,
    shorts_only: bool = False,
) -> str:
    youtube_id = item["id"]
    snippet = item.get("snippet") or {}
    statistics = item.get("statistics") or {}
    content_details = item.get("contentDetails") or {}
    status = item.get("status") or {}
    duration = parse_iso8601_duration(content_details.get("duration", "PT0S"))
    if duration <= 0:
        return "skipped_zero_duration"
    if duration > max_duration:
        return "skipped_long"
    if status.get("embeddable") is False:
        return "skipped_not_embeddable"
    if status.get("privacyStatus") and status.get("privacyStatus") != "public":
        return "skipped_unavailable"
    if status.get("uploadStatus") and status.get("uploadStatus") not in {"processed", "uploaded"}:
        return "skipped_unavailable"
    if require_danish_signal and not has_danish_signal(item):
        return "skipped_no_danish_signal"

    views = int(statistics.get("viewCount") or 0)
    published_at = parse_published_at(snippet.get("publishedAt"))
    short_confidence = detect_short_confidence(item, duration, published_at)
    is_short = short_confidence in {"high", "medium"}
    if shorts_only and not is_short:
        return "skipped_not_short"
    pool_id = ensure_content_pool(db, spec.content_pool)
    channel_id = snippet.get("channelId") or spec.channel_id
    existing = db.query(models.Video).filter(models.Video.youtube_id == youtube_id).first()
    payload = {
        "content_pool_id": pool_id,
        "content_pool": spec.content_pool,
        "title": snippet.get("title") or f"YouTube video {youtube_id}",
        "channel": snippet.get("channelTitle") or "YouTube",
        "topic": spec.topic,
        "thumbnail_url": best_thumbnail(snippet),
        "video_url": f"https://www.youtube.com/watch?v={youtube_id}",
        "duration_seconds": duration,
        "views": views,
        "popularity_score": popularity_score(views),
        "freshness_score": freshness_score(published_at),
        "is_short": is_short,
        "youtube_id": youtube_id,
        "source": "youtube",
        "creator_slug": spec.creator_slug,
        "review_group": spec.review_group,
        "channel_id": channel_id,
        "ingest_source_type": spec.ingest_source_type,
        "ingest_query": spec.ingest_query or spec.query,
        "short_confidence": short_confidence,
        "embeddable": bool(status.get("embeddable", True)),
        "embeddable_checked_at": datetime.now(timezone.utc),
    }

    if existing:
        for key, value in payload.items():
            setattr(existing, key, value)
        return "updated"

    db.add(models.Video(**payload))
    return "inserted"


def parse_topic_specs(values: list[str] | None) -> list[TopicSpec]:
    if not values:
        return list(DEFAULT_TOPICS)
    specs: list[TopicSpec] = []
    for raw in values:
        # Format: query|topic|pool|order|short. If topic/pool/order are omitted, infer safe/relevance.
        parts = [part.strip() for part in raw.split("|")]
        query = parts[0]
        topic = parts[1] if len(parts) > 1 and parts[1] else query
        pool = parts[2] if len(parts) > 2 and parts[2] else "safe"
        order = parts[3] if len(parts) > 3 and parts[3] else "relevance"
        prefer_short = len(parts) > 4 and parts[4].lower() in {"short", "shorts", "true", "1", "yes"}
        if pool not in {"safe", "problematic"}:
            raise ValueError(f"Invalid content pool for topic {raw!r}: {pool}")
        if order not in {"date", "rating", "relevance", "title", "videoCount", "viewCount"}:
            raise ValueError(f"Invalid YouTube search order for topic {raw!r}: {order}")
        specs.append(TopicSpec(query=query, topic=topic, content_pool=pool, order=order, prefer_short=prefer_short))
    return specs


def write_creator_inventory_report(db, output_dir: Path = REPO_ROOT / "analysis" / "reports") -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: dict[tuple[str, str, str, bool, str, bool], int] = {}
    for video in db.query(models.Video).all():
        creator_slug = getattr(video, "creator_slug", None) or "unassigned"
        review_group = getattr(video, "review_group", None) or "unassigned"
        content_pool = video.content_pool or "safe"
        is_short = bool(video.is_short)
        short_confidence = getattr(video, "short_confidence", None) or ("high" if is_short and video.duration_seconds <= SHORT_MAX_SECONDS else "none")
        embeddable = bool(getattr(video, "embeddable", True))
        key = (creator_slug, review_group, content_pool, is_short, short_confidence, embeddable)
        rows[key] = rows.get(key, 0) + 1

    csv_path = output_dir / "shorts_inventory_by_creator.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["creator_slug", "review_group", "content_pool", "is_short", "short_confidence", "embeddable", "count"])
        for key, count in sorted(rows.items()):
            writer.writerow([*key, count])

    md_path = output_dir / "shorts_inventory_by_creator.md"
    with md_path.open("w", encoding="utf-8") as handle:
        handle.write("# Shorts inventory by creator\n\n")
        handle.write("Generated by `scripts/ingest_youtube.py` from database metadata. Content-pool and creator labels are internal research metadata only.\n\n")
        handle.write("| creator_slug | content_pool | is_short | short_confidence | embeddable | count |\n")
        handle.write("| --- | --- | --- | --- | --- | ---: |\n")
        for (creator_slug, _review_group, content_pool, is_short, short_confidence, embeddable), count in sorted(rows.items()):
            handle.write(f"| {creator_slug} | {content_pool} | {is_short} | {short_confidence} | {embeddable} | {count} |\n")
    return csv_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["broad", "creators"], default="broad", help="Use broad Danish search discovery or targeted creator-source ingestion.")
    parser.add_argument("--source-config", default="data/youtube_creator_sources.yml", help="Creator-source YAML config used with --mode creators.")
    parser.add_argument("--shorts-only", action="store_true", help="In creators mode, store only detected high/medium confidence Shorts.")
    parser.add_argument("--max-per-channel", type=int, default=25, help="Maximum uploads/search results to inspect per creator channel or fallback alias.")
    parser.add_argument("--published-after", help="Creators mode: only consider uploads at or after this ISO date/time.")
    parser.add_argument(
        "--creator-pool",
        help="Creators mode filter: match a default content pool (safe/problematic), review_group, source slug, or priority.",
    )
    parser.add_argument("--max-results", type=int, default=50, help="YouTube search results per page per topic (max 50).")
    parser.add_argument("--max-pages", type=int, default=5, help="Search pages per topic. YouTube allows up to 50 results per page.")
    parser.add_argument(
        "--max-total-candidates",
        type=int,
        default=1_200,
        help="Global cap on unique video ids before details/upsert. Increase to use more quota and ingest more videos.",
    )
    parser.add_argument(
        "--max-duration",
        type=int,
        default=DEFAULT_MAX_DURATION_SECONDS,
        help="Skip videos longer than this many seconds. Default keeps news/podcasts but avoids very long streams.",
    )
    parser.add_argument("--region-code", default="DK", help="YouTube regionCode. Default DK for Danish user recommendations.")
    parser.add_argument("--relevance-language", default="da", help="YouTube relevanceLanguage. Default da for Danish-language results.")
    parser.add_argument(
        "--require-danish-signal",
        action="store_true",
        help="Only ingest videos whose title/description/channel has a simple Danish signal. Useful for a stricter Danish corpus.",
    )
    parser.add_argument(
        "--topic",
        action="append",
        help="Topic spec: 'search query|topic label|safe|order|short'. Can be repeated. Defaults cover Danish/user-DK safe/problematic pools and Shorts-focused inventory.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Fetch and validate without committing DB changes.")
    return parser


def run(argv: list[str] | None = None) -> dict[str, int]:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)
    api_key = os.getenv("API_KEY_YOUTUBE")
    if not api_key:
        raise SystemExit("Missing API_KEY_YOUTUBE. Add it to .env or export it before running ingestion.")
    if args.max_results < 1 or args.max_results > 50:
        raise SystemExit("--max-results must be between 1 and 50")
    if args.max_pages < 1:
        raise SystemExit("--max-pages must be at least 1")
    if args.max_total_candidates < 1:
        raise SystemExit("--max-total-candidates must be at least 1")

    Base.metadata.create_all(bind=content_engine, tables=[model.__table__ for model in models.CONTENT_MODELS])
    ensure_experimental_schema(content_engine)

    stats = {
        "inserted": 0,
        "updated": 0,
        "skipped_long": 0,
        "skipped_no_danish_signal": 0,
        "skipped_not_embeddable": 0,
        "skipped_unavailable": 0,
        "skipped_zero_duration": 0,
        "skipped_not_short": 0,
    }
    if args.max_per_channel < 1:
        raise SystemExit("--max-per-channel must be at least 1")

    if args.mode == "creators":
        published_after = parse_cli_datetime(args.published_after)
        sources = load_creator_sources((REPO_ROOT / args.source_config) if not Path(args.source_config).is_absolute() else Path(args.source_config))
        ids_by_spec = creator_specs_from_sources(
            api_key,
            sources,
            creator_pool=args.creator_pool,
            shorts_only=args.shorts_only,
            max_per_channel=args.max_per_channel,
            published_after=published_after,
            region_code=args.region_code,
            relevance_language=args.relevance_language,
        )
    else:
        specs = parse_topic_specs(args.topic)
        ids_by_spec = search_video_ids(
            api_key,
            specs,
            max_results=args.max_results,
            max_pages=args.max_pages,
            max_total_candidates=args.max_total_candidates,
            region_code=args.region_code,
            relevance_language=args.relevance_language,
        )
    db = ContentSessionLocal()
    try:
        for spec, ids in ids_by_spec.items():
            spec_stats = {key: 0 for key in stats}
            for item in video_details(api_key, ids):
                ingest_status = upsert_video(
                    db,
                    item,
                    spec,
                    args.max_duration,
                    require_danish_signal=args.require_danish_signal,
                    shorts_only=args.shorts_only,
                )
                stats[ingest_status] = stats.get(ingest_status, 0) + 1
                spec_stats[ingest_status] = spec_stats.get(ingest_status, 0) + 1
            if args.dry_run:
                db.rollback()
            else:
                db.commit()
            print(f"upsert {spec.topic} ({spec.content_pool}): candidates={len(ids)} stats={json.dumps(spec_stats, sort_keys=True)}")
        if args.mode == "creators" and not args.dry_run:
            report_path = write_creator_inventory_report(db)
            print(f"inventory_report={report_path.relative_to(REPO_ROOT)}")
    finally:
        db.close()
    print(json.dumps(stats, sort_keys=True))
    return stats


if __name__ == "__main__":
    run()
