import redis
import os
from dotenv import load_dotenv

load_dotenv()

# Connect to Memurai (Live Memory)
# This uses the REDIS_URL from your .env file
r = redis.from_url(os.getenv("REDIS_URL"), decode_responses=True) #provide link with memurai,res=true return data as string instead of byte

def set_context(user_id: str, key: str, value: str, expiry: int = 300):
    """
    Stores temporary data (e.g., student name) for a specific user.
    'expiry' is in seconds (default 5 minutes).
    """
    full_key = f"user:{user_id}:{key}" #for multikiosk if a&b are diffrent kiosk their data wont get mixed up as key are distinct
    r.set(full_key, value, ex=expiry)#default seesion erased after 5 mins
    print(f" Memory Updated: {full_key} -> {value}")

def get_context(user_id: str, key: str):
    """Retrieves temporary data for a specific user."""
    full_key = f"user:{user_id}:{key}"
    return r.get(full_key)

def clear_context(user_id: str):
    """Clears all live memory for a user (e.g., when they walk away)."""
    keys = r.keys(f"user:{user_id}:*")
    if keys:
        r.delete(*keys)
        print(f" Memory Cleared for user: {user_id}")