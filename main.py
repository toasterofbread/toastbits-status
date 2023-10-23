import os
import traceback
from waitress import serve
from flask import Flask, Response, request
from supabase import create_client, Client
from datetime import datetime, timezone
import json
import requests

STATUS_LIFETIMES_S: dict[str, int] = {
    "listening_to": 60 * 10
}
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:105.0) Gecko/20100101 Firefox/105.0"
SUPABASE_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"

supabase_url: str = os.environ.get("SUPABASE_URL")
supabase_key: str = os.environ.get("SUPABASE_KEY")

app = Flask(__name__)
app.url_map.strict_slashes = False

def _getNow():
    return datetime.utcnow()

def _getYoutubeVideoInfo(video_id: str, hl: str = "ja"):
    r = requests.post(
        "https://music.youtube.com/youtubei/v1/player?key=AIzaSyC9XL3ZjWddXya6X74dJoCTL-WEYFDNX30&prettyPrint=false",
        json = { 
            "context": {
                "client":{
                    "hl": hl,
                    "platform": "DESKTOP",
                    "clientName": "WEB_REMIX",
                    "clientVersion": "1.20230306.01.00",
                    "userAgent": USER_AGENT,
                    "acceptHeader": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
                },
                "user": {}
            },
            "videoId": video_id
        }
    )
    r.raise_for_status()

    data = r.json()
    details = data["videoDetails"]

    ret = {
        "youtube_video_id": details["videoId"],
        "title": details["title"],
        "channel_name": details["author"],
        "channel_id": details["channelId"],
        "thumbnails": details["thumbnail"]["thumbnails"],
        "duration_seconds": details["lengthSeconds"],
        "view_count": details["viewCount"]
    }

    return ret

def _getStatusIfInLifetime(key: str):
    supabase: Client = create_client(supabase_url, supabase_key)
    
    status: dict = supabase.table("status").select("value", "updated_at").eq("id", key).execute().data[0]
    updated_at = datetime.strptime(status["updated_at"], SUPABASE_TIME_FORMAT)

    age = (_getNow() - updated_at).total_seconds()
    if age > STATUS_LIFETIMES_S[key]:
        return None

    status["age"] = age
    return status

def _setStatus(key: str, value):
    supabase: Client = create_client(supabase_url, supabase_key)
    supabase.table("status").update({"value": value, "updated_at": _getNow().strftime(SUPABASE_TIME_FORMAT)}).eq("id", key).execute()

@app.route("/")
def status():
    return "Nothing here!"

def _getListeningTo():
    data = _getStatusIfInLifetime("listening_to")

    if data is None:
        return None

    if "youtube_video_id" in data["value"]:
        data["youtube_video_id"] = data["value"]["youtube_video_id"]
    else:
        return None

    data.pop("value")
    return data

@app.route("/song", methods = ["GET", "POST", "DELETE"])
def song():
    try:
        if request.method == "GET":
            return Response(json.dumps(_getListeningTo()), mimetype = "application/json")
        
        elif request.method == "POST":
            data = request.json

            if len(data) == 0:
                _setStatus("listening_to", {})
            elif "youtube_video_id" in data:
                _setStatus("listening_to", {"youtube_video_id": data["youtube_video_id"]})
            else:
                return "Unknown listening_to video key (expected 'youtube_video_id')", 400

        elif request.method == "DELETE":
            _setStatus("listening_to", {})
            
        else:
            return f"Unsupported method '{request.method}'", 405

    
    except Exception:
        tb = traceback.format_exc()
        print(tb)
        return str(tb), 500

    return "OK"

@app.route("/song/info")
def songInfo():
    try:
        data = _getListeningTo()
        if data is None:
            return json.dumps(None)
        
        if "youtube_video_id" in data:
            video_info = _getYoutubeVideoInfo(data["youtube_video_id"])
        else:
            return json.dumps(None)

        data.update(video_info)
        return Response(json.dumps(data), mimetype = "application/json")
    
    except Exception:
        tb = traceback.format_exc()
        print(tb)
        return str(tb), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8090))
    print(f"Serving on port {port}...")
    serve(app = app, host = "0.0.0.0", port = port)
