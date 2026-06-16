# add fields to Video model

duration_seconds = Column(Integer)
topic = Column(String)
content_pool = Column(String, default="unknown")
source = Column(String, default="youtube")
youtube_id = Column(String, unique=True)
