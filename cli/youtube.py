"""What YouTube says about a video, through its public oEmbed endpoint.

No key and no account: oEmbed answers for any public video with its title and channel, and
refuses for one that is private or removed. That is the whole of what is asked of it.
"""

import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, unquote

_ENDPOINT = "https://www.youtube.com/oembed?format=json&url="
GONE = (400, 401, 403, 404)


def watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def channel_key(url: str) -> str:
    """A channel URL in one spelling: decoded, lower case, no trailing slash."""
    return unquote(url).strip().rstrip("/").lower().replace("://youtube.com", "://www.youtube.com")


def lookup(video_id: str, attempts: int = 4) -> dict:
    """{"status": 200, "title", "channel", "channelUrl"} or {"status": code}; 0 if unreachable."""
    request = urllib.request.Request(_ENDPOINT + quote(watch_url(video_id), safe=""),
                                     headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.load(response)
            return {"status": 200, "title": data.get("title"), "channel": data.get("author_name"),
                    "channelUrl": data.get("author_url")}
        except urllib.error.HTTPError as e:
            if e.code in GONE:
                return {"status": e.code}
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            pass
        time.sleep(2 + 3 * attempt)
    return {"status": 0}


def lookup_many(video_ids, workers: int = 4) -> dict:
    """Four at a time: more than that and YouTube starts dropping connections."""
    ids = list(dict.fromkeys(video_ids))
    with ThreadPoolExecutor(workers) as pool:
        return dict(zip(ids, pool.map(lookup, ids)))
