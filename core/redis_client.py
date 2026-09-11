import redis

from core.config import settings


redis_client = redis.Redis(
    host="dokotela-redis.7ctctb.0001.use1.cache.amazonaws.com",
    port=6379,
    db=0,
)