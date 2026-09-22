# ─── eventlet monkey-patch (MUST be first import for Railway/gunicorn + SocketIO) ─
try:
    import eventlet
    eventlet.monkey_patch()
except ImportError:
    pass  # Local dev without eventlet is fine

import os
import re
import sys
import json
import uuid
import time
import random
import hashlib
import shutil
import base64
import cv2
import numpy as np
from PIL import Image
import io

from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from bson import ObjectId, json_util
import pymongo
import yaml
import datetime
import urllib.request

app = Flask(__name__, static_folder="uploads", static_url_path="/uploads")
async_mode = "eventlet" if "eventlet" in sys.modules else None
socketio = SocketIO(app, cors_allowed_origins="*", async_mode=async_mode)

# ─── Configuration ─────────────────────────────────────────────────────────────
PENDING_DIR = "pending_dataset"
CLASS_MAPPING_FILE = os.path.join(PENDING_DIR, "class_mapping.json")
REJECTION_LOG_FILE = os.path.join(PENDING_DIR, "rejection_log.json")
EXPANDED_DATASET_DIR = "expanded_dataset"

os.makedirs(PENDING_DIR, exist_ok=True)
os.makedirs("temp_uploads", exist_ok=True)
os.makedirs("models", exist_ok=True)
os.makedirs(os.path.join("uploads", "candidates"), exist_ok=True)

if not os.path.exists(CLASS_MAPPING_FILE):
    default_mapping = {
        "Khafre-Pyramid": 0,
        "Mask-of-Tutankhamun": 1,
        "Sphinx": 2
    }
    with open(CLASS_MAPPING_FILE, 'w') as f:
        json.dump(default_mapping, f, indent=2)

# ─── Load MongoDB Atlas Credentials ──────────────────────────────────────────
def get_mongo_uri():
    env_uri = os.environ.get("MONGODB_URI")
    if env_uri:
        return env_uri
    paths = [
        "atlas-credentials.env",
        "../atlas-credentials.env",
        os.path.join(os.path.dirname(__file__), "atlas-credentials.env"),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "atlas-credentials.env")),
        ".env",
        "../.env"
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                with open(p, "r") as f:
                    for line in f:
                        match = re.match(r'^\s*MONGODB_URI\s*=\s*["\']?(.*?)["\']?\s*$', line)
                        if match:
                            return match.group(1).strip()
            except Exception as e:
                print(f"[WARNING] Error reading credentials file {p}: {e}")
    return "mongodb+srv://mahmoudmohamed114_db_user:ZQ4jERdG5SXrdBLs@graduationcluster.6umeau9.mongodb.net/heritage_social?retryWrites=true&w=majority"

db_uri = get_mongo_uri()
print(f"[INFO] Connecting to MongoDB: {db_uri}")
try:
    mongo_client = pymongo.MongoClient(
        db_uri,
        serverSelectionTimeoutMS=15000,
        connectTimeoutMS=15000,
        tls=True,
        tlsAllowInvalidCertificates=True
    )
    db = mongo_client["heritage_social"]
    # Check connection
    mongo_client.admin.command('ping')
    print("[SUCCESS] MongoDB connected successfully!")
    use_mongodb = True
except Exception as e:
    print(f"[WARNING] MongoDB Atlas is unreachable. Running in offline/mock database mode. Error: {e}")
    use_mongodb = False
    # Mock databases
    class MockCollection:
        def __init__(self, data=None):
            self.data = list(data) if data else []
        def find(self, query=None, *args, **kwargs):
            results = self.data
            if query:
                filtered = []
                for d in results:
                    match = True
                    for k, v in query.items():
                        if k == "$or" and isinstance(v, list):
                            or_match = False
                            for subq in v:
                                sub_match = True
                                for sub_k, sub_v in subq.items():
                                    val = d.get(sub_k, "")
                                    regex_obj = None
                                    if isinstance(sub_v, dict) and "$regex" in sub_v:
                                        regex_obj = sub_v["$regex"]
                                    elif hasattr(sub_v, "search") or hasattr(sub_v, "pattern"):
                                        regex_obj = sub_v
                                        
                                    if regex_obj is not None:
                                        pattern = getattr(regex_obj, "pattern", str(regex_obj))
                                        if not re.search(pattern, str(val), re.IGNORECASE):
                                            sub_match = False
                                            break
                                    elif val != sub_v:
                                        sub_match = False
                                        break
                                if sub_match:
                                    or_match = True
                                    break
                            if not or_match:
                                match = False
                                break
                        elif isinstance(v, dict) and "$regex" in v:
                            pattern = getattr(v["$regex"], "pattern", str(v["$regex"]))
                            if not re.search(pattern, str(d.get(k, "")), re.IGNORECASE):
                                match = False
                                break
                        elif isinstance(v, dict) and "$in" in v:
                            if d.get(k) not in v["$in"]:
                                match = False
                                break
                        elif isinstance(v, dict) and "$exists" in v:
                            if (k in d) != v["$exists"]:
                                match = False
                                break
                        elif d.get(k) != v:
                            match = False
                            break
                    if match:
                        filtered.append(d)
                results = filtered
            
            # Allow chaining .sort()
            class MockCursor(list):
                def sort(self, *s_args, **s_kwargs):
                    return self
            return MockCursor(results)
            
        def find_one(self, query=None, *args, **kwargs):
            res = self.find(query)
            return res[0] if len(res) > 0 else None
            
        def insert_one(self, doc):
            doc_copy = dict(doc)
            if "_id" not in doc_copy:
                doc_copy["_id"] = ObjectId()
            self.data.append(doc_copy)
            return type('obj', (object,), {'inserted_id': doc_copy["_id"]})
            
        def delete_many(self, query):
            count = len(self.data)
            self.data = []
            return type('obj', (object,), {'deleted_count': count})
            
        def update_one(self, query, update, **kwargs):
            doc = self.find_one(query)
            if doc and "$set" in update:
                doc.update(update["$set"])
            return type('obj', (object,), {'modified_count': 1 if doc else 0})
            
        def find_one_and_update(self, query, update, **kwargs):
            doc = self.find_one(query)
            if doc and "$set" in update:
                doc.update(update["$set"])
            return doc
    db = type('obj', (object,), {
        "locations": MockCollection([
            {"location_id": "L001", "name": "Giza Pyramids", "latitude": 29.9792, "longitude": 31.1342, "geohash": "stq4s3"},
            {"location_id": "L002", "name": "Egyptian Museum", "latitude": 30.0478, "longitude": 31.2336, "geohash": "stq4yw"}
        ]),
        "objects": MockCollection([
            {"object_id": "O001", "name": "Khafre Pyramid", "class_name": "Khafre-Pyramid", "location_id": "L001", "latitude": 29.9761, "longitude": 31.1308, "geohash": "stq4s2", "radius_m": 80},
            {"object_id": "O002", "name": "Mask of Tutankhamun", "class_name": "Mask-of-Tutankhamun", "location_id": "L002", "latitude": 30.0478, "longitude": 31.2336, "geohash": "stq4yw", "radius_m": 80},
            {"object_id": "O003", "name": "Sphinx", "class_name": "Sphinx", "location_id": "L001", "latitude": 29.9753, "longitude": 31.1376, "geohash": "stq4s8", "radius_m": 80},
            {"object_id": "O004", "name": "Great Pyramid", "class_name": "Great-Pyramid", "location_id": "L001", "latitude": 29.9792, "longitude": 31.1342, "geohash": "stq4s3", "radius_m": 80}
        ]),
        "posts": MockCollection([
            {"post_id": "P001", "content": "The Khafre Pyramid stands 136 meters tall!", "location_id": "L001", "object_id": "O001", "author": "Heritage Explorer"},
            {"post_id": "P002", "content": "The Khafre Pyramid is amazing!", "location_id": "L001", "object_id": "O001", "author": "Hassan Mostafa"},
            {"post_id": "P003", "content": "Beautiful view of the Sphinx at sunset!", "location_id": "L001", "object_id": "O003", "author": "Sara Ahmed"},
            {"post_id": "P004", "content": "The Mask of Tutankhamun is incredible — crafted in solid gold!", "location_id": "L002", "object_id": "O002", "author": "Archaeologist Dr. Ali"},
            {"post_id": "P005", "content": "The Great Pyramid of Khufu was built around 2560 BCE.", "location_id": "L001", "object_id": "O004", "author": "Heritage Explorer"},
            {"post_id": "P006", "content": "Great Pyramid is the oldest of the Seven Wonders of the World!", "location_id": "L001", "object_id": "O004", "author": "Tour Guide Mahmoud"}
        ]),
        "training_candidates": MockCollection([])
    })

# ─── Load YOLO Models (Memory-Optimized: ONLY YOLOv11) ──────────────────────
from ultralytics import YOLO

colab_y11_path = "models/yolo11_best.pt"
local_y11_path = "models/yolo11n.pt"

if os.path.exists(colab_y11_path):
    model_path_y11 = colab_y11_path
    is_custom_yolo11 = True
    is_yolo11_demo = False
elif os.path.exists(local_y11_path):
    model_path_y11 = local_y11_path
    is_custom_yolo11 = False
    is_yolo11_demo = False
else:
    model_path_y11 = "yolo11n.pt"
    is_custom_yolo11 = False
    is_yolo11_demo = False

model_path_v8 = model_path_y11
is_custom_yolov8 = is_custom_yolo11

print(f"[INFO] Single YOLO11 model configured: {model_path_y11} (custom={is_custom_yolo11})")

# ── Lazy singletons ──────────────────────────────────────────────────────────
_yolo_y11 = None

def get_yolo_y11():
    global _yolo_y11
    if _yolo_y11 is None:
        print(f"[INFO] Loading YOLO11 model into memory: {model_path_y11}")
        _yolo_y11 = YOLO(model_path_y11)
    return _yolo_y11

def get_yolo_v8():
    # Alias to YOLO11 to save RAM (no duplicate model loading)
    return get_yolo_y11()

def get_yolo_world():
    # Disabled to save 500MB+ RAM on 1GB instances
    return None

# ─── Geohash Utility (Pure Python, 100% self-contained) ────────────────────────
def geohash_encode(latitude, longitude, precision=6):
    lat_interval = (-90.0, 90.0)
    lon_interval = (-180.0, 180.0)
    geohash_alphabet = "0123456789bcdefghjkmnpqrstuvwxyz"
    
    geohash = []
    bits = 0
    ch = 0
    even = True
    
    while len(geohash) < precision:
        if even:
            mid = (lon_interval[0] + lon_interval[1]) / 2
            if longitude > mid:
                ch |= 1 << (4 - bits)
                lon_interval = (mid, lon_interval[1])
            else:
                lon_interval = (lon_interval[0], mid)
        else:
            mid = (lat_interval[0] + lat_interval[1]) / 2
            if latitude > mid:
                ch |= 1 << (4 - bits)
                lat_interval = (mid, lat_interval[1])
            else:
                lat_interval = (lat_interval[0], mid)
        
        even = not even
        if bits < 4:
            bits += 1
        else:
            geohash.append(geohash_alphabet[ch])
            bits = 0
            ch = 0
            
    return "".join(geohash)

def geohash_decode(geohash):
    geohash_alphabet = "0123456789bcdefghjkmnpqrstuvwxyz"
    lat_interval = (-90.0, 90.0)
    lon_interval = (-180.0, 180.0)
    even = True
    for char in geohash:
        cd = geohash_alphabet.index(char)
        for mask in [16, 8, 4, 2, 1]:
            if even:
                mid = (lon_interval[0] + lon_interval[1]) / 2
                if cd & mask:
                    lon_interval = (mid, lon_interval[1])
                else:
                    lon_interval = (lon_interval[0], mid)
            else:
                mid = (lat_interval[0] + lat_interval[1]) / 2
                if cd & mask:
                    lat_interval = (mid, lat_interval[1])
                else:
                    lat_interval = (lat_interval[0], mid)
            even = not even
    lat = (lat_interval[0] + lat_interval[1]) / 2
    lon = (lon_interval[0] + lon_interval[1]) / 2
    return lat, lon

def get_geohash_neighbors(lat, lng, precision=6):
    # Dimensions at precision 6:
    lat_height = 0.005493
    lon_width = 0.010986
    
    neighbors = set()
    for d_lat in [-lat_height, 0, lat_height]:
        for d_lon in [-lon_width, 0, lon_width]:
            neighbors.add(geohash_encode(lat + d_lat, lng + d_lon, precision))
    return list(neighbors)

# ─── Haversine Distance Utility ────────────────────────────────────────────────
def haversine_meters(lat1, lng1, lat2, lng2):
    EARTH_RADIUS_M = 6371000
    to_rad = lambda deg: (deg * np.PI) / 180.0 if hasattr(np, 'PI') else (deg * 3.1415926535) / 180.0
    
    phi1 = to_rad(lat1)
    phi2 = to_rad(lat2)
    delta_phi = to_rad(lat2 - lat1)
    delta_lambda = to_rad(lng2 - lng1)
    
    a = np.sin(delta_phi / 2)**2 + np.cos(phi1) * np.cos(phi2) * np.sin(delta_lambda / 2)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    return EARTH_RADIUS_M * c

# ─── Gemini Integration ────────────────────────────────────────────────────────
import google.generativeai as genai

# Load Gemini key
def get_gemini_api_key():
    env_key = os.environ.get("GEMINI_API_KEY")
    if env_key:
        return env_key
    paths = [
        ".env",
        "../.env",
        os.path.join(os.path.dirname(__file__), ".env"),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env")),
        "atlas-credentials.env",
        "../atlas-credentials.env"
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                with open(p, "r") as f:
                    for line in f:
                        match = re.match(r'^\s*GEMINI_API_KEY\s*=\s*["\']?(.*?)["\']?\s*$', line)
                        if match:
                            return match.group(1).strip()
            except:
                pass
    return None

gemini_key = get_gemini_api_key()
if gemini_key:
    print(f"[INFO] Gemini API Key loaded: {gemini_key[:8]}...")
    genai.configure(api_key=gemini_key)
else:
    print("[WARNING] GEMINI_API_KEY is not defined. Zero-Shot fallback will use mock description.")

def analyze_with_gemini(image_bytes, mime_type, nearby_landmarks_str):
    if not gemini_key:
        return {
            "description": "Mock description of a classic Egyptian archaeological structure with columns and carvings.",
            "possibleLandmark": "Tomb of Seshemnefer IV",
            "isNewLandmark": True,
            "confidence": 95,
            "reason": "Gemini API key is missing. Using pre-loaded mock descriptor."
        }
        
    prompt = f"""You are a heritage landmark identification assistant.

The image was captured near these known heritage landmarks:
{nearby_landmarks_str}

Analyse the uploaded image carefully and identify any heritage site or landmark visible in it.

Rules:
1. If the image clearly shows one of the nearby listed landmarks, use that exact name and set "isNewLandmark" to false.
2. If the image shows a different, identifiable landmark that is NOT in the nearby list, name it and set "isNewLandmark" to true.
3. If no recognisable landmark is visible, set "possibleLandmark" to "Unknown" and "isNewLandmark" to false.
4. IMPORTANT: Always include the real-world GPS coordinates of the identified landmark based on your knowledge.
   - For example: Eiffel Tower → latitude: 48.8584, longitude: 2.2945
   - If the landmark is unknown or unrecognisable, use null for both.

Return ONLY a valid JSON object — no markdown fences, no extra text:
{{
  "description": "Detailed visual description of what is shown in the image",
  "possibleLandmark": "Name of the identified landmark",
  "isNewLandmark": false,
  "confidence": 85,
  "reason": "Brief explanation supporting your identification",
  "latitude": null,
  "longitude": null
}}

confidence must be an integer from 0 to 100.
latitude and longitude must be real decimal numbers (e.g. 48.8584, 2.2945) or null if unknown."""

    b64_data = base64.b64encode(image_bytes).decode('utf-8')
    mime = mime_type if mime_type else "image/jpeg"
    
    # 1. Try Direct REST endpoint with gemini-3.6-flash & gemini-2.5-flash
    for model_name in ["gemini-3.6-flash", "gemini-2.5-flash"]:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={gemini_key}"
            payload = {
                "contents": [{
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": mime, "data": b64_data}}
                    ]
                }]
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode('utf-8'),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                res_data = json.loads(response.read().decode('utf-8'))
                text = res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
                if text.startswith("```"):
                    text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.IGNORECASE)
                    text = re.sub(r'\s*```$', '', text, flags=re.IGNORECASE)
                return json.loads(text.strip())
        except Exception as e:
            print(f"[DEBUG] Gemini Direct REST ({model_name}) attempt: {e}")
            continue

    # 2. Try SDK with gemini-1.5-flash-latest
    try:
        model = genai.GenerativeModel("gemini-1.5-flash-latest")
        img = Image.open(io.BytesIO(image_bytes))
        resp = model.generate_content([prompt, img])
        text = resp.text.strip()
        if text.startswith("```"):
            text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.IGNORECASE)
            text = re.sub(r'\s*```$', '', text, flags=re.IGNORECASE)
        return json.loads(text.strip())
    except Exception as e:
        print(f"[DEBUG] Gemini SDK attempt: {e}")

    # 3. Fallback
    return {
        "description": "An unidentified subject or landmark with distinct architectural features.",
        "possibleLandmark": "Unknown",
        "isNewLandmark": False,
        "confidence": 0,
        "reason": "Could not identify landmark while offline."
    }

# ─── Dataset & Bounding Box Helpers ──────────────────────────────────────────
def compute_hash(image_bytes: bytes) -> str:
    return hashlib.md5(image_bytes).hexdigest()

def validate_box(box: list) -> bool:
    if not isinstance(box, list) or len(box) != 4:
        return False
    try:
        x, y, w, h = map(float, box)
        return (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 and 0.0 < w <= 1.0 and 0.0 < h <= 1.0)
    except:
        return False

def get_class_id(class_name: str) -> int:
    with open(CLASS_MAPPING_FILE, 'r') as f:
        mapping = json.load(f)
    if class_name in mapping:
        return mapping[class_name]
    existing_ids = mapping.values()
    new_id = max(existing_ids) + 1 if existing_ids else 3
    mapping[class_name] = new_id
    with open(CLASS_MAPPING_FILE, 'w') as f:
        json.dump(mapping, f, indent=2)
    return new_id

def is_duplicate(image_hash: str) -> tuple:
    for folder in os.listdir(PENDING_DIR):
        folder_path = os.path.join(PENDING_DIR, folder)
        if os.path.isdir(folder_path) and not folder.startswith('.'):
            images_dir = os.path.join(folder_path, "images")
            if os.path.exists(images_dir):
                for file in os.listdir(images_dir):
                    if file.startswith(image_hash):
                        return True, folder
    return False, ""

def save_verified_sample(image_bytes, image_name, class_name, description, box, confidence):
    image_hash = compute_hash(image_bytes)
    duplicate_found, duplicate_class = is_duplicate(image_hash)
    if duplicate_found:
        raise ValueError(f"Duplicate image! Already verified under class: '{duplicate_class}'")
    if not validate_box(box):
        raise ValueError("Invalid bounding box coordinates.")
        
    formatted_class = class_name.replace(" ", "-")
    class_id = get_class_id(formatted_class)
    
    class_dir = os.path.join(PENDING_DIR, formatted_class)
    images_dir = os.path.join(class_dir, "images")
    labels_dir = os.path.join(class_dir, "labels")
    metadata_dir = os.path.join(class_dir, "metadata")
    
    os.makedirs(images_dir, exist_ok=True)
    os.makedirs(labels_dir, exist_ok=True)
    os.makedirs(metadata_dir, exist_ok=True)
    
    _, ext = os.path.splitext(image_name)
    if not ext or ext.lower() not in ['.jpg', '.jpeg', '.png']:
        ext = '.jpg'
        
    img_filename = f"{image_hash}{ext}"
    lbl_filename = f"{image_hash}.txt"
    meta_filename = f"{image_hash}.json"
    
    with open(os.path.join(images_dir, img_filename), 'wb') as f:
        f.write(image_bytes)
        
    x_c, y_c, w, h = box
    with open(os.path.join(labels_dir, lbl_filename), 'w') as f:
        f.write(f"{class_id} {x_c:.6f} {y_c:.6f} {w:.6f} {h:.6f}\n")
        
    metadata = {
        "image_name": image_name,
        "description": description,
        "suggested_class": formatted_class,
        "bounding_box": {
            "x_center": round(x_c, 4),
            "y_center": round(y_c, 4),
            "width": round(w, 4),
            "height": round(h, 4)
        },
        "zero_shot_confidence": round(confidence, 4),
        "verified": True,
        "source": "user_collection"
    }
    with open(os.path.join(metadata_dir, meta_filename), 'w') as f:
        json.dump(metadata, f, indent=2)
        
    return image_hash

def serialize_mongo(data):
    if isinstance(data, list):
        return [serialize_mongo(item) for item in data]
    if isinstance(data, dict):
        new_dict = {}
        for k, v in data.items():
            if isinstance(v, ObjectId):
                new_dict[k] = str(v)
            elif isinstance(v, dict) and "$oid" in v:
                new_dict[k] = str(v["$oid"])
            elif isinstance(v, dict) and "$date" in v:
                new_dict[k] = str(v["$date"])
            else:
                new_dict[k] = serialize_mongo(v)
        return new_dict
    return data

# ─── Mock Description Database for Zero-Shot Offline Fallback ──────────────────
MOCK_DESCRIPTIONS = {
    "cairo_tower.jpg": {
        "description": "A tall concrete telecommunications tower with a lattice-shaped exterior, located in Cairo.",
        "suggested_landmark": "Cairo Tower"
    },
    "unknown_pyramid.jpg": {
        "description": "A large ancient Egyptian pyramid made of limestone blocks in a sandy desert region.",
        "suggested_landmark": "Great Pyramid of Giza"
    },
    "temple.jpg": {
        "description": "An ancient temple containing large decorated sandstone columns and hieroglyphic wall reliefs.",
        "suggested_landmark": "Luxor Temple"
    }
}

def get_fallback_description(filename):
    fn_lower = filename.lower()
    if "cairo" in fn_lower or "tower" in fn_lower:
        return MOCK_DESCRIPTIONS["cairo_tower.jpg"]
    elif "pyramid" in fn_lower or "giza" in fn_lower:
        return MOCK_DESCRIPTIONS["unknown_pyramid.jpg"]
    elif "temple" in fn_lower or "luxor" in fn_lower or "column" in fn_lower:
        return MOCK_DESCRIPTIONS["temple.jpg"]
    return {
        "description": f"An unidentified heritage structure or landmark in image: '{filename}'.",
        "suggested_landmark": "Cairo Tower"
    }

# ─── Landmark Geocoding & Registration Helpers ────────────────────────────────
# NOTE: Coordinates are stored in the database (db.objects / db.locations).
# There is NO hardcoded coordinate dictionary — all lookups go through the DB.

def geocode_via_gemini(landmark_name):
    """Ask Gemini to return the real GPS coordinates for a named landmark."""
    if not gemini_key or not landmark_name:
        return None, None
    prompt = f"""Return ONLY a valid JSON object with the real-world GPS coordinates of the following landmark: "{landmark_name}".
No markdown, no explanation, just JSON:
{{"latitude": <decimal number or null>, "longitude": <decimal number or null>}}"""
    for model_name in ["gemini-2.5-flash", "gemini-1.5-flash-latest"]:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={gemini_key}"
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode('utf-8'),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                res_data = json.loads(response.read().decode('utf-8'))
                text = res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
                text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.IGNORECASE)
                text = re.sub(r'\s*```$', '', text, flags=re.IGNORECASE)
                parsed = json.loads(text.strip())
                lat_v = parsed.get("latitude")
                lng_v = parsed.get("longitude")
                if lat_v is not None and lng_v is not None:
                    print(f"[GEOCODE] Gemini returned coords for '{landmark_name}': ({lat_v}, {lng_v})")
                    return float(lat_v), float(lng_v)
        except Exception as e:
            print(f"[DEBUG] geocode_via_gemini ({model_name}): {e}")
            continue
    return None, None

def resolve_landmark_coordinates(landmark_name, default_lat=29.9792, default_lng=31.1342):
    """Resolve a landmark's GPS coordinates.

    Priority:
        1. db.objects  — matched by name or class_name (case-insensitive)
        2. db.locations — matched by name (case-insensitive, partial)
        3. Gemini geocoding API — ask Gemini for real coordinates
        4. (default_lat, default_lng) — centre of Giza plateau as absolute last resort
    """
    if not landmark_name:
        return default_lat, default_lng

    clean_space  = landmark_name.lower().strip().replace("-", " ")
    clean_hyphen = clean_space.replace(" ", "-")

    # 1. Query db.objects
    try:
        obj = db.objects.find_one({
            "$or": [
                {"name":       {"$regex": re.compile(f"^{re.escape(clean_space)}$",  re.IGNORECASE)}},
                {"name":       {"$regex": re.compile(f"^{re.escape(clean_hyphen)}$", re.IGNORECASE)}},
                {"class_name": {"$regex": re.compile(f"^{re.escape(clean_space)}$",  re.IGNORECASE)}},
                {"class_name": {"$regex": re.compile(f"^{re.escape(clean_hyphen)}$", re.IGNORECASE)}},
            ]
        })
        if obj and obj.get("latitude") is not None and obj.get("longitude") is not None:
            return float(obj["latitude"]), float(obj["longitude"])
    except Exception as e:
        print(f"[WARNING] resolve_landmark_coordinates db.objects lookup failed: {e}")

    # 2. Query db.locations (partial name match)
    try:
        loc = db.locations.find_one({
            "name": {"$regex": re.compile(re.escape(clean_space), re.IGNORECASE)}
        })
        if loc and loc.get("latitude") is not None and loc.get("longitude") is not None:
            return float(loc["latitude"]), float(loc["longitude"])
    except Exception as e:
        print(f"[WARNING] resolve_landmark_coordinates db.locations lookup failed: {e}")

    # 3. Geocode via Gemini
    g_lat, g_lng = geocode_via_gemini(landmark_name)
    if g_lat is not None and g_lng is not None:
        return g_lat, g_lng

    # 4. Last resort fallback
    print(f"[INFO] No coordinates found for '{landmark_name}'. Using default ({default_lat}, {default_lng}).")
    return default_lat, default_lng

def register_landmark_object(landmark_name, class_name=None, lat=None, lng=None, description=None):
    if not landmark_name:
        landmark_name = "Unknown Landmark"
        
    clean_name = landmark_name.replace("-", " ").strip()
    clean_class = (class_name or landmark_name).replace(" ", "-").strip()
    
    GIZA_DEFAULT = (29.9792, 31.1342)

    # Resolve coordinates if missing or invalid
    if lat is None or lng is None:
        lat, lng = resolve_landmark_coordinates(clean_name)
    else:
        try:
            lat = float(lat)
            lng = float(lng)
            # If coords exactly match the Giza default, they were never real —
            # try Gemini geocoding to get the actual world coordinates
            if abs(lat - GIZA_DEFAULT[0]) < 0.0001 and abs(lng - GIZA_DEFAULT[1]) < 0.0001:
                g_lat, g_lng = geocode_via_gemini(clean_name)
                if g_lat is not None and g_lng is not None:
                    lat, lng = g_lat, g_lng
                    print(f"[GEOCODE] Corrected '{clean_name}' coords to Gemini-provided: ({lat}, {lng})")
        except:
            lat, lng = resolve_landmark_coordinates(clean_name)
            
    geo_code = geohash_encode(lat, lng, 6)
    
    # Check if object already exists in database
    existing_obj = db.objects.find_one({
        "$or": [
            {"class_name": {"$regex": re.compile(f"^{re.escape(clean_class)}$", re.IGNORECASE)}},
            {"class_name": {"$regex": re.compile(f"^{re.escape(clean_name)}$", re.IGNORECASE)}},
            {"name": {"$regex": re.compile(f"^{re.escape(clean_name)}$", re.IGNORECASE)}},
            {"name": {"$regex": re.compile(f"^{re.escape(clean_class)}$", re.IGNORECASE)}}
        ]
    })
    
    if existing_obj:
        update_fields = {}
        if "latitude" not in existing_obj or existing_obj.get("latitude") is None:
            update_fields["latitude"] = lat
            update_fields["longitude"] = lng
            update_fields["geohash"] = geo_code
        if description and not existing_obj.get("description"):
            update_fields["description"] = description
            
        if update_fields:
            try:
                db.objects.update_one({"_id": existing_obj["_id"]}, {"$set": update_fields})
                existing_obj.update(update_fields)
            except Exception as e:
                print(f"[WARNING] Could not update existing object: {e}")
                
        return existing_obj
        
    # Generate unique IDs
    rand_suffix = uuid.uuid4().hex[:6].upper()
    loc_id = f"L_{rand_suffix}"
    obj_id = f"O_{rand_suffix}"
    post_id = f"P_{rand_suffix}"
    
    # 1. Create Location document
    loc_doc = {
        "location_id": loc_id,
        "name": clean_name,
        "latitude": lat,
        "longitude": lng,
        "geohash": geo_code
    }
    try:
        db.locations.insert_one(loc_doc)
    except Exception as e:
        print(f"[WARNING] Insert location error: {e}")
        
    # 2. Create Object document
    obj_doc = {
        "object_id": obj_id,
        "name": clean_name,
        "class_name": clean_class,
        "location_id": loc_id,
        "latitude": lat,
        "longitude": lng,
        "geohash": geo_code,
        "radius_m": 80,
        "description": description or f"Registered heritage landmark: {clean_name}"
    }
    try:
        db.objects.insert_one(obj_doc)
    except Exception as e:
        print(f"[WARNING] Insert object error: {e}")
        
    # 3. Create initial Social Post
    post_content = f"📍 Welcome to {clean_name}! {description}" if description else f"📍 Welcome to {clean_name}! Verified heritage landmark."
    post_doc = {
        "post_id": post_id,
        "content": post_content,
        "location_id": loc_id,
        "object_id": obj_id
    }
    try:
        db.posts.insert_one(post_doc)
    except Exception as e:
        print(f"[WARNING] Insert initial post error: {e}")
        
    # 4. Real-time broadcast
    try:
        socketio.emit("object_registered", {
            "object": serialize_mongo(obj_doc),
            "location": serialize_mongo(loc_doc),
            "post": serialize_mongo(post_doc)
        })
        print(f"[SUCCESS] Registered new landmark in database and emitted 'object_registered': {clean_name}")
    except Exception as e:
        print(f"[WARNING] SocketIO broadcast error: {e}")
        
    return obj_doc

# ─── Async Job Queue (prevents Railway 60s proxy timeout on YOLO inference) ───
import threading
_job_store = {}   # job_id -> {"status": "pending"|"done"|"error", "result": {...}}
_job_lock  = threading.Lock()

def _run_detect_job(job_id, detect_fn, *args, **kwargs):
    """Run a detection job in a background thread and store the result."""
    try:
        result = detect_fn(*args, **kwargs)
        with _job_lock:
            _job_store[job_id] = {"status": "done", "result": result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        with _job_lock:
            _job_store[job_id] = {"status": "error", "result": {"error": str(e)}}

# ─── API Routes ───────────────────────────────────────────────────────────────
@app.route('/favicon.ico')
def favicon():
    # Suppress browser 404 for favicon
    return '', 204

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/detect/result/<job_id>', methods=['GET'])
def api_detect_result(job_id):
    """Poll for the result of an async detect job."""
    with _job_lock:
        job = _job_store.get(job_id)
    if job is None:
        return jsonify({"status": "not_found"}), 404
    if job["status"] == "pending":
        return jsonify({"status": "pending"})
    # Clean up after delivery
    with _job_lock:
        _job_store.pop(job_id, None)
    if job["status"] == "error":
        return jsonify(job["result"]), 500
    return jsonify(job["result"])

@app.route('/api/objects', methods=['GET'])
def api_objects():
    try:
        objs = list(db.objects.find({}))
        return jsonify(serialize_mongo(objs))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/posts', methods=['GET', 'POST'])
def api_posts():
    if request.method == 'POST':
        try:
            data = request.get_json() or {}
            content = data.get('content', '').strip()
            if not content:
                return jsonify({'error': 'Post content cannot be empty'}), 400
                
            author = data.get('author', 'Heritage Explorer').strip() or 'Heritage Explorer'
            object_id = data.get('object_id')
            location_id = data.get('location_id')
            
            if object_id and not location_id:
                obj = db.objects.find_one({"object_id": object_id})
                if obj and "location_id" in obj:
                    location_id = obj["location_id"]
                    
            rand_id = f"P{int(time.time() % 1000000):06d}"
            post_doc = {
                "post_id": rand_id,
                "author": author,
                "content": content,
                "location_id": location_id,
                "object_id": object_id,
                "createdAt": datetime.datetime.now(datetime.timezone.utc) if use_mongodb else time.strftime("%Y-%m-%dT%H:%M:%SZ")
            }
            
            db.posts.insert_one(post_doc)
            serialized_post = serialize_mongo(post_doc)
            
            try:
                socketio.emit("new_post", {
                    "post": serialized_post,
                    "object_id": object_id,
                    "location_id": location_id
                })
            except Exception as se:
                print(f"[WARNING] SocketIO emit new_post error: {se}")
                
            return jsonify({'success': True, 'post': serialized_post}), 201
        except Exception as e:
            return jsonify({'error': str(e)}), 500
            
    # GET method
    try:
        query = {}
        obj_id = request.args.get('object_id')
        loc_id = request.args.get('location_id')
        if obj_id and loc_id:
            query["$or"] = [{"object_id": obj_id}, {"location_id": loc_id}]
        elif obj_id:
            query["object_id"] = obj_id
        elif loc_id:
            query["location_id"] = loc_id
            
        posts = list(db.posts.find(query).sort("createdAt", -1))
        return jsonify(serialize_mongo(posts))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/locations', methods=['GET'])
def api_locations():
    try:
        locs = list(db.locations.find({}))
        return jsonify(serialize_mongo(locs))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/fix-coordinates', methods=['POST'])
def api_admin_fix_coordinates():
    """Admin endpoint: scan all objects with Giza default coords and geocode them via Gemini."""
    try:
        GIZA_LAT, GIZA_LNG = 29.9792, 31.1342
        GIZA_LANDMARKS = {'great pyramid', 'khafre pyramid', 'sphinx', 'giza', 'great pyramid of giza'}
        objs = list(db.objects.find({}))
        fixed = []
        skipped = []
        for o in objs:
            name = o.get('name', '')
            lat_o = o.get('latitude')
            lng_o = o.get('longitude')
            # Only fix objects that have Giza default coords AND are NOT actually Giza landmarks
            is_giza_default = (
                lat_o is None or lng_o is None or
                (abs(float(lat_o or 0) - GIZA_LAT) < 0.001 and
                 abs(float(lng_o or 0) - GIZA_LNG) < 0.001)
            )
            if is_giza_default and name.lower().strip() not in GIZA_LANDMARKS:
                g_lat, g_lng = geocode_via_gemini(name)
                if g_lat is not None and g_lng is not None:
                    try:
                        new_hash = geohash_encode(g_lat, g_lng, 6)
                        db.objects.update_one(
                            {"_id": o["_id"]},
                            {"$set": {"latitude": g_lat, "longitude": g_lng, "geohash": new_hash}}
                        )
                        # Also fix the linked location
                        if o.get('location_id'):
                            db.locations.update_one(
                                {"location_id": o['location_id']},
                                {"$set": {"latitude": g_lat, "longitude": g_lng, "geohash": new_hash}}
                            )
                        fixed.append({"name": name, "lat": g_lat, "lng": g_lng})
                        print(f"[ADMIN FIX] '{name}' -> ({g_lat}, {g_lng})")
                    except Exception as ue:
                        skipped.append({"name": name, "reason": str(ue)})
                else:
                    skipped.append({"name": name, "reason": "Gemini could not geocode"})
            else:
                skipped.append({"name": name, "reason": "coords OK or is a Giza landmark"})
        return jsonify({"fixed": fixed, "skipped": skipped, "total_fixed": len(fixed)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/nearby', methods=['GET'])
def api_nearby():
    try:
        lat = float(request.args.get('lat', 29.9792))
        lng = float(request.args.get('lng', 31.1342))
        
        # Geohash lookup
        center_geohash = geohash_encode(lat, lng, 6)
        geohashes = get_geohash_neighbors(lat, lng, 6)
        
        # Find matching locations
        locations = list(db.locations.find({"geohash": {"$in": geohashes}}))
        loc_ids = [l["location_id"] for l in locations]
        
        # Filter posts
        post_filter = {"location_id": {"$in": loc_ids}}
        
        # Check if object filter is requested
        obj_class = request.args.get('object_class')
        obj_id = request.args.get('object_id')
        
        if obj_class:
            obj = db.objects.find_one({"class_name": obj_class})
            if obj:
                post_filter["object_id"] = obj["object_id"]
        elif obj_id:
            post_filter["object_id"] = obj_id
            
        posts = list(db.posts.find(post_filter))
        
        return jsonify({
            "userLocation": {
                "latitude": lat,
                "longitude": lng,
                "geohash": center_geohash
            },
            "locations": serialize_mongo(locations),
            "posts": serialize_mongo(posts)
        })
    except Exception as e:
        print(f"[ERROR] Nearby endpoint: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/detect', methods=['POST'])
@app.route('/api/predict', methods=['POST'])
def api_detect():
    if 'image' not in request.files:
        return jsonify({'error': 'No image file uploaded'}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    # Read ALL data from request BEFORE spawning thread (Flask request context dies after return)
    model_type = request.form.get('model_type', 'v11')
    lat_form   = request.form.get('lat', '29.9792')
    lng_form   = request.form.get('lng', '31.1342')
    filename   = file.filename
    mimetype   = file.mimetype
    file_bytes = file.read()

    # Quick image validation before dispatching
    nparr = np.frombuffer(file_bytes, np.uint8)
    img   = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return jsonify({'error': 'Invalid image format'}), 400

    # Create job entry and launch background thread
    job_id = str(uuid.uuid4())
    with _job_lock:
        _job_store[job_id] = {"status": "pending"}

    threading.Thread(
        target=_run_detect_job,
        args=(job_id, _do_detect_sync, file_bytes, img, filename, mimetype, model_type, lat_form, lng_form),
        daemon=True
    ).start()

    return jsonify({"job_id": job_id, "status": "pending"})


def _do_detect_sync(file_bytes, img, filename, mimetype, model_type, lat_form, lng_form):
    """Heavy detection logic — runs in background thread, returns a plain dict result."""
    is_custom_active = is_custom_yolo11 if model_type == 'v11' else is_custom_yolov8
    is_demo_active   = is_yolo11_demo   if model_type == 'v11' else False
    active_model     = get_yolo_y11()   if model_type == 'v11' else get_yolo_v8()
    threshold = 0.60

    try:

            
        t0 = time.time()
        
        # 1. Check local duplicates
        img_hash = compute_hash(file_bytes)
        dup_found, dup_class = is_duplicate(img_hash)
        
        if dup_found:
            # Look up metadata from verified custom samples
            metadata_path = os.path.join(PENDING_DIR, dup_class, "metadata", f"{img_hash}.json")
            if os.path.exists(metadata_path):
                with open(metadata_path, 'r') as f:
                    meta = json.load(f)
                box_norm = [
                    meta["bounding_box"]["x_center"],
                    meta["bounding_box"]["y_center"],
                    meta["bounding_box"]["width"],
                    meta["bounding_box"]["height"]
                ]
                conf_val = meta["zero_shot_confidence"]
                suggested_landmark = dup_class.replace("-", " ")
                
                # Draw box
                h_img, w_img, _ = img.shape
                x_c, y_c, box_w, box_h = box_norm
                x1 = int((x_c - box_w / 2) * w_img)
                y1 = int((y_c - box_h / 2) * h_img)
                x2 = int((x_c + box_w / 2) * w_img)
                y2 = int((y_c + box_h / 2) * h_img)
                
                annotated_img = img.copy()
                cv2.rectangle(annotated_img, (x1, y1), (x2, y2), (0, 255, 0), 3)
                cv2.putText(annotated_img, f"{suggested_landmark} ({conf_val:.2%})", (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                            
                _, buffer = cv2.imencode('.jpg', annotated_img)
                encoded_image = base64.b64encode(buffer).decode('utf-8')
                
                # Ensure object is registered in live tracking DB
                matched_obj = register_landmark_object(
                    landmark_name=suggested_landmark,
                    class_name=dup_class,
                    description=meta.get("description", "")
                )
                posts = list(db.posts.find({"object_id": matched_obj["object_id"]})) if matched_obj else []
                
                return {
                    'image': f"data:image/jpeg;base64,{encoded_image}",
                    'detections': [{'class': suggested_landmark, 'confidence': f"{conf_val:.2%}"}],
                    'inference_time': '0.0ms',
                    'is_custom': True,
                    'is_oneshot': True,
                    'recognition_method': 'YOLO (One-Shot Learned)',
                    'object': serialize_mongo(matched_obj) if matched_obj else None,
                    'posts': serialize_mongo(posts)
                }
                
        # 2. Run standard model prediction
        results = active_model.predict(source=img, save=False, verbose=False)
        inference_time = (time.time() - t0) * 1000
        result = results[0]
        
        has_custom_detection = False
        detections = []
        for box in result.boxes:
            conf = float(box.conf[0])
            if is_demo_active:
                conf = max(0.01, min(0.99, conf + random.uniform(-0.02, 0.03)))
            if conf >= threshold:
                has_custom_detection = True
                cls_id = int(box.cls[0])
                name = result.names[cls_id]
                detections.append({
                    'class': name,
                    'confidence': f"{conf:.2%}"
                })
                
        if has_custom_detection:
            # Match highest confidence detection with database
            best_det = max(result.boxes, key=lambda b: float(b.conf[0]))
            cls_id = int(best_det.cls[0])
            cls_name = result.names[cls_id]
            
            # Fetch object & posts from MongoDB — coordinates come from DB only
            cls_name_alt    = cls_name.replace("-", " ")
            cls_name_hyphen = cls_name.replace(" ", "-")
            matched_obj = db.objects.find_one({
                "$or": [
                    {"class_name": {"$regex": re.compile(f"^{re.escape(cls_name)}$",        re.IGNORECASE)}},
                    {"class_name": {"$regex": re.compile(f"^{re.escape(cls_name_hyphen)}$", re.IGNORECASE)}},
                    {"name":       {"$regex": re.compile(f"^{re.escape(cls_name)}$",        re.IGNORECASE)}},
                    {"name":       {"$regex": re.compile(f"^{re.escape(cls_name_alt)}$",    re.IGNORECASE)}}
                ]
            })

            if not matched_obj:
                # Class detected but not yet in DB — register it now so live tracking works
                print(f"[INFO] YOLO detected '{cls_name}' but no DB entry found. Auto-registering...")
                matched_obj = register_landmark_object(
                    landmark_name=cls_name_alt,
                    class_name=cls_name_hyphen
                )
            elif matched_obj.get("latitude") is None or matched_obj.get("longitude") is None:
                # Entry exists but coords missing — resolve from DB and patch
                lat_r, lng_r = resolve_landmark_coordinates(cls_name_alt)
                try:
                    db.objects.update_one(
                        {"_id": matched_obj["_id"]},
                        {"$set": {"latitude": lat_r, "longitude": lng_r,
                                  "geohash": geohash_encode(lat_r, lng_r, 6)}}
                    )
                except Exception as _e:
                    print(f"[WARNING] Could not patch coords for '{cls_name}': {_e}")
                matched_obj["latitude"]  = lat_r
                matched_obj["longitude"] = lng_r

            posts = []
            if matched_obj and "object_id" in matched_obj:
                posts = list(db.posts.find({"object_id": matched_obj["object_id"]}))
                
            # Plot & Encode
            annotated_img = result.plot()
            _, buffer = cv2.imencode('.jpg', annotated_img)
            encoded_image = base64.b64encode(buffer).decode('utf-8')
            
            return {
                'image': f"data:image/jpeg;base64,{encoded_image}",
                'detections': detections,
                'inference_time': f"{inference_time:.1f}ms",
                'is_custom': is_custom_active,
                'recognition_method': 'YOLO',
                'object': serialize_mongo(matched_obj) if matched_obj else None,
                'posts': serialize_mongo(posts)
            }
            
        # 3. Check if image matches any confirmed custom classes in pending_dataset / class_mapping
        custom_confirmed_classes = []
        if os.path.exists(CLASS_MAPPING_FILE):
            try:
                with open(CLASS_MAPPING_FILE, 'r') as f:
                    cmap = json.load(f)
                    for k, v in cmap.items():
                        if v >= 3:
                            custom_confirmed_classes.append(k.replace("-", " "))
            except Exception as e:
                pass
                
        for s in os.listdir(PENDING_DIR):
            img_dir = os.path.join(PENDING_DIR, s, "images")
            if os.path.exists(img_dir) and len(os.listdir(img_dir)) > 0:
                cname = s.replace("-", " ")
                if cname not in custom_confirmed_classes:
                    custom_confirmed_classes.append(cname)
                    
        # Also check fallback meta filename
        fallback_meta = get_fallback_description(filename)
        if fallback_meta and fallback_meta.get("suggested_landmark"):
            s_name = fallback_meta["suggested_landmark"]
            if s_name not in custom_confirmed_classes:
                if os.path.exists(os.path.join(PENDING_DIR, s_name.replace(" ", "-"), "images")):
                    custom_confirmed_classes.append(s_name)

        if custom_confirmed_classes:
            try:
                yolo_world = get_yolo_world()
                yolo_world.set_classes(custom_confirmed_classes)
                world_res = yolo_world.predict(source=img, save=False, verbose=False)[0]
                
                best_box = None
                best_conf = 0.0
                best_cls_name = None
                
                for box in world_res.boxes:
                    conf = float(box.conf[0])
                    if conf >= 0.35 and conf > best_conf:
                        best_conf = conf
                        best_box = box.xywhn[0].tolist()
                        cls_idx = int(box.cls[0])
                        best_cls_name = custom_confirmed_classes[cls_idx] if cls_idx < len(custom_confirmed_classes) else custom_confirmed_classes[0]
                        
                if best_box and best_cls_name:
                    h_img, w_img, _ = img.shape
                    x_c, y_c, box_w, box_h = best_box
                    x1 = int((x_c - box_w / 2) * w_img)
                    y1 = int((y_c - box_h / 2) * h_img)
                    x2 = int((x_c + box_w / 2) * w_img)
                    y2 = int((y_c + box_h / 2) * h_img)
                    
                    annotated_img = img.copy()
                    cv2.rectangle(annotated_img, (x1, y1), (x2, y2), (16, 185, 129), 3)
                    cv2.putText(annotated_img, f"{best_cls_name} ({best_conf:.2%})", (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (16, 185, 129), 2)
                                
                    _, buffer = cv2.imencode('.jpg', annotated_img)
                    encoded_image = base64.b64encode(buffer).decode('utf-8')
                    
                    cls_name_alt    = best_cls_name.replace("-", " ")
                    cls_name_hyphen = best_cls_name.replace(" ", "-")
                    matched_obj = db.objects.find_one({
                        "$or": [
                            {"class_name": {"$regex": re.compile(f"^{re.escape(best_cls_name)}$",  re.IGNORECASE)}},
                            {"class_name": {"$regex": re.compile(f"^{re.escape(cls_name_hyphen)}$", re.IGNORECASE)}},
                            {"name":       {"$regex": re.compile(f"^{re.escape(best_cls_name)}$",  re.IGNORECASE)}},
                            {"name":       {"$regex": re.compile(f"^{re.escape(cls_name_alt)}$",   re.IGNORECASE)}}
                        ]
                    })

                    if not matched_obj:
                        # Custom class detected but not in DB — register it now
                        print(f"[INFO] YOLO-World detected '{best_cls_name}' but no DB entry. Auto-registering...")
                        matched_obj = register_landmark_object(
                            landmark_name=cls_name_alt,
                            class_name=cls_name_hyphen
                        )
                    elif matched_obj.get("latitude") is None or matched_obj.get("longitude") is None:
                        # Coords missing — resolve from DB and patch
                        lat_r, lng_r = resolve_landmark_coordinates(cls_name_alt)
                        try:
                            db.objects.update_one(
                                {"_id": matched_obj["_id"]},
                                {"$set": {"latitude": lat_r, "longitude": lng_r,
                                          "geohash": geohash_encode(lat_r, lng_r, 6)}}
                            )
                        except Exception as _e:
                            print(f"[WARNING] Could not patch coords for '{best_cls_name}': {_e}")
                        matched_obj["latitude"]  = lat_r
                        matched_obj["longitude"] = lng_r

                    posts = []
                    if matched_obj and "object_id" in matched_obj:
                        posts = list(db.posts.find({"object_id": matched_obj["object_id"]}))
                        
                    return {
                        'image': f"data:image/jpeg;base64,{encoded_image}",
                        'detections': [{'class': best_cls_name, 'confidence': f"{best_conf:.2%}"}],
                        'inference_time': f"{(time.time() - t0)*1000:.1f}ms",
                        'is_custom': True,
                        'is_oneshot': True,
                        'recognition_method': 'YOLO (One-Shot Learned)',
                        'object': serialize_mongo(matched_obj) if matched_obj else {'name': best_cls_name, 'description': 'Custom learned landmark'},
                        'posts': serialize_mongo(posts)
                    }
            except Exception as e:
                print(f"[WARNING] Custom classes YOLO-World detection failed: {e}")

        # 4. Unknown landmark fallback — zero-shot pipeline
        print(f"[INFO] Running Zero-Shot Fallback Pipeline for: {filename}")
        
        # Read user active GPS coordinate from request
        try:
            lat_context = float(lat_form)
            lng_context = float(lng_form)
        except:
            lat_context = 29.9792
            lng_context = 31.1342
        geohashes = get_geohash_neighbors(lat_context, lng_context, 6)
        nearby_locs = list(db.locations.find({"geohash": {"$in": geohashes}}))
        
        nearby_objs = []
        for loc in nearby_locs:
            objs = list(db.objects.find({"location_id": loc["location_id"]}))
            for o in objs:
                nearby_objs.append(f"{o['name']} (at {loc['name']})")
        nearby_landmarks_str = "\n".join([f"  - {o}" for o in nearby_objs])
        
        # Run Gemini
        gemini_res = analyze_with_gemini(file_bytes, mimetype, nearby_landmarks_str)
        suggested_landmark = gemini_res.get("possibleLandmark", "Unknown")
        description = gemini_res.get("description", "")
        confidence_val = gemini_res.get("confidence", 80) / 100.0
        is_new_landmark = gemini_res.get("isNewLandmark", False)
        # Use Gemini-provided coordinates if available (real-world GPS from its knowledge)
        gemini_lat = gemini_res.get("latitude")
        gemini_lng = gemini_res.get("longitude")
        if gemini_lat is not None and gemini_lng is not None:
            try:
                lat_context = float(gemini_lat)
                lng_context = float(gemini_lng)
                print(f"[GEOCODE] Using Gemini-provided coords for '{suggested_landmark}': ({lat_context}, {lng_context})")
            except:
                pass  # Keep user GPS context if Gemini coords are invalid
        
        # Run YOLO-World to locate it
        box_norm = [0.5, 0.5, 0.5, 0.5]
        if suggested_landmark != "Unknown":
            try:
                yolo_world = get_yolo_world()
                yolo_world.set_classes([suggested_landmark])
                world_res = yolo_world.predict(source=img, save=False, verbose=False)[0]
                for box in world_res.boxes:
                    box_norm = box.xywhn[0].tolist()
                    break
            except Exception as e:
                print(f"[WARNING] YOLO-World localization failed: {e}")
                
        # Draw bounding box
        h_img, w_img, _ = img.shape
        x_c, y_c, box_w, box_h = box_norm
        x1 = int((x_c - box_w / 2) * w_img)
        y1 = int((y_c - box_h / 2) * h_img)
        x2 = int((x_c + box_w / 2) * w_img)
        y2 = int((y_c + box_h / 2) * h_img)
        
        annotated_img = img.copy()
        cv2.rectangle(annotated_img, (x1, y1), (x2, y2), (185, 6, 212), 3)
        cv2.putText(annotated_img, f"{suggested_landmark} ({confidence_val:.2%})", (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (185, 6, 212), 2)
                    
        # ── Auto-Confirm Check ──────────────────────────────────────────────
        # If Gemini identified a landmark that already exists in our DB as a
        # registered object (i.e. it was previously confirmed), auto-save this
        # image as training data without asking the user again.
        auto_confirmed = False
        existing_db_obj = None
        if suggested_landmark and suggested_landmark != "Unknown":
            lm_clean  = suggested_landmark.lower().strip()
            lm_hyphen = lm_clean.replace(" ", "-")
            existing_db_obj = db.objects.find_one({
                "$or": [
                    {"name":       {"$regex": re.compile(f"^{re.escape(lm_clean)}$",  re.IGNORECASE)}},
                    {"name":       {"$regex": re.compile(f"^{re.escape(lm_hyphen)}$", re.IGNORECASE)}},
                    {"class_name": {"$regex": re.compile(f"^{re.escape(lm_clean)}$",  re.IGNORECASE)}},
                    {"class_name": {"$regex": re.compile(f"^{re.escape(lm_hyphen)}$", re.IGNORECASE)}},
                ]
            })
            if existing_db_obj and confidence_val >= 0.60:
                auto_confirmed = True
                print(f"[AUTO-CONFIRM] '{suggested_landmark}' already in DB with conf {confidence_val:.0%}. Auto-saving training sample.")

        # Save temporary image for verify preview
        temp_img_path = os.path.join("temp_uploads", f"{img_hash}.jpg")
        with open(temp_img_path, 'wb') as f:
            f.write(file_bytes)
            
        # Also upload candidate to uploads/candidates/ for review dashboard
        candidate_filename = f"{uuid.uuid4()}.jpg"
        candidate_path = os.path.join("uploads", "candidates", candidate_filename)
        shutil.copy2(temp_img_path, candidate_path)

        # If auto-confirmed, immediately save as approved training sample
        auto_status = "approved" if auto_confirmed else "pending"
        if auto_confirmed:
            class_name_for_save = (existing_db_obj.get("class_name") or suggested_landmark).replace(" ", "-")
            save_verified_sample(
                image_bytes=file_bytes,
                image_name=filename,
                class_name=class_name_for_save,
                description=description,
                box=box_norm,
                confidence=confidence_val
            )
            # Clean up temp
            if os.path.exists(temp_img_path):
                os.remove(temp_img_path)
            print(f"[AUTO-CONFIRM] Training sample saved for '{suggested_landmark}'.")
        
        # Write to MongoDB Atlas as a training candidate
        candidate_doc = {
            "imagePath": f"uploads/candidates/{candidate_filename}",
            "description": description,
            "suggestedLandmark": suggested_landmark,
            "isNewLandmark": is_new_landmark,
            "confidence": int(confidence_val * 100),
            "reason": gemini_res.get("reason", ""),
            "latitude": lat_context,
            "longitude": lng_context,
            "geminiLat": gemini_lat,
            "geminiLng": gemini_lng,
            "nearbyLandmarks": [o.split(" (at")[0] for o in nearby_objs],
            "status": auto_status,
            "autoConfirmed": auto_confirmed,
            "createdAt": datetime.datetime.now(datetime.timezone.utc) if use_mongodb else time.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        
        try:
            cand_res = db.training_candidates.insert_one(candidate_doc)
            cand_id = str(cand_res.inserted_id)
        except Exception as e:
            print(f"[ERROR] Failed to save candidate doc: {e}")
            cand_id = str(uuid.uuid4())
            
        _, buffer = cv2.imencode('.jpg', annotated_img)
        encoded_image = base64.b64encode(buffer).decode('utf-8')

        # Posts for the object (auto-confirm case shows them immediately)
        auto_posts = []
        if auto_confirmed and existing_db_obj and existing_db_obj.get("object_id"):
            auto_posts = list(db.posts.find({"object_id": existing_db_obj["object_id"]}).sort("createdAt", -1))
        
        return {
            'image': f"data:image/jpeg;base64,{encoded_image}",
            'detections': [{'class': suggested_landmark, 'confidence': f"{confidence_val:.2%}"}],
            'inference_time': f"{(time.time() - t0)*1000:.1f}ms",
            'is_custom': False,
            'recognition_method': 'Zero-Shot',
            'image_hash': img_hash,
            'description': description,
            'suggested_class': suggested_landmark.replace(" ", "-"),
            'box': box_norm,
            'confidence_val': confidence_val,
            'filename': filename,
            'trainingCandidateId': cand_id,
            'auto_confirmed': auto_confirmed,
            'auto_object': serialize_mongo(existing_db_obj) if auto_confirmed else None,
            'auto_posts': serialize_mongo(auto_posts) if auto_confirmed else [],
            'gemini': {
                'description': description,
                'possibleLandmark': suggested_landmark,
                'isNewLandmark': is_new_landmark,
                'confidence': int(confidence_val * 100),
                'reason': gemini_res.get("reason", "")
            },
            'unknown': not auto_confirmed,
            'nearbyCandidates': [{'locationName': l['name'], 'objects': [o['name'] for o in db.objects.find({'location_id': l['location_id']})]} for l in nearby_locs]
        }
        
    except Exception as e:
        print(f"[ERROR] Detection job: {e}")
        import traceback
        traceback.print_exc()
        return {'error': str(e)}

@app.route('/api/compare', methods=['POST'])
def api_compare():
    if 'image' not in request.files:
        return jsonify({'error': 'No image file uploaded'}), 400
    file = request.files['image']
    
    try:
        file_bytes = file.read()
        nparr = np.frombuffer(file_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # Predict YOLOv8 (lazy load)
        t0 = time.time()
        res_v8 = get_yolo_v8().predict(source=img, save=False, verbose=False)[0]
        time_v8 = (time.time() - t0) * 1000
        
        annotated_v8 = res_v8.plot()
        _, buf_v8 = cv2.imencode('.jpg', annotated_v8)
        enc_v8 = base64.b64encode(buf_v8).decode('utf-8')
        
        det_v8 = []
        for box in res_v8.boxes:
            det_v8.append({
                'class': res_v8.names[int(box.cls[0])],
                'confidence': f"{float(box.conf[0]):.2%}"
            })
            
        # Predict YOLO11 (lazy load)
        t0 = time.time()
        res_y11 = get_yolo_y11().predict(source=img, save=False, verbose=False)[0]
        time_y11 = (time.time() - t0) * 1000
        
        if is_yolo11_demo:
            # Perceptual variations
            time_y11 = time_v8 * random.uniform(0.85, 0.95)
            
        annotated_y11 = res_y11.plot()
        _, buf_y11 = cv2.imencode('.jpg', annotated_y11)
        enc_y11 = base64.b64encode(buf_y11).decode('utf-8')
        
        det_y11 = []
        for box in res_y11.boxes:
            conf = float(box.conf[0])
            if is_yolo11_demo:
                conf = max(0.01, min(0.99, conf + random.uniform(-0.02, 0.03)))
            det_y11.append({
                'class': res_y11.names[int(box.cls[0])],
                'confidence': f"{conf:.2%}"
            })
            
        return jsonify({
            'yolov8': {
                'image': f"data:image/jpeg;base64,{enc_v8}",
                'detections': det_v8,
                'inference_time': f"{time_v8:.1f}ms",
                'is_custom': is_custom_yolov8
            },
            'yolo11': {
                'image': f"data:image/jpeg;base64,{enc_y11}",
                'detections': det_y11,
                'inference_time': f"{time_y11:.1f}ms",
                'is_custom': is_custom_yolo11,
                'is_demo': is_yolo11_demo
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/confirm', methods=['POST'])
def api_confirm():
    try:
        data = request.get_json()
        image_hash = data.get('image_hash')
        suggested_class = data.get('suggested_class')
        description = data.get('description', '')
        box = data.get('box', [0.5, 0.5, 0.5, 0.5])
        confidence = float(data.get('confidence', 0.85))
        filename = data.get('filename', 'verified.jpg')
        cand_id = data.get('trainingCandidateId')
        lat = data.get('lat')
        lng = data.get('lng')
        
        cand_doc = None
        if cand_id:
            try:
                cand_doc = db.training_candidates.find_one({"_id": ObjectId(cand_id)})
            except:
                pass
                
        if (lat is None or lng is None) and cand_doc:
            lat = cand_doc.get('latitude')
            lng = cand_doc.get('longitude')
            
        temp_path = os.path.join("temp_uploads", f"{image_hash}.jpg")
        if not os.path.exists(temp_path):
            return jsonify({'error': 'Temporary file expired. Please re-upload.'}), 404
            
        with open(temp_path, 'rb') as f:
            image_bytes = f.read()
            
        # Save sample locally
        save_verified_sample(
            image_bytes=image_bytes,
            image_name=filename,
            class_name=suggested_class,
            description=description,
            box=box,
            confidence=confidence
        )
        
        # Delete temp file
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
        # Update MongoDB Atlas candidate status
        if cand_id:
            try:
                db.training_candidates.update_one(
                    {"_id": ObjectId(cand_id)},
                    {"$set": {"status": "approved"}}
                )
            except Exception as e:
                print(f"[WARNING] Could not update MongoDB candidate status: {e}")
                
        # Register new landmark into heritage_social.objects, locations, and posts
        landmark_name = suggested_class.replace("-", " ")
        reg_obj = register_landmark_object(
            landmark_name=landmark_name,
            class_name=suggested_class,
            lat=lat,
            lng=lng,
            description=description
        )
                
        return jsonify({
            'success': True,
            'message': f'Sample verified and registered "{landmark_name}" in Live Object Tracker & Dataset!',
            'object': serialize_mongo(reg_obj) if reg_obj else None
        })
        
    except Exception as e:
        print(f"[ERROR] Confirm route: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/reject', methods=['POST'])
def api_reject():
    try:
        data = request.get_json()
        image_hash = data.get('image_hash')
        suggested_class = data.get('suggested_class')
        cand_id = data.get('trainingCandidateId')
        
        # Increment rejection log
        rejections = {}
        if os.path.exists(REJECTION_LOG_FILE):
            try:
                with open(REJECTION_LOG_FILE, 'r') as f:
                    rejections = json.load(f)
            except:
                pass
        formatted_class = suggested_class.replace(" ", "-")
        rejections[formatted_class] = rejections.get(formatted_class, 0) + 1
        with open(REJECTION_LOG_FILE, 'w') as f:
            json.dump(rejections, f, indent=2)
            
        # Remove temp image
        temp_path = os.path.join("temp_uploads", f"{image_hash}.jpg")
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
        # Update MongoDB Atlas candidate status
        if cand_id:
            try:
                db.training_candidates.update_one(
                    {"_id": ObjectId(cand_id)},
                    {"$set": {"status": "rejected"}}
                )
            except Exception as e:
                print(f"[WARNING] Could not update MongoDB candidate status: {e}")
                
        return jsonify({'success': True, 'message': 'Prediction rejected.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/training-candidates', methods=['GET'])
def api_get_candidates():
    try:
        status_filter = request.args.get('status', 'pending')
        query = {}
        if status_filter != 'all':
            query['status'] = status_filter
            
        candidates = list(db.training_candidates.find(query).sort("createdAt", -1))
        return jsonify(serialize_mongo(candidates))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/training-candidates/<id>/status', methods=['PATCH'])
def api_patch_candidate(id):
    try:
        data = request.get_json()
        status = data.get('status')
        if status not in ["pending", "approved", "rejected"]:
            return jsonify({'error': 'Invalid status'}), 400
            
        candidate = db.training_candidates.find_one({"_id": ObjectId(id)})
        if not candidate:
            return jsonify({'error': 'Candidate not found'}), 404
            
        # Update status in MongoDB
        db.training_candidates.update_one(
            {"_id": ObjectId(id)},
            {"$set": {"status": status}}
        )
        
        # If approved, move and save candidate to local pending dataset
        if status == "approved" and candidate.get("status") != "approved":
            # Load candidate image bytes
            img_path = candidate.get("imagePath")
            # Convert candidate path
            full_img_path = os.path.join(os.path.dirname(__file__), img_path)
            if os.path.exists(full_img_path):
                with open(full_img_path, 'rb') as f:
                    image_bytes = f.read()
                    
                # Save locally
                save_verified_sample(
                    image_bytes=image_bytes,
                    image_name=os.path.basename(img_path),
                    class_name=candidate.get("suggestedLandmark"),
                    description=candidate.get("description", ""),
                    box=[0.5, 0.5, 0.5, 0.5], # default centroid
                    confidence=candidate.get("confidence", 85) / 100.0
                )
                
            # Also register object in live tracking DB
            register_landmark_object(
                landmark_name=candidate.get("suggestedLandmark"),
                class_name=candidate.get("suggestedLandmark"),
                lat=candidate.get("latitude"),
                lng=candidate.get("longitude"),
                description=candidate.get("description", "")
            )
                
        return jsonify({'success': True, 'message': f'Status updated to {status}.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/simulate/move', methods=['POST'])
def api_simulate_move():
    try:
        data = request.get_json()
        lat = float(data.get('lat'))
        lng = float(data.get('lng'))
        user_id = data.get('userId', 'demo-user')
        prev_obj_id = data.get('previousObjectId')
        requested_obj_id = data.get('requestedObjectId')  # Explicit object chosen by user

        # If user explicitly selected an object from the tracker, use it directly
        explicit_obj = None
        if requested_obj_id:
            explicit_obj = db.objects.find_one({"object_id": requested_obj_id})

        # Step 1: Detect nearest object via geofence (for location-aware logic)
        geohashes = get_geohash_neighbors(lat, lng, 6)
        candidates = list(db.objects.find({
            "geohash": {"$in": geohashes},
            "latitude": {"$exists": True},
            "longitude": {"$exists": True}
        }))
        
        nearest = None
        nearest_dist = float('inf')
        
        for obj in candidates:
            dist = haversine_meters(lat, lng, obj["latitude"], obj["longitude"])
            radius = obj.get("radius_m", 80)
            if dist <= radius and dist < nearest_dist:
                nearest = obj
                nearest_dist = dist

        # Prefer explicit selection over geofence result
        active_obj = explicit_obj if explicit_obj else nearest
        current_obj_id = active_obj["object_id"] if active_obj else None
        current_obj_name = active_obj["name"] if active_obj else None
        location_id = active_obj.get("location_id") if active_obj else None

        # Distance is always based on geofence detection
        geofence_hit = nearest is not None
        if nearest and explicit_obj and nearest["object_id"] == explicit_obj["object_id"]:
            distance_m = round(nearest_dist)
        elif nearest:
            distance_m = round(nearest_dist)
        else:
            distance_m = 0 if explicit_obj else None

        # Check if changed
        changed = current_obj_id is not None and current_obj_id != prev_obj_id
        
        # Load posts — ONLY for the active (selected) object, never spill from other objects
        posts = []
        if active_obj:
            post_query = {}
            if current_obj_id and location_id:
                post_query = {"$or": [{"object_id": current_obj_id}, {"location_id": location_id}]}
            elif current_obj_id:
                post_query = {"object_id": current_obj_id}
            elif location_id:
                post_query = {"location_id": location_id}

            if post_query:
                posts = list(db.posts.find(post_query).sort("createdAt", -1))
            
        # Emit Socket.IO event if changed
        if changed:
            serialized_near = serialize_mongo(active_obj)
            serialized_posts = serialize_mongo(posts)
            geofence_name = nearest["name"] if nearest else current_obj_name
            print(f"[SIMULATOR] Object changed to: {current_obj_name}. Emitting Live Event...")
            socketio.emit("object_changed", {
                "object": serialized_near,
                "posts": serialized_posts,
                "geofence_name": geofence_name
            })
            
        # Return the stored coordinates of the active object for map panning
        # (no Gemini calls here — coordinate fixing is done via /api/admin/fix-coordinates)
        real_lat = None
        real_lng = None
        if active_obj:
            obj_lat = active_obj.get("latitude")
            obj_lng = active_obj.get("longitude")
            if obj_lat is not None and obj_lng is not None:
                stored_lat = float(obj_lat)
                stored_lng = float(obj_lng)
                # Only send real_lat/real_lng if they differ from where the user thinks they are
                if abs(stored_lat - lat) > 0.001 or abs(stored_lng - lng) > 0.001:
                    real_lat = stored_lat
                    real_lng = stored_lng

        return jsonify({
            "currentObjectId": current_obj_id,
            "currentObjectName": current_obj_name,
            "locationId": location_id,
            "distance_m": distance_m,
            "geofence_hit": geofence_hit,
            "geofence_object": nearest["name"] if nearest else None,
            "changed": changed,
            "real_lat": real_lat,
            "real_lng": real_lng,
            "posts": serialize_mongo(posts)
        })
        
    except Exception as e:
        print(f"[ERROR] Simulation route: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats', methods=['GET'])
def api_stats():
    try:
        stats_list = []
        with open(CLASS_MAPPING_FILE, 'r') as f:
            mapping = json.load(f)
            
        rejections = {}
        if os.path.exists(REJECTION_LOG_FILE):
            try:
                with open(REJECTION_LOG_FILE, 'r') as f:
                    rejections = json.load(f)
            except:
                pass
                
        for class_name, class_id in mapping.items():
            if class_id < 3:
                continue # Skip base classes
                
            class_dir = os.path.join(PENDING_DIR, class_name)
            images_dir = os.path.join(class_dir, "images")
            verified_count = 0
            if os.path.exists(images_dir):
                verified_count = len([f for f in os.listdir(images_dir) if os.path.isfile(os.path.join(images_dir, f))])
                
            rejected_count = rejections.get(class_name, 0)
            
            # Readiness
            if verified_count <= 4:
                readiness = "Insufficient Data"
            elif verified_count <= 19:
                readiness = "Few-Shot Ready"
            else:
                readiness = "Fine-Tuning Ready"
                
            stats_list.append({
                "class_name": class_name,
                "class_id": class_id,
                "verified": verified_count,
                "rejected": rejected_count,
                "readiness": readiness
            })
            
        return jsonify({'stats': stats_list})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/prepare_dataset', methods=['POST'])
def api_prepare_dataset():
    try:
        # Original dataset setup
        orig_ds_dir = "egypt-landmarks-3-classes"
        
        # Verify it exists
        if not os.path.exists(orig_ds_dir):
            # Fallback path try
            orig_ds_dir = "../egypt-landmarks-3-classes"
            if not os.path.exists(orig_ds_dir):
                orig_ds_dir = r"D:\Gradautaion_Project\egypt-landmarks-3-classes"
                
        if not os.path.exists(CLASS_MAPPING_FILE):
            return jsonify({'error': 'Class mapping file missing.'}), 400
            
        with open(CLASS_MAPPING_FILE, 'r') as f:
            mapping = json.load(f)
            
        # Clean target directory
        if os.path.exists(EXPANDED_DATASET_DIR):
            shutil.rmtree(EXPANDED_DATASET_DIR)
        os.makedirs(EXPANDED_DATASET_DIR, exist_ok=True)
        
        # Copy base dataset splits
        splits = ['train', 'valid', 'test']
        for split in splits:
            dest_img_dir = os.path.join(EXPANDED_DATASET_DIR, split, "images")
            dest_lbl_dir = os.path.join(EXPANDED_DATASET_DIR, split, "labels")
            os.makedirs(dest_img_dir, exist_ok=True)
            os.makedirs(dest_lbl_dir, exist_ok=True)
            
            src_img_dir = os.path.join(orig_ds_dir, split, "images")
            src_lbl_dir = os.path.join(orig_ds_dir, split, "labels")
            
            if os.path.exists(src_img_dir):
                for f in os.listdir(src_img_dir):
                    shutil.copy2(os.path.join(src_img_dir, f), os.path.join(dest_img_dir, f))
            if os.path.exists(src_lbl_dir):
                for f in os.listdir(src_lbl_dir):
                    shutil.copy2(os.path.join(src_lbl_dir, f), os.path.join(dest_lbl_dir, f))
                    
        # Export custom pending datasets
        for class_name, class_id in mapping.items():
            if class_id < 3:
                continue
            class_dir = os.path.join(PENDING_DIR, class_name)
            images_dir = os.path.join(class_dir, "images")
            labels_dir = os.path.join(class_dir, "labels")
            
            if not os.path.exists(images_dir) or not os.path.exists(labels_dir):
                continue
                
            img_files = os.listdir(images_dir)
            pairs = []
            for img_file in img_files:
                img_hash, ext = os.path.splitext(img_file)
                lbl_file = f"{img_hash}.txt"
                lbl_path = os.path.join(labels_dir, lbl_file)
                if os.path.exists(lbl_path):
                    pairs.append((
                        os.path.join(images_dir, img_file),
                        lbl_path,
                        img_file,
                        lbl_file
                    ))
                    
            n = len(pairs)
            if n == 0: continue
            
            random.seed(42)
            random.shuffle(pairs)
            
            n_train = int(n * 0.70)
            n_val = int(n * 0.15)
            if n > 1 and n_val == 0:
                n_val = 1
            n_test = n - n_train - n_val
            if n_test < 0:
                n_test = 0
                n_train = n - n_val
                
            train_pairs = pairs[:n_train]
            val_pairs = pairs[n_train:n_train + n_val]
            test_pairs = pairs[n_train + n_val:]
            
            split_map = {
                'train': train_pairs,
                'valid': val_pairs,
                'test': test_pairs
            }
            
            for split, split_pairs in split_map.items():
                dest_img_dir = os.path.join(EXPANDED_DATASET_DIR, split, "images")
                dest_lbl_dir = os.path.join(EXPANDED_DATASET_DIR, split, "labels")
                
                for src_img, src_lbl, img_name, lbl_name in split_pairs:
                    shutil.copy2(src_img, os.path.join(dest_img_dir, img_name))
                    shutil.copy2(src_lbl, os.path.join(dest_lbl_dir, lbl_name))
                    
        # Write data.yaml
        sorted_names = {int(v): k for k, v in mapping.items()}
        sorted_names = dict(sorted(sorted_names.items()))
        
        data_yaml = {
            'path': 'expanded_dataset',
            'train': 'train/images',
            'val': 'valid/images',
            'test': 'test/images',
            'names': sorted_names
        }
        
        yaml_path = os.path.join(EXPANDED_DATASET_DIR, "data.yaml")
        with open(yaml_path, 'w') as f:
            yaml.safe_dump(data_yaml, f, default_flow_style=False, sort_keys=False)
            
        return jsonify({
            'success': True,
            'dataset_path': os.path.abspath(EXPANDED_DATASET_DIR),
            'class_mapping': sorted_names
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/analytics', methods=['GET'])
def api_analytics():
    # Read training results
    v8_csv_paths = [
        "runs/train_landmarks_colab/New_results.csv",
        "runs/train_landmarks_colab/results.csv",
        "runs/train_landmarks/results.csv"
    ]
    
    v8_csv = next((p for p in v8_csv_paths if os.path.exists(p)), None)
    
    v8_data = None
    if v8_csv:
        try:
            epochs, mAP50, precision, recall, box_loss, cls_loss = [], [], [], [], [], []
            import csv
            with open(v8_csv, mode='r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    row = {k.strip(): v for k, v in row.items()}
                    epochs.append(int(row.get('epoch', 0)))
                    box_loss.append(float(row.get('train/box_loss', row.get('box_loss', 0))))
                    cls_loss.append(float(row.get('train/cls_loss', row.get('cls_loss', 0))))
                    precision.append(float(row.get('metrics/precision(B)', row.get('metrics/precision', 0))))
                    recall.append(float(row.get('metrics/recall(B)', row.get('metrics/recall', 0))))
                    mAP50.append(float(row.get('metrics/mAP50(B)', row.get('metrics/mAP50', 0))))
            v8_data = {
                'epochs': epochs,
                'box_loss': box_loss,
                'cls_loss': cls_loss,
                'precision': precision,
                'recall': recall,
                'mAP50': mAP50
            }
        except Exception as e:
            print(f"[ERROR] Parsing CSV results: {e}")
            
    # Simulated YOLO11 results (Demo Mode)
    y11_data = None
    is_simulated = False
    if v8_data:
        random.seed(42)
        y11_data = {
            'epochs': v8_data['epochs'],
            'mAP50': [],
            'precision': [],
            'recall': [],
            'box_loss': [],
            'cls_loss': []
        }
        for i in range(len(v8_data['epochs'])):
            y11_data['mAP50'].append(min(0.99, v8_data['mAP50'][i] * random.uniform(1.005, 1.015)))
            y11_data['precision'].append(min(0.99, v8_data['precision'][i] * random.uniform(1.005, 1.02)))
            y11_data['recall'].append(min(0.99, v8_data['recall'][i] * random.uniform(1.005, 1.015)))
            y11_data['box_loss'].append(v8_data['box_loss'][i] * random.uniform(0.92, 0.96))
            y11_data['cls_loss'].append(v8_data['cls_loss'][i] * random.uniform(0.92, 0.96))
        is_simulated = True
        
    return jsonify({
        'v8': v8_data,
        'y11': y11_data,
        'is_y11_simulated': is_simulated
    })

@app.route('/api/health', methods=['GET'])
def api_health():
    """Quick health check — Railway uses this to verify the app is alive."""
    return jsonify({
        'status': 'ok',
        'models_loaded': {
            'yolov8': _yolo_v8 is not None,
            'yolo11': _yolo_y11 is not None,
            'yolo_world': yolo_world_model is not None
        }
    })

# ─── Background Model Warmup ──────────────────────────────────────────────────
def _warmup_models():
    """Pre-load YOLO models in the background so the first user request is fast."""
    import threading
    def _load():
        try:
            print("[WARMUP] Pre-loading YOLOv8 model...")
            get_yolo_v8()
            print("[WARMUP] YOLOv8 ready.")
            print("[WARMUP] Pre-loading YOLO11 model...")
            get_yolo_y11()
            print("[WARMUP] YOLO11 ready.")
            print("[WARMUP] All models pre-loaded successfully.")
        except Exception as e:
            print(f"[WARMUP] Model pre-load failed (non-fatal): {e}")
    t = threading.Thread(target=_load, daemon=True)
    t.start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    print(f"[SUCCESS] Starting PharaohScan Server on http://localhost:{port}...")
    _warmup_models()
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)
else:
    # Running under gunicorn — warmup after first request context is ready
    _warmup_models()
