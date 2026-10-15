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


def subtitles(video_id: str, lang: str = "en") -> dict:
    """{"status": "ok", "events": [{"t": seconds, "text"}]} from the subtitles a person wrote
    in `lang`, or {"status": "none" | "error", "reason"}.

    Only subtitles somebody wrote are taken. YouTube's own automatic captions are machine
    output: a quote copied from them would be a quote of the machine, not of the speaker.
    Needs yt-dlp, which reads YouTube the way its own player does; nothing is downloaded but
    the subtitle text.
    """
    import yt_dlp
    options = {"skip_download": True, "quiet": True, "no_warnings": True}
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(watch_url(video_id), download=False)
            tracks = (info.get("subtitles") or {}).get(lang) or []
            track = next((t for t in tracks if t.get("ext") == "json3"), None)
            if track is None:
                return {"status": "none", "reason": f"no {lang} subtitles written by a person"}
            data = json.loads(ydl.urlopen(track["url"]).read().decode("utf-8"))
    except Exception as e:  # yt-dlp raises many kinds; any of them means "not this time"
        return {"status": "error", "reason": str(e).splitlines()[0][:200]}
    events = []
    for event in data.get("events", []):
        line = "".join(seg.get("utf8", "") for seg in event.get("segs") or []).replace("\n", " ").strip()
        if line:
            events.append({"t": event.get("tStartMs", 0) // 1000, "text": line})
    if not events:
        return {"status": "none", "reason": "the subtitle track is empty"}
    return {"status": "ok", "events": events}


def lookup_many(video_ids, workers: int = 4) -> dict:
    """Four at a time: more than that and YouTube starts dropping connections."""
    ids = list(dict.fromkeys(video_ids))
    with ThreadPoolExecutor(workers) as pool:
        return dict(zip(ids, pool.map(lookup, ids)))
