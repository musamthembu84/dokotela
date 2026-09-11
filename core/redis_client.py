import redis

redis_client = redis.Redis(
    host="10.0.3.206",
    port=6379,
    db=0,
)