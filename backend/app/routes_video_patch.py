
@router.get("/videos")
def get_videos(topic: str = None):
    q = db.query(Video)

    if topic:
        q = q.filter(Video.topic == topic)

    return q.limit(50).all()
