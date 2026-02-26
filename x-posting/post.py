#!/usr/bin/env python3.11
"""Post to @GetPercept on X."""

import json
import sys
from requests_oauthlib import OAuth1Session

CREDS_PATH = "/Users/jarvis/.config/x-api/percept-credentials.json"

def post_tweet(text, reply_to=None):
    creds = json.load(open(CREDS_PATH))
    oauth = OAuth1Session(
        creds["consumer_key"],
        client_secret=creds["consumer_secret"],
        resource_owner_key=creds["access_token"],
        resource_owner_secret=creds["access_token_secret"],
    )
    payload = {"text": text}
    if reply_to:
        payload["reply"] = {"in_reply_to_tweet_id": reply_to}
    r = oauth.post("https://api.x.com/2/tweets", json=payload)
    if r.status_code == 201:
        data = r.json()["data"]
        print(f"✅ Posted: https://x.com/GetPercept/status/{data['id']}")
        return data
    else:
        print(f"❌ {r.status_code}: {r.text}")
        return None

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: post.py 'tweet text' [reply_to_id]")
        sys.exit(1)
    reply_id = sys.argv[2] if len(sys.argv) > 2 else None
    post_tweet(sys.argv[1], reply_id)
