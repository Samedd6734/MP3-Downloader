import os
import secrets
import time
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.concurrency import run_in_threadpool
from downloader import (
    search_youtube, start_download, download_tasks,
    get_artist_songs, get_random_songs, get_discover_songs,
    search_artist_info,
)

app = FastAPI()
os.makedirs("static", exist_ok=True)

# ── Google OAuth Config ────────────────────────────────────────────────────────
GOOGLE_CLIENT_ID     = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
REDIRECT_URI         = os.environ.get("REDIRECT_URI", "http://localhost:8000/api/auth/google/callback")
OAUTH_SCOPE          = "openid email profile https://www.googleapis.com/auth/youtube.readonly"

# In-memory session store (dev only — replace with Redis/DB for production)
_sessions: dict[str, dict] = {}

# ── Home Songs Cache — ultra-fast serving via pre-fetch ───────────────────────
_home_cache: dict = {"songs": [], "fetched_at": 0, "seed": 0}
_HOME_CACHE_TTL = 90  # seconds before cache expires
_home_lock = False

async def _ensure_home_cache(force_new: bool = False) -> list:
    global _home_lock
    now = time.time()
    age = now - _home_cache["fetched_at"]
    
    if not force_new and _home_cache["songs"] and age < _HOME_CACHE_TTL:
        return _home_cache["songs"]
    
    if _home_lock:
        return _home_cache["songs"]  # Return stale while refreshing
    
    _home_lock = True
    try:
        seed = int(now)
        songs = await run_in_threadpool(get_random_songs, 50, seed)
        _home_cache.update({"songs": songs, "fetched_at": now, "seed": seed})
    finally:
        _home_lock = False
    
    return _home_cache["songs"]


# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/")
def read_index():
    return FileResponse("static/index.html")

app.mount("/static", StaticFiles(directory="static"), name="static")


# ── Home API ──────────────────────────────────────────────────────────────────
@app.get("/api/home")
async def home_api(request: Request, refresh: bool = False):
    """
    Returns random official songs for the home screen.
    ?refresh=true forces a new batch (different seed).
    If user is logged in, returns personalized discover songs.
    """
    # Check for logged-in user session
    session_id = request.cookies.get("session_id")
    if session_id and session_id in _sessions:
        user = _sessions[session_id]
        access_token = user.get("access_token", "")
        if access_token:
            try:
                songs = await run_in_threadpool(get_discover_songs, access_token, 50)
                return {"results": songs, "mode": "discover", "user": user.get("name")}
            except:
                pass  # Fall through to random

    songs = await _ensure_home_cache(force_new=refresh)
    import random
    if refresh:
        random.shuffle(songs)
    return {"results": songs, "mode": "explore"}


# ── Search API ────────────────────────────────────────────────────────────────
@app.get("/api/search")
async def search_api(q: str, max_results: int = 12):
    if not q:
        raise HTTPException(status_code=400, detail="Search query is required")
    try:
        results = await run_in_threadpool(search_youtube, q, max_results)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/search/artist")
async def search_artist_api(q: str):
    """Returns artist channel metadata for the artist card in search results."""
    if not q:
        raise HTTPException(status_code=400, detail="Artist query is required")
    try:
        artist = await run_in_threadpool(search_artist_info, q)
        return {"artist": artist}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Artist API ────────────────────────────────────────────────────────────────
@app.get("/api/artist")
async def artist_api(url: str, max_results: int = 20, offset: int = 0):
    if not url:
        raise HTTPException(status_code=400, detail="Channel URL is required")
    try:
        results = await run_in_threadpool(get_artist_songs, url, max_results, offset)
        return {"results": results, "offset": offset, "has_more": len(results) == max_results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Download API ──────────────────────────────────────────────────────────────
@app.get("/api/download")
def download_init_api(url: str):
    if not url:
        raise HTTPException(status_code=400, detail="Video URL is required")
    try:
        task_id = start_download(url)
        return {"task_id": task_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/progress")
def download_progress_api(task_id: str):
    if task_id not in download_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return download_tasks[task_id]


@app.get("/api/file")
def download_file_api(task_id: str):
    if task_id not in download_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    task = download_tasks[task_id]
    if task["status"] != "done":
        raise HTTPException(status_code=400, detail="File not ready")
    file_path = task["file_path"]
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=500, detail="File could not be found.")
    filename = os.path.basename(file_path)
    return FileResponse(path=file_path, filename=filename, media_type="audio/mpeg")


# ── Google OAuth ──────────────────────────────────────────────────────────────
@app.get("/api/auth/google/start")
def google_auth_start():
    """Redirect to Google OAuth consent screen."""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=501,
            detail="Google OAuth not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET env vars."
        )
    state = secrets.token_urlsafe(16)
    params = {
        "client_id":     GOOGLE_CLIENT_ID,
        "redirect_uri":  REDIRECT_URI,
        "response_type": "code",
        "scope":         OAUTH_SCOPE,
        "access_type":   "offline",
        "prompt":        "select_account",
        "state":         state,
    }
    from urllib.parse import urlencode
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return RedirectResponse(url)


@app.get("/api/auth/google/callback")
async def google_auth_callback(code: str, state: str, response: Response):
    """Handle Google OAuth callback, create session."""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=501, detail="Google OAuth not configured.")
    
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            # Exchange code for tokens
            token_resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code":          code,
                    "client_id":     GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "redirect_uri":  REDIRECT_URI,
                    "grant_type":    "authorization_code",
                }
            )
            tokens = token_resp.json()
            access_token = tokens.get("access_token", "")
            
            # Get user info
            user_resp = await client.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            user_info = user_resp.json()
        
        session_id = secrets.token_urlsafe(32)
        _sessions[session_id] = {
            "access_token": access_token,
            "refresh_token": tokens.get("refresh_token", ""),
            "name":    user_info.get("name", "Kullanıcı"),
            "email":   user_info.get("email", ""),
            "picture": user_info.get("picture", ""),
        }
        
        resp = RedirectResponse("/")
        resp.set_cookie("session_id", session_id, httponly=True, samesite="lax", max_age=86400 * 30)
        return resp
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OAuth error: {e}")


@app.get("/api/auth/status")
def auth_status(request: Request):
    """Returns current login state."""
    session_id = request.cookies.get("session_id")
    if session_id and session_id in _sessions:
        user = _sessions[session_id]
        return {
            "logged_in": True,
            "name":    user.get("name"),
            "picture": user.get("picture"),
            "email":   user.get("email"),
        }
    return {"logged_in": False}


@app.post("/api/auth/logout")
def auth_logout(request: Request, response: Response):
    """Clear session."""
    session_id = request.cookies.get("session_id")
    if session_id in _sessions:
        del _sessions[session_id]
    response.delete_cookie("session_id")
    return {"ok": True}
