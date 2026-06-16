import math
import hashlib
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from . import models
from .experiment import normalize_pool_mode


def _tokens(value: str | None) -> set[str]:
    if not value:
        return set()
    cleaned = value.lower().replace("-", " ")
    return {token.strip(".,:;!?()[]{}\"'") for token in cleaned.split() if len(token.strip(".,:;!?()[]{}\"'")) > 2}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def topic_similarity(video: models.Video, topic: str | None) -> float:
    """Neutral/homepage or topic-based relevance for the PRD formula."""
    if not topic:
        return 0.5
    if video.topic == topic:
        return 1.0
    source_tokens = _tokens(topic)
    candidate_tokens = _tokens(video.topic) | _tokens(video.title)
    overlap = _jaccard(source_tokens, candidate_tokens)
    if overlap > 0:
        return 0.25 + min(0.5, overlap)
    return 0.2


def related_similarity(video: models.Video, source_video: models.Video) -> float:
    """Boost related rows that match or overlap the current video topic/title."""
    if video.topic == source_video.topic:
        return 1.1
    source_tokens = _tokens(source_video.topic) | _tokens(source_video.title)
    candidate_tokens = _tokens(video.topic) | _tokens(video.title)
    overlap = _jaccard(source_tokens, candidate_tokens)
    if overlap > 0:
        return 0.25 + min(0.75, overlap * 2)
    return 0.15


def _fallback_popularity_score(video: models.Video) -> float:
    if video.popularity_score and video.popularity_score > 0:
        return float(video.popularity_score)
    return min(1.0, math.log10(max(video.views or 0, 0) + 1) / 7)


def _fallback_freshness_score(video: models.Video) -> float:
    if video.freshness_score and video.freshness_score > 0:
        return float(video.freshness_score)
    created_at = video.created_at
    if not created_at:
        return 0.5
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    age_days = max(0, (datetime.now(timezone.utc) - created_at.astimezone(timezone.utc)).days)
    return max(0.05, 1 / (1 + age_days / 365))


def score_video(video: models.Video, topic: str | None = None) -> float:
    """PRD score: topic_similarity + popularity_score + freshness_score."""
    return topic_similarity(video, topic) + _fallback_popularity_score(video) + _fallback_freshness_score(video)


def score_related_video(video: models.Video, source_video: models.Video) -> float:
    """Related PRD score with topic/title overlap similarity."""
    return related_similarity(video, source_video) + _fallback_popularity_score(video) + _fallback_freshness_score(video)


def _pool_filtered(query, pool_mode: str):
    if pool_mode == "mixed":
        return query
    return query.filter(models.Video.content_pool == pool_mode)


def servable_video_query(query):
    """Restrict served surfaces to rows that can actually play on-platform."""
    return query.filter(
        models.Video.embeddable.is_(True),
        models.Video.video_url.is_not(None),
        models.Video.video_url != "",
    )


def prefer_real_youtube_rows(candidates: list[models.Video]) -> list[models.Video]:
    """Use ingested YouTube rows when present; seed fixtures remain fallback only."""
    real_rows = [video for video in candidates if video.youtube_id]
    return real_rows or candidates


def _ranked(candidates: list[models.Video], score_fn, limit: int) -> list[models.Video]:
    return sorted(
        candidates,
        key=lambda video: (
            score_fn(video),
            video.views or 0,
            video.title.lower(),
            video.id,
        ),
        reverse=True,
    )[:limit]


def _hash_int(seed: str, value: str) -> int:
    digest = hashlib.sha256(f"{seed}:{value}".encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _session_seed(session_id: str | None, surface: str, pool_mode: str, topic: str | None = None) -> str | None:
    if not session_id:
        return f"transient:{surface}:{pool_mode}:{topic or 'all'}:{time.time_ns()}"
    return f"{session_id}:{surface}:{pool_mode}:{topic or 'all'}"


def _rotate_for_session(videos: list[models.Video], seed: str | None) -> list[models.Video]:
    """Deterministically rotate a ranked feed for a session.

    The base order is still computed by the PRD score formula. Rotation gives
    sessions reproducible exposure variants without changing condition/pool
    constraints or making tests flaky.
    """
    if not seed or len(videos) <= 1:
        return videos
    offset = _hash_int(seed, "offset") % len(videos)
    return videos[offset:] + videos[:offset]


def _topic_filtered(candidates: list[models.Video], topic: str | None) -> list[models.Video]:
    normalized = (topic or "").strip().lower()
    if not normalized or normalized == "all":
        return candidates
    return [
        video
        for video in candidates
        if normalized == (video.topic or "").strip().lower()
        or normalized in _tokens(video.topic)
        or normalized in _tokens(video.title)
    ]


def _ranked_mixed(candidates: list[models.Video], score_fn, limit: int) -> list[models.Video]:
    """Rank deterministically while ensuring mixed-pool treatments expose both pools."""
    ranked = _ranked(candidates, score_fn, len(candidates))
    safe = [video for video in ranked if video.content_pool == "safe"]
    problematic = [video for video in ranked if video.content_pool == "problematic"]
    if not safe or not problematic:
        return ranked[:limit]

    first_pool = ranked[0].content_pool
    queues = [safe, problematic] if first_pool == "safe" else [problematic, safe]
    result: list[models.Video] = []
    while len(result) < limit and (queues[0] or queues[1]):
        for queue in queues:
            if queue and len(result) < limit:
                result.append(queue.pop(0))
    return result


def _cap_repeated_creators(videos: list[models.Video], limit: int, *, max_per_creator: int) -> list[models.Video]:
    """Limit repeated Shorts exposure from one creator when creator metadata exists."""
    if max_per_creator <= 0:
        return videos[:limit]
    result: list[models.Video] = []
    skipped: list[models.Video] = []
    counts: dict[str, int] = {}
    for video in videos:
        creator = (getattr(video, "creator_slug", None) or "").strip()
        if not creator:
            result.append(video)
        elif counts.get(creator, 0) < max_per_creator:
            counts[creator] = counts.get(creator, 0) + 1
            result.append(video)
        else:
            skipped.append(video)
        if len(result) >= limit:
            break

    if len(result) < limit:
        seen_ids = {video.id for video in result}
        for video in skipped:
            if video.id not in seen_ids:
                result.append(video)
                seen_ids.add(video.id)
                if len(result) >= limit:
                    break
    return result[:limit]


def _ensure_mixed_pool_exposure(result: list[models.Video], candidates: list[models.Video], score_fn, limit: int) -> list[models.Video]:
    """Keep mixed treatments mixed after topic diversification."""
    pools_in_candidates = {video.content_pool for video in candidates}
    pools_in_result = {video.content_pool for video in result}
    missing_pools = [pool for pool in ("safe", "problematic") if pool in pools_in_candidates and pool not in pools_in_result]
    if not missing_pools:
        return result[:limit]

    result_ids = {video.id for video in result}
    repaired = result[:limit]
    for pool in missing_pools:
        replacements = _ranked([video for video in candidates if video.content_pool == pool and video.id not in result_ids], score_fn, 1)
        if not replacements:
            continue
        if len(repaired) >= limit and repaired:
            repaired[-1] = replacements[0]
        else:
            repaired.append(replacements[0])
        result_ids.add(replacements[0].id)
    return repaired[:limit]


def _fill_from_candidates(
    result: list[models.Video],
    *,
    candidates: list[models.Video],
    limit: int,
    blocked_ids: set[str] | None = None,
) -> list[models.Video]:
    seen = {video.id for video in result}
    if blocked_ids:
        seen |= blocked_ids
    for video in candidates:
        if video.id in seen:
            continue
        result.append(video)
        seen.add(video.id)
        if len(result) >= limit:
            break
    return result[:limit]


def _compose_with_slots(
    safe_ranked: list[models.Video],
    problematic_ranked: list[models.Video],
    *,
    limit: int,
    problematic_slots: list[int],
) -> list[models.Video]:
    if limit <= 0:
        return []

    slots = {slot for slot in problematic_slots if 0 <= slot < limit}
    result: list[models.Video | None] = [None] * limit
    used_ids: set[str] = set()

    problematic_iter = iter(problematic_ranked)
    safe_iter = iter(safe_ranked)

    for index in range(limit):
        iterator = problematic_iter if index in slots else safe_iter
        for video in iterator:
            if video.id in used_ids:
                continue
            result[index] = video
            used_ids.add(video.id)
            break

    merged = [video for video in result if video is not None]
    if len(merged) < limit:
        merged = _fill_from_candidates(
            merged,
            candidates=problematic_ranked + safe_ranked,
            limit=limit,
            blocked_ids=used_ids,
        )
    return merged[:limit]


def _mixed_problematic_slots(limit: int, target_problematic: int) -> list[int]:
    if limit >= 16 and target_problematic >= 4:
        return [1, 4, 7, 12]
    if limit >= 10 and target_problematic >= 3:
        return [1, 4, 7][:target_problematic]
    if limit >= 8 and target_problematic >= 3:
        return [1, 4, 7]
    if limit >= 8 and target_problematic == 2:
        return [2, 5]
    return list(range(min(limit, target_problematic)))


def _target_problematic_count(limit: int, available_problematic: int) -> int:
    if available_problematic <= 0 or limit <= 0:
        return 0
    if limit >= 16:
        return min(4, available_problematic)
    if limit >= 10:
        return min(3, available_problematic)
    return min(max(1, min(limit // 3, 3)), available_problematic)


def _mixed_feed_with_quota(
    safe_ranked: list[models.Video],
    problematic_ranked: list[models.Video],
    *,
    limit: int,
) -> list[models.Video]:
    if not problematic_ranked:
        return safe_ranked[:limit]
    if not safe_ranked:
        return problematic_ranked[:limit]

    target_problematic = _target_problematic_count(limit, len(problematic_ranked))
    slots = _mixed_problematic_slots(limit, target_problematic)
    return _compose_with_slots(
        safe_ranked,
        problematic_ranked,
        limit=limit,
        problematic_slots=slots,
    )


def _ranked_diverse_by_topic(candidates: list[models.Video], score_fn, limit: int, seed: str | None, pool_mode: str) -> list[models.Video]:
    """Build an "All" feed by sampling across topics instead of one dominant category.

    The individual topic queues are still score-ranked by the PRD formula, but
    the feed is assembled round-robin across topic/category groups. The topic
    order and within-topic offsets are seed-driven, so session ids get
    reproducible variants while anonymous homepage loads can still rotate.
    """
    if not candidates or limit <= 0:
        return []
    if len(candidates) <= limit and len({video.topic for video in candidates}) <= 1:
        return _ranked_mixed(candidates, score_fn, limit) if pool_mode == "mixed" else _ranked(candidates, score_fn, limit)

    seed = seed or "no-seed"
    grouped: dict[str, list[models.Video]] = {}
    for video in candidates:
        grouped.setdefault((video.topic or "uncategorized").strip() or "uncategorized", []).append(video)

    topic_order = sorted(grouped, key=lambda topic: _hash_int(seed, topic))
    queues: dict[str, list[models.Video]] = {}
    for topic, topic_videos in grouped.items():
        ranked_topic = _ranked(topic_videos, score_fn, len(topic_videos))
        queues[topic] = _rotate_for_session(ranked_topic, f"{seed}:{topic}")

    result: list[models.Video] = []
    seen: set[str] = set()
    while len(result) < limit and any(queues.values()):
        for topic in topic_order:
            queue = queues[topic]
            while queue and queue[0].id in seen:
                queue.pop(0)
            if queue and len(result) < limit:
                video = queue.pop(0)
                result.append(video)
                seen.add(video.id)

    if len(result) < limit:
        for video in _ranked(candidates, score_fn, len(candidates)):
            if video.id not in seen:
                result.append(video)
                seen.add(video.id)
                if len(result) >= limit:
                    break

    if pool_mode == "mixed":
        return _ensure_mixed_pool_exposure(result, candidates, score_fn, limit)
    return result[:limit]


def homepage_recommendations(
    db: Session,
    limit: int = 16,
    *,
    condition: str | None = None,
    content_pool: str | None = None,
    topic: str | None = None,
    session_id: str | None = None,
) -> list[models.Video]:
    pool_mode = normalize_pool_mode(content_pool, condition)
    query = servable_video_query(db.query(models.Video)).filter(models.Video.is_short.is_(False))
    candidates = prefer_real_youtube_rows(_pool_filtered(query, pool_mode).all())
    normalized_topic = (topic or "").strip().lower()
    seed = _session_seed(session_id, "recommendation", pool_mode, topic)
    if not normalized_topic or normalized_topic == "all":
        if pool_mode == "mixed":
            safe_candidates = [video for video in candidates if video.content_pool == "safe"]
            problematic_candidates = [video for video in candidates if video.content_pool == "problematic"]
            safe_ranked = _ranked_diverse_by_topic(
                safe_candidates,
                lambda video: score_video(video),
                min(limit, len(safe_candidates)),
                f"{seed}:safe" if seed else None,
                "safe",
            )
            problematic_ranked = _ranked_diverse_by_topic(
                problematic_candidates,
                lambda video: score_video(video),
                min(limit, len(problematic_candidates)),
                f"{seed}:problematic" if seed else None,
                "problematic",
            )
            ranked = _mixed_feed_with_quota(safe_ranked, problematic_ranked, limit=min(limit, len(candidates)))
        else:
            ranked = _ranked_diverse_by_topic(candidates, lambda video: score_video(video), min(limit, len(candidates)), seed, pool_mode)
    else:
        filtered = _topic_filtered(candidates, topic)
        if pool_mode == "mixed":
            safe_ranked = _rotate_for_session(
                _ranked([video for video in filtered if video.content_pool == "safe"], lambda video: score_video(video), min(limit, len(filtered))),
                f"{seed}:safe" if seed else None,
            )
            problematic_ranked = _rotate_for_session(
                _ranked([video for video in filtered if video.content_pool == "problematic"], lambda video: score_video(video), min(limit, len(filtered))),
                f"{seed}:problematic" if seed else None,
            )
            ranked = _mixed_feed_with_quota(safe_ranked, problematic_ranked, limit=min(limit, len(filtered)))
        else:
            ranked = _ranked(filtered, lambda video: score_video(video), min(limit, len(filtered)))
            ranked = _rotate_for_session(ranked, seed)
    return ranked


def related_videos(
    db: Session,
    source_video: models.Video,
    limit: int = 8,
    *,
    condition: str | None = None,
    content_pool: str | None = None,
    session_id: str | None = None,
) -> list[models.Video]:
    pool_mode = normalize_pool_mode(content_pool, condition)
    query = servable_video_query(db.query(models.Video)).filter(models.Video.is_short.is_(False), models.Video.id != source_video.id)
    candidates = prefer_real_youtube_rows(_pool_filtered(query, pool_mode).all())
    if pool_mode == "mixed":
        ranked = _ranked_mixed(candidates, lambda video: score_related_video(video, source_video), limit)
    else:
        ranked = _ranked(candidates, lambda video: score_related_video(video, source_video), limit)
    return _rotate_for_session(ranked, _session_seed(session_id, "related", pool_mode, source_video.topic))


def shorts_feed(
    db: Session,
    limit: int = 10,
    *,
    condition: str | None = None,
    content_pool: str | None = None,
    session_id: str | None = None,
) -> list[models.Video]:
    pool_mode = normalize_pool_mode(content_pool, condition)
    query = servable_video_query(db.query(models.Video)).filter(models.Video.is_short.is_(True))
    candidates = prefer_real_youtube_rows(_pool_filtered(query, pool_mode).all())
    if pool_mode == "mixed":
        safe_ranked = _cap_repeated_creators(
            _ranked([video for video in candidates if video.content_pool == "safe"], lambda video: score_video(video), max(limit * 3, limit)),
            max(limit * 3, limit),
            max_per_creator=2,
        )
        problematic_ranked = _cap_repeated_creators(
            _ranked([video for video in candidates if video.content_pool == "problematic"], lambda video: score_video(video), max(limit * 3, limit)),
            max(limit * 3, limit),
            max_per_creator=2,
        )
        ranked = _mixed_feed_with_quota(safe_ranked, problematic_ranked, limit=limit)
    else:
        ranked = _ranked(candidates, lambda video: score_video(video), max(limit * 3, limit))
    rotated = _rotate_for_session(ranked, _session_seed(session_id, "shorts", pool_mode))
    return _cap_repeated_creators(rotated, limit, max_per_creator=2)


def available_topics(
    db: Session,
    *,
    condition: str | None = None,
    content_pool: str | None = None,
) -> list[str]:
    """Return user-facing long-form topics for category chips."""
    pool_mode = normalize_pool_mode(content_pool, condition)
    query = servable_video_query(db.query(models.Video)).with_entities(models.Video.topic).filter(models.Video.is_short.is_(False))
    if pool_mode != "mixed":
        query = query.filter(models.Video.content_pool == pool_mode)
    return sorted({(topic or "").strip() for (topic,) in query.all() if (topic or "").strip()})
