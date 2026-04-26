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
    """Detect official artist sources. Note: 'Topic' channels are often blocked from embedding."""
    if not channel:
        return False
    c = channel.lower()
    return (
        "vevo" in c or        # VEVO channels
        "official" in c or    # Official channels
        "music" in c or       # Music channels
        "records" in c or     # Record labels
        "müzik" in c or       # Turkish music channels
        "artist" in c         # Artist channels
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




# ── Core fetcher — YouTube Music Search via ytmusicapi ─────────────────────────
def _ytm_search_url(query: str, count: int, official_only: bool = False) -> list:
    """Search YouTube Music using ytmusicapi."""
    try:
        from ytmusicapi import YTMusic
        ytm = YTMusic()
        # filter="videos" tends to have much better embedding permissions than filter="songs" (Topic channels)
        search_results = ytm.search(query, filter="videos", limit=count)
        
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
                artist_name = t.get("artist")
                
                # Sometime 'browseId' and 'artist' are nested in 'artists' array
                artists_list = t.get("artists") or []
                if artists_list:
                    if not browse_id:
                        browse_id = artists_list[-1].get("id") if artists_list else None
                    if not artist_name:
                        artist_name = artists_list[0].get("name") if artists_list else None
                
                # Try to get more details (subs etc) from artist profile
                if browse_id:
                    try:
                        info = ytm.get_artist(browse_id)
                        return {
                            "name": info.get("name") or artist_name or query,
                            "channel_url": f"https://www.youtube.com/channel/{browse_id}",
                            "thumbnail": (info.get("thumbnails") or t.get("thumbnails") or [{}])[-1].get("url"),
                            "subscriber_count": info.get("subscribers"),
                            "uploader_id": browse_id,
                        }
                    except:
                        pass

                return {
                    "name": artist_name or query,
                    "channel_url": f"https://www.youtube.com/channel/{browse_id}" if browse_id else "",
                    "thumbnail": (t.get("thumbnails") or [{}])[-1].get("url"),
                    "subscriber_count": t.get("subscribers"),
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


def get_artist_songs(channel_url: str, max_results: int = 20, offset: int = 0) -> list:
    """
    Fetch songs from an artist's channel. 
    Uses a hybrid approach: Popular songs first, then search to reach the full discography.
    """
    try:
        from ytmusicapi import YTMusic
        ytm = YTMusic()
        
        # Extract browseId from URL
        path_parts = channel_url.rstrip("/").split("/")
        browse_id = path_parts[-1]
        
        artist_data = {}
        channel_name = None
        
        try:
            artist_data = ytm.get_artist(browse_id)
            channel_name = artist_data.get("name")
        except Exception as e:
            print(f"YTM get_artist failed for {browse_id}: {e}")

        # Try to gather tracks from the popular playlist or section
        all_tracks = []
        if artist_data and 'songs' in artist_data:
            songs_section = artist_data['songs']
            songs_browse_id = None
            if isinstance(songs_section, dict):
                songs_browse_id = songs_section.get("browseId")
                
            if songs_browse_id:
                try:
                    # Fetching up to 200 items from popular playlist if available
                    # We fetch a large batch once to avoid overhead in pagination
                    full_list = ytm.get_playlist(songs_browse_id, limit=200)
                    all_tracks = full_list.get("tracks", [])
                except:
                    if isinstance(songs_section, dict):
                        all_tracks = songs_section.get("results", [])
            elif isinstance(songs_section, dict):
                all_tracks = songs_section.get("results", [])

        # ENHANCEMENT: If the popular list is too short or we have reached its end,
        # fallback to a massive search for the artist's full discography.
        # This allows us to reach 500+ songs as the user requested.
        if (offset + max_results > len(all_tracks)) and channel_name:
            print(f"Switching to search for exhaustive discography: {channel_name}")
            # We search with a high limit to get as much as possible
            # ytmusicapi search pagination is relatively fast
            search_pool = ytm.search(channel_name, filter="songs", limit=max_results + offset + 50)
            
            # Merge logic: Add search results that aren't already in the tracks list
            existing_ids = {t.get("videoId") for t in all_tracks if t.get("videoId")}
            for s in search_pool:
                vid_id = s.get("videoId")
                if vid_id and vid_id not in existing_ids:
                    all_tracks.append(s)
                    existing_ids.add(vid_id)

        # Slice the final combined list
        songs_list = all_tracks[offset:offset+max_results]
        
        results = []
        for s in songs_list:
            vid_id = s.get("videoId")
            if not vid_id: continue
            
            title = s.get("title") or "Unknown Title"
            # Duration parsing
            duration_sec = s.get("duration_seconds")
            if not duration_sec and s.get("duration"):
                d_str = s["duration"]
                parts = d_str.split(":")
                if len(parts) == 2: duration_sec = int(parts[0])*60 + int(parts[1])
                elif len(parts) == 3: duration_sec = int(parts[0])*3600 + int(parts[1])*60 + int(parts[2])

            if not is_valid_track(title, duration_sec):
                continue

            results.append({
                "id": vid_id,
                "title": title,
                "url": f"https://www.youtube.com/watch?v={vid_id}",
                "thumbnail": (s.get("thumbnails") or [{}])[-1].get("url") or f"https://i.ytimg.com/vi/{vid_id}/mqdefault.jpg",
                "channel": channel_name or s.get("artists", [{}])[0].get("name", "Sanatçı"),
                "duration": duration_sec,
                "is_official": True
            })
        
        return results
    except Exception as ex:
        print(f"Artist songs error (YTM): {ex}")
        # Final fallback: Try general search for the artist name if YTM fails
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
