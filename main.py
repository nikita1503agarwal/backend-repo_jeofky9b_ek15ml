import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import requests

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI Backend!"}


@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        from database import db

        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"

            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"

    except ImportError:
        response["database"] = "❌ Database module not found (run enable-database first)"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    import os
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


def iso8601_to_hms(duration: str) -> str:
    # Minimal ISO8601 duration (PT#H#M#S) parser to H:MM:SS or MM:SS
    import re
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
    if not m:
        return "0:00"
    h = int(m.group(1) or 0)
    mi = int(m.group(2) or 0)
    s = int(m.group(3) or 0)
    total = h * 3600 + mi * 60 + s
    hh = total // 3600
    mm = (total % 3600) // 60
    ss = total % 60
    if hh:
        return f"{hh}:{mm:02d}:{ss:02d}"
    return f"{mm}:{ss:02d}"


@app.get("/api/youtube/search")
def youtube_search(q: str = Query(..., min_length=1), maxResults: int = Query(12, ge=1, le=25)):
    api_key = os.getenv("YT_API_KEY") or os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="YouTube API key not configured")

    # Search videos
    search_url = "https://www.googleapis.com/youtube/v3/search"
    s_params = {
        "part": "snippet",
        "type": "video",
        "maxResults": maxResults,
        "q": q,
        "key": api_key,
    }
    s_res = requests.get(search_url, params=s_params, timeout=15)
    if s_res.status_code != 200:
        raise HTTPException(status_code=s_res.status_code, detail=s_res.text)
    s_data = s_res.json()

    ids: List[str] = [item["id"]["videoId"] for item in s_data.get("items", []) if item.get("id", {}).get("videoId")]
    if not ids:
        return {"query": q, "items": []}

    # Fetch details for stats and duration
    videos_url = "https://www.googleapis.com/youtube/v3/videos"
    v_params = {
        "part": "snippet,contentDetails,statistics",
        "id": ",".join(ids),
        "key": api_key,
    }
    v_res = requests.get(videos_url, params=v_params, timeout=15)
    if v_res.status_code != 200:
        raise HTTPException(status_code=v_res.status_code, detail=v_res.text)
    v_data = v_res.json()

    details = {}
    for it in v_data.get("items", []):
        vid = it.get("id")
        snippet = it.get("snippet", {})
        stats = it.get("statistics", {})
        cd = it.get("contentDetails", {})
        thumbs = snippet.get("thumbnails", {})
        best_thumb = thumbs.get("maxres") or thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {}
        details[vid] = {
            "id": vid,
            "title": snippet.get("title"),
            "channel": snippet.get("channelTitle"),
            "publishedAt": snippet.get("publishedAt"),
            "thumb": best_thumb.get("url"),
            "duration": iso8601_to_hms(cd.get("duration", "PT0S")),
            "views": stats.get("viewCount"),
        }

    items = [details[i] for i in ids if i in details]
    return {"query": q, "items": items}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
