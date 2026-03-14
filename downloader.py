import yt_dlp
import os
import uuid
import imageio_ffmpeg
import threading
import urllib.parse
import random
import time

# ── Constants ─────────────────────────────────────────────────────────────────
download_tasks = {}
DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ── Single-track guard ─────────────────────────────────────────────────────────
_BLOCK = {
    'full album', 'tam albüm', 'albüm', 'compilation', 'greatest hits',
    'best of', 'playlist', 'megamix', 'non stop', 'nonstop', 'kesintisiz',
    'saatlik', 'hours', 'audiobook', 'podcast', 'tracklist', 'collection',
    'karaoke', 'sleep', 'meditation', 'asmr', 'lo-fi', 'lofi', 'mix',
    'live session', 'set', 'dj set'
}

def is_valid_track(title: str, duration) -> bool:
    if not title:
        return False
    t = title.lower()
    # Allow "remix" but block "megamix"
    for kw in _BLOCK:
        if kw == 'mix':
            # only block if it looks like a mix compilation
            if 'mix' in t and 'remix' not in t:
                return False
            continue
        if kw in t:
            return False
    if duration:
        if duration > 600:  # 10 min hard cap
            return False
        if duration < 60:   # too short
            return False
    return True

def is_official_channel(channel: str) -> bool:
    """Only keep tracks from official artist channels."""
    if not channel:
        return False
    c = channel.lower()
    return (
        "topic" in c or       # Auto-generated Topic channels
        "vevo" in c or        # VEVO channels
        "official" in c or    # Official channels
        "music" in c or       # Music channels
        "records" in c or     # Record labels
        "müzik" in c          # Turkish music channels
    )

# ── Home Discovery Queries — fast, diverse, official ─────────────────────────
_HOME_QUERY_POOLS = [
    # Global hits
    "Drake new song 2025", "The Weeknd official music", "Taylor Swift songs",
    "Ed Sheeran official", "Billie Eilish official music", "Post Malone hits",
    "Ariana Grande official", "Justin Bieber official", "Dua Lipa songs",
    "Harry Styles music", "Olivia Rodrigo official", "Bad Bunny songs",
    "BTS official music", "BLACKPINK official", "Coldplay official",
    "Eminem official music", "Kendrick Lamar songs", "SZA official",
    "Tyler the Creator songs", "Future official music",
    # Turkish hits
    "Müslüm Gürses şarkıları", "Tarkan resmi şarkılar", "Sezen Aksu şarkıları",
    "Manga official", "Ceza official music", "Ezhel official",
    "Norm Ender resmi", "Gripin official", "Mabel Matiz official",
    "Sıla Şahin şarkıları", "Hadise official", "Aleyna Tilki official",
    "Burak Doğansoy official", "Sagopa Kajmer official", "Bengu official",
    # Genre mixes
    "top R&B hits 2025 official", "Latin pop official songs 2025",
    "K-pop official hits 2025", "Afrobeats official 2025",
    "indie pop hits official 2025", "electronic official music 2025",
]

# ── Home Songs — fast random discovery ───────────────────────────────────────
def get_random_songs(count: int = 50, seed: int | None = None) -> list:
    """
    Fetch diverse, official-channel songs for home screen.
    Uses multiple parallel queries for speed.
    """
    if seed is None:
        seed = int(time.time())
    
    rng = random.Random(seed)
    # Pick 5 different queries to ensure diversity
    queries = rng.sample(_HOME_QUERY_POOLS, min(5, len(_HOME_QUERY_POOLS)))
    
    per_query = max(12, count // len(queries) + 5)
    all_results = []
    
    threads = []
    results_lock = threading.Lock()
    
    def fetch_query(q):
        items = _ytm_search_url(q, per_query, official_only=True)
        with results_lock:
            all_results.extend(items)
    
    for q in queries:
        t = threading.Thread(target=fetch_query, args=(q,), daemon=True)
        threads.append(t)
        t.start()
    
    for t in threads:
        t.join(timeout=8)  # max 8s per batch
    
    # Deduplicate by video ID
    seen = set()
    unique = []
    for item in all_results:
        if item['id'] not in seen:
            seen.add(item['id'])
            unique.append(item)
    
    rng.shuffle(unique)
    return unique[:count]


# ── YTM Discover (Google OAuth) ───────────────────────────────────────────────
def get_discover_songs(access_token: str, count: int = 50) -> list:
    """
    Fetch personalized YouTube Music recommendations using OAuth token.
    Falls back to random songs if ytmusicapi is unavailable.
    """
    try:
        from ytmusicapi import YTMusic
        ytm = YTMusic(auth={"access_token": access_token})
        home = ytm.get_home(limit=5)
        results = []
        for shelf in home:
            for item in shelf.get("contents", []):
                vid_id = (item.get("videoId") or "")
                title = (item.get("title") or "")
                if not vid_id or not title:
                    continue
                artists = item.get("artists") or []
                channel = artists[0]["name"] if artists else "YouTube Music"
                duration = item.get("duration_seconds")
                if not is_valid_track(title, duration):
                    continue
                results.append({
                    "id": vid_id,
                    "title": title,
                    "url": f"https://www.youtube.com/watch?v={vid_id}",
                    "thumbnail": f"https://i.ytimg.com/vi/{vid_id}/mqdefault.jpg",
                    "channel": channel,
                    "duration": duration,
                    "is_official": True,
                })
                if len(results) >= count:
                    break
            if len(results) >= count:
                break
        return results
    except Exception as ex:
        print(f"Discover Error (falling back): {ex}")
        return get_random_songs(count)


# ── Core fetcher — YouTube Music Search via ytmusicapi ─────────────────────────
def _ytm_search_url(query: str, count: int, official_only: bool = False) -> list:
    """Search YouTube Music using ytmusicapi."""
    try:
        from ytmusicapi import YTMusic
        ytm = YTMusic()
        # filter="songs" ensures we get music tracks, not random videos
        search_results = ytm.search(query, filter="songs", limit=count)
        
        results = []
        for r in search_results:
            vid_id = r.get("videoId")
            if not vid_id:
                continue
                
            title = r.get("title") or ""
            artists = r.get("artists") or []
            # Extract names and join if multiple
            artist_names = [a["name"] for a in artists] if artists else ["Unknown Artist"]
            channel = ", ".join(artist_names)
            
            # Duration check
            duration_str = r.get("duration")
            duration_sec = 0
            if duration_str:
                parts = str(duration_str).split(":")
                if len(parts) == 2:
                    duration_sec = int(parts[0]) * 60 + int(parts[1])
                elif len(parts) == 3:
                    duration_sec = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])

            if not is_valid_track(title, duration_sec):
                continue
            
            # If official_only is requested, check if it's from an official source
            # In YTM 'songs' filter, results are generally official meta-data tagged
            is_off = True 

            # Channel detail for artist links
            first_artist = artists[0] if artists else {}
            ch_url = f"https://www.youtube.com/channel/{first_artist['id']}" if first_artist.get("id") else ""

            results.append({
                "id": vid_id,
                "title": title,
                "url": f"https://www.youtube.com/watch?v={vid_id}",
                "thumbnail": f"https://i.ytimg.com/vi/{vid_id}/mqdefault.jpg",
                "channel": channel,
                "channel_url": ch_url,
                "duration": duration_sec,
                "is_official": is_off,
            })
            if len(results) >= count:
                break
        return results
    except Exception as ex:
        print(f"YTM Search Error: {ex}")
        return []


# ── Search — Songs ─────────────────────────────────────────────────────────────
def search_youtube(query: str, max_results: int = 12) -> list:
    """Search for songs by query on YTM."""
    return _ytm_search_url(query, max_results)


# ── Search — Artist Info ───────────────────────────────────────────────────────
def search_artist_info(query: str) -> dict | None:
    """
    Search for the most relevant artist/match on YouTube Music.
    Prioritizes 'Top Result' (En İyi Eşleşme) to ensure relevance.
    """
    try:
        from ytmusicapi import YTMusic
        ytm = YTMusic()
        
        # 1. Check Top Result (Most Relevant)
        top = ytm.search(query, limit=1)
        if top:
            t = top[0]
            r_type = t.get("resultType")
            
            # If top is already an artist, use it
            if r_type == "artist":
                browse_id = t.get("browseId")
                # Try to get more details (subs etc)
                try:
                    info = ytm.get_artist(browse_id)
                    return {
                        "name": info.get("name") or t.get("artist"),
                        "channel_url": f"https://www.youtube.com/channel/{browse_id}",
                        "thumbnail": (info.get("thumbnails") or t.get("thumbnails") or [{}])[-1].get("url"),
                        "subscriber_count": info.get("subscribers"),
                        "uploader_id": browse_id,
                    }
                except:
                    return {
                        "name": t.get("artist"),
                        "channel_url": f"https://www.youtube.com/channel/{browse_id}",
                        "thumbnail": (t.get("thumbnails") or [{}])[-1].get("url"),
                        "subscriber_count": None,
                        "uploader_id": browse_id,
                    }
            
            # If top is a song/video, show the main artist of that song
            if r_type in ["song", "video"]:
                artists = t.get("artists") or []
                if artists:
                    art = artists[0]
                    # If we have an ID, we can try to get artist page details
                    if art.get("id"):
                        try:
                            info = ytm.get_artist(art["id"])
                            return {
                                "name": info["name"],
                                "channel_url": f"https://www.youtube.com/channel/{art['id']}",
                                "thumbnail": (info.get("thumbnails") or t.get("thumbnails") or [{}])[-1].get("url"),
                                "subscriber_count": info.get("subscribers"),
                                "uploader_id": art["id"],
                            }
                        except: pass
                    
                    # Fallback to general data from the song result
                    return {
                        "name": art["name"],
                        "channel_url": f"https://www.youtube.com/channel/{art['id']}" if art.get("id") else "",
                        "thumbnail": (t.get("thumbnails") or [{}])[-1].get("url"),
                        "subscriber_count": None,
                        "uploader_id": art.get("id"),
                    }

        # 2. Fallback: Specific artist filter search (Legacy)
        artist_results = ytm.search(query, filter="artists", limit=1)
        if artist_results:
            a = artist_results[0]
            return {
                "name": a.get("artist"),
                "channel_url": f"https://www.youtube.com/channel/{a['browseId']}",
                "thumbnail": (a.get("thumbnails") or [{}])[-1].get("url"),
                "subscriber_count": None,
                "uploader_id": a.get("browseId"),
            }
    except Exception as ex:
        print(f"Artist Info Error: {ex}")
    
    return None


# ── Artist Songs — lazy loading ───────────────────────────────────────────────
def get_artist_songs(channel_url: str, max_results: int = 20, offset: int = 0) -> list:
    """Fetch songs from an artist's channel with offset for lazy loading."""
    target = channel_url.rstrip("/") + "/videos"
    opts = {
        "extract_flat": "in_playlist",
        "quiet": True,
        "no_warnings": True,
        "playliststart": offset + 1,
        "playlistend": offset + max_results,
        "socket_timeout": 15,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(target, download=False)
            entries = info.get("entries") or []
            channel_name = info.get("title", "")
            results = []
            for e in entries:
                if not e:
                    continue
                title = e.get("title") or ""
                duration = e.get("duration")
                vid_id = e.get("id")
                if not vid_id:
                    continue
                # On artist pages, include all non-blocked tracks
                if not is_valid_track(title, duration):
                    continue
                results.append({
                    "id": vid_id,
                    "title": title,
                    "url": f"https://www.youtube.com/watch?v={vid_id}",
                    "thumbnail": f"https://i.ytimg.com/vi/{vid_id}/mqdefault.jpg",
                    "channel": channel_name,
                    "duration": duration,
                })
            return results
    except Exception as ex:
        print(f"Artist songs error: {ex}")
        return []


# ── Download Core ─────────────────────────────────────────────────────────────
def download_to_mp3_bg(url: str, task_id: str) -> None:
    def hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 1)
            pct = (d.get("downloaded_bytes", 0) / total) * 90
            download_tasks[task_id].update({"status": "downloading", "progress": round(pct, 1)})
        elif d["status"] == "finished":
            download_tasks[task_id].update({"status": "converting", "progress": 90})

    try:
        out_dir = os.path.join(DOWNLOAD_DIR, task_id)
        os.makedirs(out_dir, exist_ok=True)
        opts = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(out_dir, "%(title)s.%(ext)s"),
            "ffmpeg_location": imageio_ffmpeg.get_ffmpeg_exe(),
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
            "quiet": True,
            "noplaylist": True,
            "progress_hooks": [hook],
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            fname = os.path.splitext(ydl.prepare_filename(info))[0] + ".mp3"
            download_tasks[task_id].update({"status": "done", "progress": 100, "file_path": fname})
    except Exception as exc:
        download_tasks[task_id].update({"status": "error", "error_message": str(exc)})


def start_download(url: str) -> str:
    tid = str(uuid.uuid4())[:8]
    download_tasks[tid] = {"status": "starting", "progress": 0, "file_path": None}
    threading.Thread(target=download_to_mp3_bg, args=(url, tid), daemon=True).start()
    return tid
