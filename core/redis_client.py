import redis
import json

redis_client = redis.Redis(
    host="localhost",
    port=6379,   # <-- This should probably be 6379
    db=0,
)
