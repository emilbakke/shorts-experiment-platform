from sqlalchemy.orm import Session
from . import models

VIDEO_URL = "https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4"

SEED_POOLS = [
    {"name": "safe", "description": "Non-problematic experimental content pool"},
    {"name": "problematic", "description": "Problematic exposure content pool for treatment sessions"},
]

SEED_VIDEOS = [
    ("Neon City Walkthrough in 4K", "Urban Lab", "travel", 865000, 0.96, 0.84, False, "safe"),
    ("How Recommendation Systems Rank Videos", "ML Studio", "technology", 430000, 0.91, 0.92, False, "safe"),
    ("Street Food Tour: Night Market Classics", "Flavor Map", "food", 1200000, 0.98, 0.80, False, "safe"),
    ("Build a Cozy Desk Setup from Scratch", "Creator Desk", "design", 310000, 0.86, 0.88, False, "safe"),
    ("Morning Focus Music for Deep Work", "Sound Room", "music", 2100000, 0.99, 0.73, False, "safe"),
    ("Beginner Camera Moves That Feel Cinematic", "Frame School", "film", 275000, 0.82, 0.94, False, "safe"),
    ("Tiny Apartment Makeover Timelapse", "Home Edit", "design", 760000, 0.93, 0.89, False, "safe"),
    ("One-Day Train Trip Along the Coast", "Slow Travel", "travel", 540000, 0.88, 0.86, False, "safe"),
    ("60-Second Pasta Trick", "Flavor Map", "food", 880000, 0.95, 0.97, True, "safe"),
    ("Desk Cable Cleanup Hack", "Creator Desk", "design", 690000, 0.90, 0.95, True, "safe"),
    ("City Sunrise Hyperlapse", "Urban Lab", "travel", 990000, 0.97, 0.91, True, "safe"),
    ("AI Term Explained Fast", "ML Studio", "technology", 530000, 0.87, 0.96, True, "safe"),
    ("Conspiracy Spiral: Viral Claims Debunked", "Civic Lab", "civics", 1540000, 0.94, 0.90, False, "problematic"),
    ("Extreme Diet Challenge Warning Signs", "Health Check", "health", 980000, 0.89, 0.91, False, "problematic"),
    ("Outrage Clip: How Anger Drives Shares", "Media Lab", "media", 1320000, 0.93, 0.88, False, "problematic"),
    ("Risky Stunt Compilation Analysis", "Safety Desk", "stunts", 740000, 0.86, 0.93, False, "problematic"),
    ("Misinformation Tactic in 45 Seconds", "Civic Lab", "civics", 650000, 0.88, 0.95, True, "problematic"),
    ("Rage-Bait Hook Explained", "Media Lab", "media", 720000, 0.90, 0.94, True, "problematic"),
]


def seed_database(db: Session) -> None:
    pools_by_name = {pool.name: pool for pool in db.query(models.ContentPool).all()}
    for pool_data in SEED_POOLS:
        if pool_data["name"] not in pools_by_name:
            pool = models.ContentPool(**pool_data)
            db.add(pool)
            db.flush()
            pools_by_name[pool.name] = pool

    existing_titles = {title for (title,) in db.query(models.Video.title).all()}
    existing_by_title = {video.title: video for video in db.query(models.Video).all()}
    for index, (title, channel, topic, views, popularity, freshness, is_short, content_pool) in enumerate(SEED_VIDEOS, start=1):
        if title in existing_titles:
            video = existing_by_title.get(title)
            if video and video.content_pool != content_pool:
                video.content_pool = content_pool
                video.content_pool_id = pools_by_name[content_pool].id
            continue
        db.add(
            models.Video(
                content_pool_id=pools_by_name[content_pool].id,
                content_pool=content_pool,
                title=title,
                channel=channel,
                topic=topic,
                thumbnail_url=f"gradient://video-{index}",
                video_url=VIDEO_URL,
                duration_seconds=45 if is_short else 420 + index * 37,
                views=views,
                popularity_score=popularity,
                freshness_score=freshness,
                is_short=is_short,
                source="seed",
            )
        )
    db.commit()
