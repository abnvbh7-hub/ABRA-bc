from database import pool
import os
from fastapi import Depends, FastAPI, UploadFile, File, Query, Request
from fastapi.responses import StreamingResponse, FileResponse
import uvicorn
from models import AbraModel, LoginModel, GalleryModel, PaymentModel, PersonUpdateModel, ProcessGalleryModel, ResolveSuggestionModel
from auth import create_access_token, verify_access_token
from facial import extract_faces_from_image, find_matching_person, cosine_similarity, classify_face_match
from cache_manager import get_image_file_path, get_or_fetch_image_bytes, sanitize_key, IMAGES_DIR, THUMBS_DIR
import csv
import io
import json
import gc
import urllib.request
import urllib.parse
from datetime import datetime, date, timezone
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import boto3
from botocore.client import Config
import uuid
import re
from dateutil import parser as date_parser
import numpy as np
from sklearn.cluster import DBSCAN

app = FastAPI()

def init_db_schema():
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS abra_people (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        name TEXT,
                        avatar_data TEXT,
                        embeddings JSONB DEFAULT '[]'::jsonb,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    );
                    ALTER TABLE abragallery ADD COLUMN IF NOT EXISTS person_ids JSONB DEFAULT '[]'::jsonb;
                    CREATE TABLE IF NOT EXISTS abra_face_suggestions (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        photo_id INTEGER NOT NULL,
                        person_id UUID NOT NULL,
                        similarity DOUBLE PRECISION NOT NULL,
                        avatar_data TEXT,
                        embedding JSONB,
                        status TEXT DEFAULT 'pending',
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                conn.commit()
    except Exception as e:
        print(f"[DB Schema Init]: {e}")

init_db_schema()

_geocode_cache = {}

def reverse_geocode(lat: float, lon: float) -> str:
    if lat is None or lon is None:
        return "Unknown Location"
    key = (round(float(lat), 3), round(float(lon), 3))
    if key in _geocode_cache:
        return _geocode_cache[key]
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=16&addressdetails=1"
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'ABRA-Assistant/1.0 (Location Analytics)'}
        )
        with urllib.request.urlopen(req, timeout=2.0) as response:
            if response.status == 200:
                data = json.loads(response.read().decode())
                addr = data.get('address', {})
                parts = []
                name_cand = (
                    addr.get('suburb') or 
                    addr.get('neighbourhood') or 
                    addr.get('residential') or 
                    addr.get('commercial') or 
                    addr.get('amenity') or
                    addr.get('road') or
                    addr.get('quarter') or
                    data.get('name')
                )
                city_cand = addr.get('city') or addr.get('town') or addr.get('county') or addr.get('state_district')
                if name_cand:
                    parts.append(str(name_cand))
                if city_cand and city_cand != name_cand:
                    parts.append(str(city_cand))
                
                clean_name = ", ".join(parts) if parts else (data.get('display_name', '').split(',')[0] if data.get('display_name') else None)
                if clean_name:
                    _geocode_cache[key] = clean_name
                    return clean_name
    except Exception as e:
        pass
    
    fallback = f"Location ({round(float(lat), 3)}, {round(float(lon), 3)})"
    _geocode_cache[key] = fallback
    return fallback

s3 = boto3.client(
    's3',
    endpoint_url=f"https://{os.getenv('BLAZE_ENDPOINT')}",
    aws_access_key_id=os.getenv('BLAZE_KEYID'),
    aws_secret_access_key=os.getenv('BLAZE_APPKEY'),
    config=Config(signature_version='s3v4')
)
B2_BUCKET_NAME = os.getenv('B2_BUCKET_NAME')


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def read_root():
    return {"Adaptive Behavioral Reasoning Assistant": "ABRA"}

@app.get("/reverse_geocode")
async def get_reverse_geocode(lat: float, lon: float):
    name = reverse_geocode(lat, lon)
    return {"status": "success", "name": name, "lat": lat, "lon": lon}

@app.post('/login')
async def login(data: LoginModel):
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT username,password from auth limit 1")
                user = cur.fetchone()
                if user and data.username == user[0] and data.password == user[1]:
                    token = create_access_token({"username": data.username})
                    return {"status": "success", "token": token}
                else:
                    return {"status": "error", "message": "Invalid username or password"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/punch")
async def log_punch(data: AbraModel, token: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    try:
        verify_access_token(token.credentials)
    except Exception as e:
        return {"status": "error", "message": str(e)}
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO abradb (
                        timestamp,
                        day,
                        latitude,
                        longitude,
                        speed,
                        direction,
                        accel_x,
                        accel_y,
                        accel_z,
                        gyro_x,
                        gyro_y,
                        gyro_z,
                        wifi_count,
                        vendor,
                        amount,
                        battery_level,
                        is_charging,
                        network_type
                    )
                    VALUES (
                        CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Kolkata',
                        (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Kolkata')::date,
                        %(latitude)s,
                        %(longitude)s,
                        %(speed)s,
                        %(direction)s,
                        %(accel_x)s,
                        %(accel_y)s,
                        %(accel_z)s,
                        %(gyro_x)s,
                        %(gyro_y)s,
                        %(gyro_z)s,
                        %(wifi_count)s,
                        %(vendor)s,
                        %(amount)s,
                        %(battery_level)s,
                        %(is_charging)s,
                        %(network_type)s
                    )
                    """,
                    data.model_dump()
                )

        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/pick")
async def pick_data(token: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    try:
        verify_access_token(token.credentials)
    except Exception as e:
        return {"status": "error", "message": str(e)}
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM abradb ORDER BY timestamp DESC LIMIT 100")
                rows = cur.fetchall()
                columns = [desc[0] for desc in cur.description]
                result = [dict(zip(columns, row)) for row in rows]

        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/payments")
async def get_payments(range: str = "all", token: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    try:
        verify_access_token(token.credentials)
    except Exception as e:
        return {"status": "error", "message": str(e)}
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                if range == "all" or not range:
                    cur.execute("SELECT * FROM abradb WHERE amount IS NOT NULL AND vendor IS NOT NULL ORDER BY timestamp DESC LIMIT 1000")
                elif range == "today":
                    cur.execute("""
                        SELECT * FROM abradb 
                        WHERE amount IS NOT NULL AND vendor IS NOT NULL 
                          AND (
                            (timestamp::timestamptz AT TIME ZONE 'Asia/Kolkata')::date = (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Kolkata')::date
                            OR day = (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Kolkata')::date 
                            OR DATE(timestamp) = (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Kolkata')::date
                          )
                        ORDER BY timestamp DESC
                    """)
                elif range == "yesterday":
                    cur.execute("""
                        SELECT * FROM abradb 
                        WHERE amount IS NOT NULL AND vendor IS NOT NULL 
                          AND (
                            (timestamp::timestamptz AT TIME ZONE 'Asia/Kolkata')::date = (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Kolkata')::date - INTERVAL '1 day'
                            OR day = (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Kolkata')::date - INTERVAL '1 day' 
                            OR DATE(timestamp) = (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Kolkata')::date - INTERVAL '1 day'
                          )
                        ORDER BY timestamp DESC
                    """)
                else:
                    cur.execute("""
                        SELECT * FROM abradb 
                        WHERE amount IS NOT NULL AND vendor IS NOT NULL 
                          AND (
                            (timestamp::timestamptz AT TIME ZONE 'Asia/Kolkata')::date = %s::date
                            OR day = %s::date 
                            OR DATE(timestamp) = %s::date
                          )
                        ORDER BY timestamp DESC
                    """, (range, range, range))
                    
                rows = cur.fetchall()
                columns = [desc[0] for desc in cur.description]
                result = [dict(zip(columns, row)) for row in rows]

        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/payments")
async def add_payment(data: PaymentModel, token: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    try:
        verify_access_token(token.credentials)
    except Exception as e:
        return {"status": "error", "message": str(e)}
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                if data.timestamp:
                    ts_str = data.timestamp.isoformat() if hasattr(data.timestamp, 'isoformat') else str(data.timestamp)
                    cur.execute("""
                        INSERT INTO abradb (
                            timestamp,
                            day,
                            latitude,
                            longitude,
                            vendor,
                            amount
                        )
                        VALUES (
                            %(timestamp)s::timestamptz,
                            (%(timestamp)s::timestamptz AT TIME ZONE 'Asia/Kolkata')::date,
                            %(latitude)s,
                            %(longitude)s,
                            %(vendor)s,
                            %(amount)s
                        )
                        RETURNING id
                    """, {
                        "timestamp": ts_str,
                        "latitude": data.latitude,
                        "longitude": data.longitude,
                        "vendor": data.vendor,
                        "amount": data.amount
                    })
                else:
                    cur.execute("""
                        INSERT INTO abradb (
                            timestamp,
                            day,
                            latitude,
                            longitude,
                            vendor,
                            amount
                        )
                        VALUES (
                            CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Kolkata',
                            (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Kolkata')::date,
                            %(latitude)s,
                            %(longitude)s,
                            %(vendor)s,
                            %(amount)s
                        )
                        RETURNING id
                    """, {
                        "latitude": data.latitude,
                        "longitude": data.longitude,
                        "vendor": data.vendor,
                        "amount": data.amount
                    })
                new_id = cur.fetchone()[0]
                conn.commit()
        return {"status": "success", "id": new_id, "message": "Payment added successfully"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.put("/payments/{payment_id}")
async def update_payment(payment_id: int, data: PaymentModel, token: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    try:
        verify_access_token(token.credentials)
    except Exception as e:
        return {"status": "error", "message": str(e)}
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                ts_str = (data.timestamp.isoformat() if hasattr(data.timestamp, 'isoformat') else str(data.timestamp)) if data.timestamp else None
                cur.execute("""
                    UPDATE abradb
                    SET vendor = %(vendor)s,
                        amount = %(amount)s,
                        latitude = COALESCE(%(latitude)s, latitude),
                        longitude = COALESCE(%(longitude)s, longitude),
                        timestamp = COALESCE(%(timestamp)s::timestamptz, timestamp),
                        day = COALESCE((%(timestamp)s::timestamptz AT TIME ZONE 'Asia/Kolkata')::date, day)
                    WHERE id = %(id)s
                """, {
                    "id": payment_id,
                    "vendor": data.vendor,
                    "amount": data.amount,
                    "latitude": data.latitude,
                    "longitude": data.longitude,
                    "timestamp": ts_str
                })
                conn.commit()
        return {"status": "success", "message": "Payment updated successfully"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.delete("/payments/{payment_id}")
async def delete_payment(payment_id: int, token: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    try:
        verify_access_token(token.credentials)
    except Exception as e:
        return {"status": "error", "message": str(e)}
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT accel_x, gyro_x, speed FROM abradb WHERE id = %s", (payment_id,))
                row = cur.fetchone()
                if row and (row[0] is not None or row[1] is not None or row[2] is not None):
                    cur.execute("UPDATE abradb SET amount = NULL, vendor = NULL WHERE id = %s", (payment_id,))
                else:
                    cur.execute("DELETE FROM abradb WHERE id = %s", (payment_id,))
                conn.commit()
        return {"status": "success", "message": "Payment deleted successfully"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/upload_url")
async def get_upload_url(content_type: str, token: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    try:
        verify_access_token(token.credentials)
    except Exception as e:
        return {"status": "error", "message": str(e)}
    
    object_key = f"{uuid.uuid4()}"
    try:
        presigned_url = s3.generate_presigned_url(
            ClientMethod='put_object',
            Params={
                'Bucket': B2_BUCKET_NAME,
                'Key': object_key,
                'ContentType': content_type
            },
            ExpiresIn=3600
        )
        return {"status": "success", "upload_url": presigned_url, "object_key": object_key}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/media/{object_key:path}")
async def serve_cached_media(object_key: str, thumb: bool = False):
    """
    Serves media directly from local disk cache with long-lived browser caching headers.
    If not yet in local cache, fetches once from S3, stores locally, and streams immediately.
    If thumb=True, serves a lightweight, high-performance thumbnail (e.g. 20-40KB).
    """
    try:
        path, mime = get_image_file_path(object_key, s3, B2_BUCKET_NAME, thumb=thumb)
        if not path or not path.exists():
            return {"status": "error", "message": "Media not found"}

        return FileResponse(
            path=str(path),
            media_type=mime,
            headers={
                "Cache-Control": "public, max-age=31536000, immutable",
                "ETag": f'"{sanitize_key(object_key)}{"-thumb" if thumb else ""}"'
            }
        )
    except Exception as e:
        print(f"[MediaServe Error] {object_key}: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/gallery/cache/status")
async def get_cache_status(token: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    try:
        verify_access_token(token.credentials)
    except Exception as e:
        return {"status": "error", "message": str(e)}
    try:
        image_files = [f for f in IMAGES_DIR.iterdir() if f.is_file()]
        thumb_files = [f for f in THUMBS_DIR.iterdir() if f.is_file()]
        total_bytes = sum(f.stat().st_size for f in image_files) + sum(f.stat().st_size for f in thumb_files)
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM abragallery WHERE object_key IS NOT NULL")
                total_in_db = cur.fetchone()[0]
        return {
            "status": "success",
            "cached_images": len(image_files),
            "cached_thumbnails": len(thumb_files),
            "total_gallery_images": total_in_db,
            "cache_size_mb": round(total_bytes / (1024 * 1024), 2)
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/gallery/cache/warmup")
async def warmup_gallery_cache(token: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    try:
        verify_access_token(token.credentials)
    except Exception as e:
        return {"status": "error", "message": str(e)}
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT object_key FROM abragallery WHERE object_key IS NOT NULL")
                keys = [r[0] for r in cur.fetchall()]

        cached_count = 0
        for k in keys:
            path, _ = get_image_file_path(k, s3, B2_BUCKET_NAME, thumb=False)
            get_image_file_path(k, s3, B2_BUCKET_NAME, thumb=True)
            if path:
                cached_count += 1

        return {"status": "success", "message": f"Pre-cached {cached_count}/{len(keys)} gallery images and thumbnails."}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/gallery")
async def get_gallery(request: Request, token: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    try:
        verify_access_token(token.credentials)
    except Exception as e:
        return {"status": "error", "message": str(e)}
    try:
        base_url = str(request.base_url).rstrip("/")
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM abragallery ORDER BY timestamp DESC")
                rows = cur.fetchall()
                columns = [desc[0] for desc in cur.description]
                result = [dict(zip(columns, row)) for row in rows]
                
                for item in result:
                    if item.get("object_key"):
                        okey = item["object_key"]
                        item["cached_url"] = f"{base_url}/media/{okey}"
                        item["thumbnail_url"] = f"{base_url}/media/{okey}?thumb=true"
                        item["url"] = f"{base_url}/media/{okey}"
                        try:
                            item["s3_url"] = s3.generate_presigned_url(
                                ClientMethod='get_object',
                                Params={'Bucket': B2_BUCKET_NAME, 'Key': okey},
                                ExpiresIn=3600
                            )
                        except Exception:
                            item["s3_url"] = None

        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/gallery")
async def post_gallery(data: GalleryModel, token: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    try:
        verify_access_token(token.credentials)
    except Exception as e:
        return {"status": "error", "message": str(e)}
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO abragallery (
                        url,
                        object_key,
                        latitude,
                        longitude,
                        timestamp,
                        speed,
                        battery_level,
                        is_charging,
                        network_type,
                        person_ids
                    )
                    VALUES (
                        %(url)s,
                        %(object_key)s,
                        %(latitude)s,
                        %(longitude)s,
                        %(timestamp)s,
                        %(speed)s,
                        %(battery_level)s,
                        %(is_charging)s,
                        %(network_type)s,
                        %(person_ids)s
                    )
                    """,
                    {
                        **data.model_dump(),
                        "person_ids": json.dumps(data.person_ids or [])
                    }
                )
                conn.commit()
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.delete("/gallery/{item_id}")
async def delete_gallery(item_id: int, token: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    try:
        verify_access_token(token.credentials)
    except Exception as e:
        return {"status": "error", "message": str(e)}
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT object_key FROM abragallery WHERE id = %s", (item_id,))
                row = cur.fetchone()
                if row and row[0]:
                    try:
                        s3.delete_object(Bucket=B2_BUCKET_NAME, Key=row[0])
                    except Exception as e:
                        print("Failed to delete from B2:", e)
                cur.execute("DELETE FROM abragallery WHERE id = %s", (item_id,))
                conn.commit()
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/history")
async def history_data(range: str = "today", token: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    try:
        verify_access_token(token.credentials)
    except Exception as e:
        return {"status": "error", "message": str(e)}
        
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                if range == "yesterday":
                    cur.execute("SELECT * FROM abradb WHERE DATE(timestamp) = CURRENT_DATE - INTERVAL '1 day' ORDER BY timestamp ASC")
                elif range == "today":
                    cur.execute("SELECT * FROM abradb WHERE DATE(timestamp) = CURRENT_DATE ORDER BY timestamp ASC")
                else:
                    # Assume range is YYYY-MM-DD
                    cur.execute("SELECT * FROM abradb WHERE DATE(timestamp) = %s ORDER BY timestamp ASC", (range,))
                    
                rows = cur.fetchall()
                columns = [desc[0] for desc in cur.description]
                result = [dict(zip(columns, row)) for row in rows]
                
        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/clusters")
async def get_clusters(
    range: str = "today", 
    eps_meters: float = 50.0, 
    min_samples: int = 5, 
    token: HTTPAuthorizationCredentials = Depends(HTTPBearer())
):
    try:
        verify_access_token(token.credentials)
    except Exception as e:
        return {"status": "error", "message": str(e)}
        
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                if range == "yesterday":
                    cur.execute("""
                        SELECT id, timestamp, latitude, longitude, speed, battery_level, is_charging, network_type, wifi_count, vendor, amount 
                        FROM abradb 
                        WHERE (day = (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Kolkata')::date - INTERVAL '1 day' 
                               OR DATE(timestamp) = (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Kolkata')::date - INTERVAL '1 day')
                          AND latitude IS NOT NULL 
                          AND longitude IS NOT NULL 
                        ORDER BY timestamp ASC
                    """)
                elif range == "today":
                    cur.execute("""
                        SELECT id, timestamp, latitude, longitude, speed, battery_level, is_charging, network_type, wifi_count, vendor, amount 
                        FROM abradb 
                        WHERE (day = (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Kolkata')::date 
                               OR DATE(timestamp) = (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Kolkata')::date)
                          AND latitude IS NOT NULL 
                          AND longitude IS NOT NULL 
                        ORDER BY timestamp ASC
                    """)
                elif range == "all":
                    cur.execute("""
                        SELECT id, timestamp, latitude, longitude, speed, battery_level, is_charging, network_type, wifi_count, vendor, amount 
                        FROM abradb 
                        WHERE latitude IS NOT NULL 
                          AND longitude IS NOT NULL 
                        ORDER BY timestamp ASC LIMIT 5000
                    """)
                else:
                    cur.execute("""
                        SELECT id, timestamp, latitude, longitude, speed, battery_level, is_charging, network_type, wifi_count, vendor, amount 
                        FROM abradb 
                        WHERE (day = %s::date OR DATE(timestamp) = %s::date)
                          AND latitude IS NOT NULL 
                          AND longitude IS NOT NULL 
                        ORDER BY timestamp ASC
                    """, (range, range))
                    
                rows = cur.fetchall()
                columns = [desc[0] for desc in cur.description]
                raw_data = [dict(zip(columns, row)) for row in rows]

        if not raw_data or len(raw_data) < min_samples:
            return {
                "status": "success",
                "range": range,
                "eps_meters": eps_meters,
                "min_samples": min_samples,
                "total_points": len(raw_data),
                "total_clusters": 0,
                "clustered_points_count": 0,
                "noise_count": len(raw_data),
                "clusters": [],
                "noise_points": []
            }

        coords_deg = np.array([[float(item['latitude']), float(item['longitude'])] for item in raw_data], dtype=np.float64)
        coords_rad = np.radians(coords_deg)

        kms_per_radian = 6371.0088
        eps_rad = (eps_meters / 1000.0) / kms_per_radian

        db = DBSCAN(eps=eps_rad, min_samples=min_samples, metric='haversine', algorithm='ball_tree')
        labels = db.fit_predict(coords_rad)

        cluster_map = {}
        noise_points = []

        palette = [
            "#3b82f6", "#10b981", "#f59e0b", "#ec4899", 
            "#8b5cf6", "#06b6d4", "#f97316", "#14b8a6", 
            "#6366f1", "#84cc16", "#a855f7", "#e11d48",
            "#0284c7", "#16a34a", "#d97706", "#db2777"
        ]

        for idx, item in enumerate(raw_data):
            label = int(labels[idx])
            ts = item['timestamp'].isoformat() if hasattr(item['timestamp'], 'isoformat') else str(item['timestamp'])
            pt = {
                "id": item['id'],
                "lat": float(item['latitude']),
                "lon": float(item['longitude']),
                "time": ts,
                "speed": float(item['speed']) if item['speed'] is not None else 0.0,
                "battery": item['battery_level'],
                "charging": item['is_charging'],
                "network": item['network_type'],
                "vendor": item['vendor'],
                "amount": float(item['amount']) if item['amount'] is not None else None
            }
            if label == -1:
                noise_points.append(pt)
            else:
                if label not in cluster_map:
                    cluster_map[label] = []
                cluster_map[label].append(pt)

        clusters = []
        for cluster_id, pts in cluster_map.items():
            lats = [p['lat'] for p in pts]
            lons = [p['lon'] for p in pts]
            speeds = [p['speed'] for p in pts if p['speed'] is not None]
            payments = [p for p in pts if p['amount'] is not None]
            
            center_lat = float(np.mean(lats))
            center_lon = float(np.mean(lons))
            
            d_lat = np.radians(np.array(lats) - center_lat)
            d_lon = np.radians(np.array(lons) - center_lon)
            a = np.sin(d_lat / 2.0)**2 + np.cos(np.radians(center_lat)) * np.cos(np.radians(lats)) * np.sin(d_lon / 2.0)**2
            c = 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
            dists_meters = c * kms_per_radian * 1000.0
            radius_meters = float(np.max(dists_meters)) if len(dists_meters) > 0 else 0.0

            start_time = pts[0]['time']
            end_time = pts[-1]['time']
            
            try:
                dt_start = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                dt_end = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                duration_mins = max(1, round((dt_end - dt_start).total_seconds() / 60))
            except Exception:
                duration_mins = len(pts)

            loc_name = reverse_geocode(center_lat, center_lon)
            clusters.append({
                "cluster_id": cluster_id,
                "cluster_num": len(clusters) + 1,
                "name": loc_name,
                "location_name": loc_name,
                "color": palette[cluster_id % len(palette)],
                "point_count": len(pts),
                "center": {
                    "lat": round(center_lat, 6),
                    "lon": round(center_lon, 6)
                },
                "radius_meters": round(radius_meters, 1),
                "bounds": {
                    "min_lat": min(lats),
                    "max_lat": max(lats),
                    "min_lon": min(lons),
                    "max_lon": max(lons)
                },
                "start_time": start_time,
                "end_time": end_time,
                "duration_minutes": duration_mins,
                "avg_speed": round(float(np.mean(speeds)), 1) if speeds else 0.0,
                "max_speed": round(float(np.max(speeds)), 1) if speeds else 0.0,
                "payments": payments,
                "points": pts
            })

        # Sort clusters by point count descending and re-assign 1-based index numbers
        clusters.sort(key=lambda c: c['point_count'], reverse=True)
        for i, c in enumerate(clusters):
            c['cluster_num'] = i + 1

        return {
            "status": "success",
            "range": range,
            "eps_meters": eps_meters,
            "min_samples": min_samples,
            "total_points": len(raw_data),
            "total_clusters": len(clusters),
            "clustered_points_count": len(raw_data) - len(noise_points),
            "noise_count": len(noise_points),
            "clusters": clusters,
            "noise_points": noise_points
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/payment_clusters")
async def get_payment_clusters(
    range: str = "all",
    eps_meters: float = 100.0,
    min_samples: int = 1,
    token: HTTPAuthorizationCredentials = Depends(HTTPBearer())
):
    try:
        verify_access_token(token.credentials)
    except Exception as e:
        return {"status": "error", "message": str(e)}
        
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                if range == "all" or not range:
                    cur.execute("""
                        SELECT id, timestamp, latitude, longitude, amount, vendor, speed, battery_level, network_type
                        FROM abradb 
                        WHERE amount IS NOT NULL 
                          AND vendor IS NOT NULL 
                          AND latitude IS NOT NULL 
                          AND longitude IS NOT NULL
                        ORDER BY timestamp DESC LIMIT 2000
                    """)
                elif range == "today":
                    cur.execute("""
                        SELECT id, timestamp, latitude, longitude, amount, vendor, speed, battery_level, network_type
                        FROM abradb 
                        WHERE amount IS NOT NULL 
                          AND vendor IS NOT NULL 
                          AND latitude IS NOT NULL 
                          AND longitude IS NOT NULL
                          AND (
                            (timestamp::timestamptz AT TIME ZONE 'Asia/Kolkata')::date = (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Kolkata')::date
                            OR day = (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Kolkata')::date 
                            OR DATE(timestamp) = (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Kolkata')::date
                          )
                        ORDER BY timestamp DESC
                    """)
                elif range == "yesterday":
                    cur.execute("""
                        SELECT id, timestamp, latitude, longitude, amount, vendor, speed, battery_level, network_type
                        FROM abradb 
                        WHERE amount IS NOT NULL 
                          AND vendor IS NOT NULL 
                          AND latitude IS NOT NULL 
                          AND longitude IS NOT NULL
                          AND (
                            (timestamp::timestamptz AT TIME ZONE 'Asia/Kolkata')::date = (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Kolkata')::date - INTERVAL '1 day'
                            OR day = (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Kolkata')::date - INTERVAL '1 day' 
                            OR DATE(timestamp) = (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Kolkata')::date - INTERVAL '1 day'
                          )
                        ORDER BY timestamp DESC
                    """)
                else:
                    cur.execute("""
                        SELECT id, timestamp, latitude, longitude, amount, vendor, speed, battery_level, network_type
                        FROM abradb 
                        WHERE amount IS NOT NULL 
                          AND vendor IS NOT NULL 
                          AND latitude IS NOT NULL 
                          AND longitude IS NOT NULL
                          AND (
                            (timestamp::timestamptz AT TIME ZONE 'Asia/Kolkata')::date = %s::date
                            OR day = %s::date 
                            OR DATE(timestamp) = %s::date
                          )
                        ORDER BY timestamp DESC
                    """, (range, range, range))
                rows = cur.fetchall()
                columns = [desc[0] for desc in cur.description]
                raw_data = [dict(zip(columns, row)) for row in rows]

        if not raw_data:
            return {
                "status": "success",
                "eps_meters": eps_meters,
                "min_samples": min_samples,
                "total_payments": 0,
                "total_clusters": 0,
                "total_amount": 0.0,
                "clusters": [],
                "noise_payments": []
            }

        coords_deg = np.array([[float(item['latitude']), float(item['longitude'])] for item in raw_data], dtype=np.float64)
        coords_rad = np.radians(coords_deg)

        kms_per_radian = 6371.0088
        eps_rad = (eps_meters / 1000.0) / kms_per_radian

        db = DBSCAN(eps=eps_rad, min_samples=min_samples, metric='haversine', algorithm='ball_tree')
        labels = db.fit_predict(coords_rad)

        cluster_map = {}
        noise_payments = []

        palette = [
            "#10b981", "#3b82f6", "#f59e0b", "#ec4899", 
            "#8b5cf6", "#06b6d4", "#f97316", "#14b8a6", 
            "#6366f1", "#84cc16", "#a855f7", "#e11d48",
            "#0284c7", "#16a34a", "#d97706", "#db2777"
        ]

        total_amount_all = sum(float(item['amount']) for item in raw_data if item['amount'] is not None)

        for idx, item in enumerate(raw_data):
            label = int(labels[idx])
            ts = item['timestamp'].isoformat() if hasattr(item['timestamp'], 'isoformat') else str(item['timestamp'])
            pt = {
                "id": item['id'],
                "latitude": float(item['latitude']),
                "longitude": float(item['longitude']),
                "lat": float(item['latitude']),
                "lon": float(item['longitude']),
                "timestamp": ts,
                "vendor": item['vendor'],
                "amount": float(item['amount']) if item['amount'] is not None else 0.0,
                "network": item['network_type']
            }
            if label == -1:
                noise_payments.append(pt)
            else:
                if label not in cluster_map:
                    cluster_map[label] = []
                cluster_map[label].append(pt)

        clusters = []
        for cluster_id, pts in cluster_map.items():
            lats = [p['lat'] for p in pts]
            lons = [p['lon'] for p in pts]
            amounts = [p['amount'] for p in pts]
            total_spent = sum(amounts)
            
            center_lat = float(np.mean(lats))
            center_lon = float(np.mean(lons))
            
            d_lat = np.radians(np.array(lats) - center_lat)
            d_lon = np.radians(np.array(lons) - center_lon)
            a = np.sin(d_lat / 2.0)**2 + np.cos(np.radians(center_lat)) * np.cos(np.radians(lats)) * np.sin(d_lon / 2.0)**2
            c = 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
            dists_meters = c * kms_per_radian * 1000.0
            radius_meters = float(np.max(dists_meters)) if len(dists_meters) > 0 else 0.0

            # Vendor breakdown
            vendor_counts = {}
            vendor_totals = {}
            for p in pts:
                v = p['vendor'] or "Unknown"
                vendor_counts[v] = vendor_counts.get(v, 0) + 1
                vendor_totals[v] = vendor_totals.get(v, 0.0) + p['amount']
            
            sorted_vendors = sorted(
                [{"vendor": v, "count": vendor_counts[v], "total": round(vendor_totals[v], 2)} for v in vendor_counts],
                key=lambda x: x['total'],
                reverse=True
            )
            top_vendor = sorted_vendors[0]['vendor'] if sorted_vendors else "Unknown"

            loc_name = reverse_geocode(center_lat, center_lon)
            clusters.append({
                "cluster_id": cluster_id,
                "cluster_num": len(clusters) + 1,
                "name": loc_name,
                "location_name": loc_name,
                "color": palette[cluster_id % len(palette)],
                "payment_count": len(pts),
                "total_amount": round(total_spent, 2),
                "avg_amount": round(total_spent / len(pts), 2),
                "top_vendor": top_vendor,
                "vendors": sorted_vendors,
                "center": {
                    "lat": round(center_lat, 6),
                    "lon": round(center_lon, 6)
                },
                "radius_meters": round(radius_meters, 1),
                "bounds": {
                    "min_lat": min(lats),
                    "max_lat": max(lats),
                    "min_lon": min(lons),
                    "max_lon": max(lons)
                },
                "payments": pts
            })

        # Sort clusters by total spent descending
        clusters.sort(key=lambda c: c['total_amount'], reverse=True)
        for i, c in enumerate(clusters):
            c['cluster_num'] = i + 1

        return {
            "status": "success",
            "eps_meters": eps_meters,
            "min_samples": min_samples,
            "total_payments": len(raw_data),
            "total_clusters": len(clusters),
            "total_amount": round(total_amount_all, 2),
            "clusters": clusters,
            "noise_payments": noise_payments
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}




def decode_csv_content(content: bytes) -> str:
    for enc in ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']:
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    return content.decode('utf-8', errors='replace')


def parse_transaction_datetime(date_str: str, time_str: str = '') -> datetime:
    date_str = (date_str or '').strip()
    time_str = (time_str or '').strip()
    
    date_str = re.sub(r'\bSept\b', 'Sep', date_str, flags=re.IGNORECASE)
    
    # Check if date_str already includes a time component
    if ' ' in date_str or 'T' in date_str:
        sep = 'T' if 'T' in date_str else ' '
        parts = date_str.split(sep, 1)
        d_part = parts[0].strip()
        t_part = parts[1].strip() if len(parts) > 1 else ''
        
        # If no separate time_str given, use the time from date_str
        if not time_str and t_part and t_part not in ['00:00', '00:00:00']:
            time_str = t_part
        # Strip dummy midnight timestamp like '00:00'
        date_str = d_part

    combined = f"{date_str} {time_str}".strip() if time_str else date_str

    formats = [
        '%d-%m-%Y %H:%M:%S',
        '%d-%m-%Y %H:%M',
        '%d-%m-%Y %I:%M %p',
        '%d-%m-%Y %I:%M:%S %p',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d %H:%M',
        '%Y-%m-%d %I:%M %p',
        '%Y-%m-%d %I:%M:%S %p',
        '%b %d, %Y %I:%M %p',
        '%B %d, %Y %I:%M %p',
        '%b %d, %Y %H:%M:%S',
        '%b %d, %Y %H:%M',
        '%d/%m/%Y %H:%M:%S',
        '%d/%m/%Y %H:%M',
        '%d/%m/%Y %I:%M %p',
        '%d/%m/%Y %I:%M:%S %p',
        '%m/%d/%Y %H:%M:%S',
        '%m/%d/%Y %I:%M %p',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%d',
        '%d-%m-%Y',
        '%d/%m/%Y',
        '%b %d, %Y',
        '%B %d, %Y'
    ]
    for fmt in formats:
        try:
            return datetime.strptime(combined, fmt)
        except ValueError:
            continue
            
    try:
        return date_parser.parse(combined)
    except Exception:
        pass
        
    raise ValueError(f"Could not parse date/time: {combined}")


def clean_amount(val_str: str):
    if not val_str:
        return None
    cleaned = re.sub(r'[^\d.-]', '', str(val_str))
    try:
        amt = abs(float(cleaned))
        return amt if amt > 0 else None
    except ValueError:
        return None


def find_header_col_idx(header, exact_names, substring_names, exclude=None):
    exclude = exclude or []
    for target in exact_names:
        for idx, col in enumerate(header):
            if idx not in exclude and col == target:
                return idx
    for sub in substring_names:
        for idx, col in enumerate(header):
            if idx not in exclude and sub in col:
                return idx
    return None


@app.post("/upload_statement")
async def upload_statement(file: UploadFile = File(...), token: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    try:
        verify_access_token(token.credentials)
    except Exception as e:
        return {"status": "error", "message": str(e)}

    try:
        content = await file.read()
        text = decode_csv_content(content)
        reader = csv.reader(io.StringIO(text))
        
        # Skip preamble until header row with 'date'
        header = None
        for row in reader:
            if row and any('date' in str(c).strip().lower() for c in row):
                header = [str(c).strip().lower() for c in row]
                break
        
        if not header:
            return {"status": "error", "message": "Invalid CSV format: could not find header row containing 'Date'."}
        
        date_idx = find_header_col_idx(header, ['date', 'transaction date', 'txn date', 'value date'], ['date'])
        time_idx = find_header_col_idx(header, ['time', 'transaction time', 'txn time'], ['time'], exclude=[date_idx] if date_idx is not None else [])
        type_idx = find_header_col_idx(header, ['transaction type', 'type', 'txn type'], ['type'])
        
        excluded_for_amt = [type_idx] if type_idx is not None else []
        for i, col_name in enumerate(header):
            if 'instrument' in col_name:
                excluded_for_amt.append(i)
                
        amount_idx = find_header_col_idx(
            header,
            ['amount', 'txn amount', 'transaction amount', 'debit amount'],
            ['amount', 'debit', 'withdrawal'],
            exclude=excluded_for_amt
        )
        details_idx = find_header_col_idx(
            header,
            ['transaction details', 'details', 'vendor', 'payee', 'narration', 'description', 'particulars'],
            ['detail', 'vendor', 'payee', 'narration', 'desc', 'particular']
        )
        
        if date_idx is None:
            date_idx = 0
        if amount_idx is None:
            amount_idx = 7 if len(header) > 7 else len(header) - 1
        if details_idx is None:
            details_idx = 2 if len(header) > 2 else 1

        grouped_payments = {}
        min_required_cols = max(date_idx, amount_idx)
        
        for row in reader:
            if not row or len(row) <= min_required_cols:
                continue
            
            # Filter by transaction type if column exists
            if type_idx is not None and len(row) > type_idx:
                t_type = row[type_idx].strip().upper()
                if t_type and 'CREDIT' in t_type and 'DEBIT' not in t_type:
                    continue
            
            date_str = row[date_idx] if len(row) > date_idx else ''
            time_str = row[time_idx] if time_idx is not None and len(row) > time_idx else ''
            details = row[details_idx] if details_idx is not None and len(row) > details_idx else 'Unknown'
            amount_str = row[amount_idx] if len(row) > amount_idx else '0'
            
            amount = clean_amount(amount_str)
            if amount is None or amount == 0:
                continue
            
            try:
                dt = parse_transaction_datetime(date_str, time_str)
            except ValueError as e:
                print(f"Error parsing date {date_str} {time_str}: {e}")
                continue
            
            dt_minute = dt.replace(second=0, microsecond=0)
            
            vendor = details
            for prefix in ["Paid to ", "Transfer to ", "Payment to ", "Sent to ", "Paid by ", "UPI/"]:
                if vendor.lower().startswith(prefix.lower()):
                    vendor = vendor[len(prefix):]
            vendor = vendor.strip()
            if not vendor or vendor == "-":
                vendor = "Unknown"
            
            if dt_minute not in grouped_payments:
                grouped_payments[dt_minute] = {'amount': 0.0, 'vendors': set()}
                
            grouped_payments[dt_minute]['amount'] += amount
            grouped_payments[dt_minute]['vendors'].add(vendor)
            
        unmatched = []
        processed_count = 0

        with pool.connection() as conn:
            with conn.cursor() as cur:
                for dt_minute, data in grouped_payments.items():
                    vendors = list(data['vendors'])
                    vendor_str = vendors[0] if len(vendors) == 1 else "multiple"
                    amount = round(data['amount'], 2)
                    
                    # Find nearest location record within 15 minutes (900 seconds)
                    cur.execute("""
                        SELECT id, timestamp 
                        FROM abradb 
                        WHERE abs(EXTRACT(EPOCH FROM (timestamp - %(dt_minute)s::timestamp))) <= 900
                        ORDER BY 
                            CASE WHEN amount IS NULL THEN 0 ELSE 1 END,
                            abs(EXTRACT(EPOCH FROM (timestamp - %(dt_minute)s::timestamp))) ASC 
                        LIMIT 1
                    """, {'dt_minute': dt_minute})
                    
                    row = cur.fetchone()
                    if row:
                        row_id = row[0]
                        cur.execute("""
                            UPDATE abradb
                            SET amount = %(amount)s, vendor = %(vendor)s
                            WHERE id = %(row_id)s
                        """, {
                            'amount': amount, 
                            'vendor': vendor_str, 
                            'row_id': row_id
                        })
                        processed_count += 1
                    else:
                        unmatched.append({
                            'timestamp': dt_minute.strftime("%b %d, %Y %I:%M %p"),
                            'vendor': vendor_str,
                            'amount': amount
                        })
                conn.commit()

        return {
            "status": "success", 
            "processed_minutes": processed_count,
            "unmatched_payments": unmatched,
            "total_parsed": len(grouped_payments)
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ============================================================================
# FACE RECOGNITION & PERSON CLUSTERING ENDPOINTS
# ============================================================================

@app.get("/people")
async def get_people(token: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    try:
        verify_access_token(token.credentials)
    except Exception as e:
        return {"status": "error", "message": str(e)}
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT p.id, p.name, p.avatar_data, p.created_at, p.updated_at,
                           (
                               SELECT COUNT(*) 
                               FROM abragallery g 
                               WHERE g.person_ids IS NOT NULL 
                                 AND (g.person_ids @> to_jsonb(p.id::text) OR g.person_ids ? (p.id::text))
                           ) as photo_count
                    FROM abra_people p
                    ORDER BY photo_count DESC, p.updated_at DESC
                """)
                rows = cur.fetchall()
                result = []
                for r in rows:
                    result.append({
                        "id": str(r[0]),
                        "name": r[1],
                        "avatar_data": r[2],
                        "created_at": r[3].isoformat() if r[3] else None,
                        "updated_at": r[4].isoformat() if r[4] else None,
                        "photo_count": int(r[5] or 0)
                    })
        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/people/{person_id}")
async def get_person_detail(person_id: str, request: Request, token: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    try:
        verify_access_token(token.credentials)
    except Exception as e:
        return {"status": "error", "message": str(e)}
    try:
        base_url = str(request.base_url).rstrip("/")
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, name, avatar_data, created_at, updated_at FROM abra_people WHERE id = %s", (person_id,))
                person_row = cur.fetchone()
                if not person_row:
                    return {"status": "error", "message": "Person not found"}

                person_info = {
                    "id": str(person_row[0]),
                    "name": person_row[1],
                    "avatar_data": person_row[2],
                    "created_at": person_row[3].isoformat() if person_row[3] else None,
                    "updated_at": person_row[4].isoformat() if person_row[4] else None,
                }

                cur.execute("""
                    SELECT * FROM abragallery 
                    WHERE person_ids IS NOT NULL 
                      AND (person_ids @> to_jsonb(%s::text) OR person_ids ? %s::text)
                    ORDER BY timestamp DESC
                """, (person_id, person_id))
                rows = cur.fetchall()
                columns = [desc[0] for desc in cur.description]
                photos = [dict(zip(columns, row)) for row in rows]

                for p in photos:
                    if p.get("object_key"):
                        okey = p["object_key"]
                        p["cached_url"] = f"{base_url}/media/{okey}"
                        p["thumbnail_url"] = f"{base_url}/media/{okey}?thumb=true"
                        p["url"] = f"{base_url}/media/{okey}"
                        try:
                            p["s3_url"] = s3.generate_presigned_url(
                                ClientMethod='get_object',
                                Params={'Bucket': B2_BUCKET_NAME, 'Key': okey},
                                ExpiresIn=3600
                            )
                        except Exception:
                            p["s3_url"] = None

                person_info["photos"] = photos
                person_info["photo_count"] = len(photos)

        return {"status": "success", "data": person_info}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def merge_duplicate_people_records(conn, similarity_threshold: float = 0.44) -> int:
    """
    1. Finds duplicate people by normalized name and merges them into a single profile.
    2. Finds duplicate/unnamed people by face embedding similarity (cosine similarity >= similarity_threshold)
       and merges them into the primary profile, avoiding duplicate profile cards.
    """
    with conn.cursor() as cur:
        merged_count = 0

        # Step 1: Exact / normalized name matching
        cur.execute("""
            SELECT LOWER(TRIM(name)) as norm_name, COUNT(*) as cnt, array_agg(id::text) as ids
            FROM abra_people
            WHERE name IS NOT NULL AND TRIM(name) != ''
            GROUP BY LOWER(TRIM(name))
            HAVING COUNT(*) > 1
        """)
        dup_groups = cur.fetchall()
        for norm_name, cnt, ids in dup_groups:
            cur.execute("""
                SELECT p.id, p.name, p.avatar_data, p.embeddings,
                       (SELECT COUNT(*) FROM abragallery g WHERE g.person_ids @> to_jsonb(p.id::text) OR g.person_ids ? p.id::text) as photo_count
                FROM abra_people p
                WHERE p.id = ANY(%s::uuid[])
                ORDER BY photo_count DESC, p.created_at ASC
            """, (ids,))
            rows = cur.fetchall()
            if not rows:
                continue
            primary = rows[0]
            primary_id = str(primary[0])
            primary_name = primary[1]
            primary_avatar = primary[2]
            primary_embs = json.loads(primary[3]) if isinstance(primary[3], str) else (primary[3] or [])

            for dup in rows[1:]:
                dup_id = str(dup[0])
                dup_avatar = dup[2]
                dup_embs = json.loads(dup[3]) if isinstance(dup[3], str) else (dup[3] or [])
                for e in dup_embs:
                    if len(primary_embs) < 5 and e:
                        if not any(cosine_similarity(e, ex) > 0.92 for ex in primary_embs):
                            primary_embs.append(e)
                if not primary_avatar and dup_avatar:
                    primary_avatar = dup_avatar

                cur.execute("""
                    UPDATE abragallery
                    SET person_ids = (
                        SELECT COALESCE(jsonb_agg(DISTINCT elem), '[]'::jsonb)
                        FROM (
                            SELECT CASE WHEN elem = %s THEN %s ELSE elem END AS elem
                            FROM jsonb_array_elements_text(person_ids) AS elem
                        ) s
                    )
                    WHERE person_ids IS NOT NULL 
                      AND (person_ids @> to_jsonb(%s::text) OR person_ids ? %s::text)
                """, (dup_id, primary_id, dup_id, dup_id))

                cur.execute("UPDATE abra_face_suggestions SET person_id = %s WHERE person_id = %s", (primary_id, dup_id))
                cur.execute("DELETE FROM abra_people WHERE id = %s", (dup_id,))
                merged_count += 1

            cur.execute("""
                UPDATE abra_people
                SET name = %s, avatar_data = %s, embeddings = %s, updated_at = NOW()
                WHERE id = %s
            """, (primary_name, primary_avatar, json.dumps(primary_embs), primary_id))

        # Step 2: Embedding-based similarity deduplication
        cur.execute("""
            SELECT p.id, p.name, p.avatar_data, p.embeddings,
                   (SELECT COUNT(*) FROM abragallery g WHERE g.person_ids @> to_jsonb(p.id::text) OR g.person_ids ? p.id::text) as photo_count
            FROM abra_people p
            ORDER BY (p.name IS NOT NULL AND TRIM(p.name) != '') DESC, photo_count DESC, p.created_at ASC
        """)
        all_rows = cur.fetchall()
        people_data = []
        for r in all_rows:
            raw_embs = json.loads(r[3]) if isinstance(r[3], str) else (r[3] or [])
            people_data.append({
                "id": str(r[0]),
                "name": r[1],
                "avatar": r[2],
                "embs": [e for e in raw_embs if e],
                "photo_count": r[4]
            })

        merged_ids = set()
        for i in range(len(people_data)):
            p_primary = people_data[i]
            if p_primary["id"] in merged_ids or not p_primary["embs"]:
                continue

            for j in range(i + 1, len(people_data)):
                p_dup = people_data[j]
                if p_dup["id"] in merged_ids or not p_dup["embs"]:
                    continue

                # Safety: Don't merge two different named individuals
                if p_primary["name"] and p_dup["name"] and p_primary["name"].strip().lower() != p_dup["name"].strip().lower():
                    continue

                max_sim = -1.0
                for e1 in p_primary["embs"]:
                    for e2 in p_dup["embs"]:
                        sim = cosine_similarity(e1, e2)
                        if sim > max_sim:
                            max_sim = sim

                if max_sim >= similarity_threshold:
                    dup_id = p_dup["id"]
                    primary_id = p_primary["id"]
                    merged_ids.add(dup_id)

                    for e in p_dup["embs"]:
                        if len(p_primary["embs"]) < 5 and not any(cosine_similarity(e, ex) > 0.92 for ex in p_primary["embs"]):
                            p_primary["embs"].append(e)

                    if not p_primary["avatar"] and p_dup["avatar"]:
                        p_primary["avatar"] = p_dup["avatar"]

                    if not p_primary["name"] and p_dup["name"]:
                        p_primary["name"] = p_dup["name"]

                    cur.execute("""
                        UPDATE abragallery
                        SET person_ids = (
                            SELECT COALESCE(jsonb_agg(DISTINCT elem), '[]'::jsonb)
                            FROM (
                                SELECT CASE WHEN elem = %s THEN %s ELSE elem END AS elem
                                FROM jsonb_array_elements_text(person_ids) AS elem
                            ) s
                        )
                        WHERE person_ids IS NOT NULL 
                          AND (person_ids @> to_jsonb(%s::text) OR person_ids ? %s::text)
                    """, (dup_id, primary_id, dup_id, dup_id))

                    cur.execute("UPDATE abra_face_suggestions SET person_id = %s WHERE person_id = %s", (primary_id, dup_id))
                    cur.execute("DELETE FROM abra_people WHERE id = %s", (dup_id,))
                    merged_count += 1

            cur.execute("""
                UPDATE abra_people
                SET name = %s, avatar_data = %s, embeddings = %s, updated_at = NOW()
                WHERE id = %s
            """, (p_primary["name"], p_primary["avatar"], json.dumps(p_primary["embs"]), p_primary["id"]))

        conn.commit()
        return merged_count

@app.post("/people/merge_duplicates")
async def merge_duplicate_people_endpoint(
    similarity_threshold: float = Query(0.44),
    token: HTTPAuthorizationCredentials = Depends(HTTPBearer())
):
    try:
        verify_access_token(token.credentials)
    except Exception as e:
        return {"status": "error", "message": str(e)}
    try:
        with pool.connection() as conn:
            merged = merge_duplicate_people_records(conn, similarity_threshold=similarity_threshold)
        return {"status": "success", "merged_count": merged, "message": f"Successfully merged {merged} duplicate profiles."}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.patch("/people/{person_id}")
async def update_person(person_id: str, data: PersonUpdateModel, token: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    try:
        verify_access_token(token.credentials)
    except Exception as e:
        return {"status": "error", "message": str(e)}
    try:
        clean_name = data.name.strip() if data.name and data.name.strip() else None
        with pool.connection() as conn:
            with conn.cursor() as cur:
                # Check if another person already exists with the same name (case-insensitive)
                if clean_name:
                    cur.execute("""
                        SELECT id, avatar_data, embeddings FROM abra_people 
                        WHERE LOWER(TRIM(name)) = LOWER(%s) AND id != %s
                        LIMIT 1
                    """, (clean_name, person_id))
                    existing = cur.fetchone()
                    if existing:
                        target_id = str(existing[0])
                        # Merge person_id into target_id
                        cur.execute("""
                            UPDATE abragallery
                            SET person_ids = (
                                SELECT jsonb_agg(DISTINCT elem)
                                FROM (
                                    SELECT CASE WHEN elem = %s THEN %s ELSE elem END AS elem
                                    FROM jsonb_array_elements_text(person_ids) AS elem
                                ) s
                            )
                            WHERE person_ids IS NOT NULL 
                              AND (person_ids @> to_jsonb(%s::text) OR person_ids ? %s::text)
                        """, (person_id, target_id, person_id, person_id))
                        cur.execute("UPDATE abra_face_suggestions SET person_id = %s WHERE person_id = %s", (target_id, person_id))
                        cur.execute("DELETE FROM abra_people WHERE id = %s", (person_id,))
                        conn.commit()
                        return {"status": "success", "name": clean_name, "merged": True, "target_id": target_id}

                cur.execute("""
                    UPDATE abra_people
                    SET name = %s, updated_at = NOW()
                    WHERE id = %s
                """, (clean_name, person_id))
                conn.commit()
        return {"status": "success", "name": clean_name}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.delete("/people/{person_id}")
async def delete_person(person_id: str, token: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    try:
        verify_access_token(token.credentials)
    except Exception as e:
        return {"status": "error", "message": str(e)}
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM abra_people WHERE id = %s", (person_id,))
                cur.execute("""
                    UPDATE abragallery
                    SET person_ids = (
                        SELECT COALESCE(jsonb_agg(elem), '[]'::jsonb)
                        FROM jsonb_array_elements_text(person_ids) AS elem
                        WHERE elem != %s
                    )
                    WHERE person_ids IS NOT NULL 
                      AND (person_ids @> to_jsonb(%s::text) OR person_ids ? %s::text)
                """, (person_id, person_id, person_id))
                conn.commit()
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/people/suggestions")
async def get_face_suggestions(request: Request, token: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    """Returns all pending match suggestions where similarity was close to ~40% for user confirmation."""
    try:
        verify_access_token(token.credentials)
    except Exception as e:
        return {"status": "error", "message": str(e)}
    try:
        base_url = str(request.base_url).rstrip("/")
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        s.id, s.photo_id, s.person_id, s.similarity, s.avatar_data, 
                        s.created_at, p.name, p.avatar_data,
                        g.object_key, g.url, g.timestamp
                    FROM abra_face_suggestions s
                    LEFT JOIN abra_people p ON s.person_id = p.id
                    LEFT JOIN abragallery g ON s.photo_id = g.id
                    WHERE s.status = 'pending'
                    ORDER BY s.created_at DESC
                """)
                rows = cur.fetchall()
                suggestions = []
                for r in rows:
                    sugg_id, photo_id, person_id, sim, detected_avatar, created_at, p_name, p_avatar, obj_key, raw_url, photo_ts = r
                    
                    full_photo_url = f"{base_url}/media/{obj_key}" if obj_key else raw_url

                    suggestions.append({
                        "id": str(sugg_id),
                        "photo_id": photo_id,
                        "person_id": str(person_id),
                        "similarity": round(float(sim), 3),
                        "similarity_percent": int(round(float(sim) * 100)),
                        "detected_face_avatar": detected_avatar,
                        "person_name": p_name or "Unknown Person",
                        "person_avatar": p_avatar,
                        "photo_url": full_photo_url,
                        "photo_timestamp": photo_ts.isoformat() if photo_ts else None,
                        "created_at": created_at.isoformat() if created_at else None
                    })
                return {"status": "success", "data": suggestions}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/people/suggestions/{suggestion_id}/resolve")
async def resolve_face_suggestion(
    suggestion_id: str,
    body: ResolveSuggestionModel,
    token: HTTPAuthorizationCredentials = Depends(HTTPBearer())
):
    """User confirms or rejects a borderline match."""
    try:
        verify_access_token(token.credentials)
    except Exception as e:
        return {"status": "error", "message": str(e)}
    try:
        action = body.action.lower().strip() # 'accept', 'reject', 'create_new'
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT photo_id, person_id, avatar_data, embedding, similarity FROM abra_face_suggestions WHERE id = %s",
                    (suggestion_id,)
                )
                sugg = cur.fetchone()
                if not sugg:
                    return {"status": "error", "message": "Suggestion not found"}
                
                photo_id, person_id, avatar_data, emb_raw, sim = sugg
                emb = emb_raw
                if isinstance(emb, str):
                    try:
                        emb = json.loads(emb)
                    except:
                        emb = []

                if action == "accept":
                    # 1. Link person_id into abragallery
                    cur.execute("SELECT person_ids FROM abragallery WHERE id = %s", (photo_id,))
                    p_row = cur.fetchone()
                    existing_pids = []
                    if p_row and p_row[0]:
                        existing_pids = p_row[0] if isinstance(p_row[0], list) else json.loads(p_row[0])
                    
                    person_id_str = str(person_id)
                    if person_id_str not in existing_pids:
                        existing_pids.append(person_id_str)
                        cur.execute(
                            "UPDATE abragallery SET person_ids = %s WHERE id = %s",
                            (json.dumps(existing_pids), photo_id)
                        )

                    # 2. Optionally store embedding in abra_people if < 3 embeddings
                    if emb:
                        cur.execute("SELECT embeddings FROM abra_people WHERE id = %s", (person_id,))
                        person_embs_row = cur.fetchone()
                        if person_embs_row:
                            p_embs = person_embs_row[0] or []
                            if isinstance(p_embs, str):
                                try:
                                    p_embs = json.loads(p_embs)
                                except:
                                    p_embs = []
                            if len(p_embs) < 3:
                                p_embs.append(emb)
                                cur.execute(
                                    "UPDATE abra_people SET embeddings = %s, updated_at = NOW() WHERE id = %s",
                                    (json.dumps(p_embs), person_id)
                                )

                    # 3. Mark or delete suggestion
                    cur.execute("DELETE FROM abra_face_suggestions WHERE id = %s", (suggestion_id,))
                    conn.commit()
                    return {"status": "success", "action": "accepted", "message": "Linked person to photo"}

                elif action == "reject":
                    cur.execute("DELETE FROM abra_face_suggestions WHERE id = %s", (suggestion_id,))
                    conn.commit()
                    return {"status": "success", "action": "rejected", "message": "Rejected match suggestion"}

                elif action == "create_new":
                    new_person_id = str(uuid.uuid4())
                    new_embs = [emb] if emb else []
                    new_name = body.name or None
                    cur.execute(
                        """
                        INSERT INTO abra_people (id, name, avatar_data, embeddings, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, NOW(), NOW())
                        """,
                        (new_person_id, new_name, avatar_data, json.dumps(new_embs))
                    )
                    # Link to photo
                    cur.execute("SELECT person_ids FROM abragallery WHERE id = %s", (photo_id,))
                    p_row = cur.fetchone()
                    existing_pids = []
                    if p_row and p_row[0]:
                        existing_pids = p_row[0] if isinstance(p_row[0], list) else json.loads(p_row[0])
                    if new_person_id not in existing_pids:
                        existing_pids.append(new_person_id)
                        cur.execute(
                            "UPDATE abragallery SET person_ids = %s WHERE id = %s",
                            (json.dumps(existing_pids), photo_id)
                        )
                    cur.execute("DELETE FROM abra_face_suggestions WHERE id = %s", (suggestion_id,))
                    conn.commit()
                    return {"status": "success", "action": "created_new", "person_id": new_person_id}

                else:
                    return {"status": "error", "message": "Invalid action. Use 'accept', 'reject', or 'create_new'."}

    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/people/scan_stream")
async def scan_gallery_faces_stream(
    token: str = Query(...),
    similarity_threshold: float = Query(0.44),
    review_threshold: float = Query(0.32),
    reindex_all: bool = Query(False)
):
    """Server-Sent Events (SSE) stream providing real-time photo-by-photo scanning progress."""
    try:
        verify_access_token(token)
    except Exception as e:
        async def err_gen():
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        return StreamingResponse(err_gen(), media_type="text/event-stream")

    def event_stream():
        try:
            with pool.connection() as conn:
                with conn.cursor() as cur:
                    if reindex_all:
                        cur.execute("DELETE FROM abra_people WHERE name IS NULL OR TRIM(name) = ''")
                        cur.execute("UPDATE abra_people SET embeddings = '[]'::jsonb")
                        cur.execute("DELETE FROM abra_face_suggestions")
                        cur.execute("UPDATE abragallery SET person_ids = '[]'::jsonb")
                        conn.commit()
                        yield f"data: {json.dumps({'type': 'status', 'message': 'Reset previous face indexes (preserving named profiles)...'})}\n\n"

                    cur.execute("SELECT id, name, avatar_data, embeddings FROM abra_people")
                    people_rows = cur.fetchall()
                    people_list = []
                    for r in people_rows:
                        emb = r[3]
                        if isinstance(emb, str):
                            try:
                                emb = json.loads(emb)
                            except:
                                emb = []
                        people_list.append({
                            "id": str(r[0]),
                            "name": r[1],
                            "avatar_data": r[2],
                            "embeddings": emb or []
                        })

                    if reindex_all:
                        cur.execute("SELECT id, object_key, url, timestamp FROM abragallery ORDER BY timestamp DESC")
                    else:
                        cur.execute("SELECT id, object_key, url, timestamp FROM abragallery WHERE person_ids IS NULL OR person_ids = '[]'::jsonb ORDER BY timestamp DESC")
                    
                    photos_to_process = cur.fetchall()
                    total_photos = len(photos_to_process)
                    
                    yield f"data: {json.dumps({'type': 'start', 'total_photos': total_photos, 'people_count': len(people_list), 'message': f'Found {total_photos} photos to scan'})}\n\n"

                    processed_count = 0
                    total_faces_found = 0
                    total_suggestions = 0

                    for idx, photo in enumerate(photos_to_process):
                        photo_id, obj_key, raw_url, photo_ts = photo[0], photo[1], photo[2], photo[3]
                        
                        yield f"data: {json.dumps({'type': 'progress', 'index': idx + 1, 'total': total_photos, 'photo_id': photo_id, 'message': f'Scanning photo {idx + 1} of {total_photos}...'})}\n\n"

                        image_bytes = None
                        if obj_key:
                            res = get_or_fetch_image_bytes(obj_key, s3, B2_BUCKET_NAME)
                            if res:
                                image_bytes, _ = res

                        if not image_bytes and raw_url and str(raw_url).startswith("http"):
                            try:
                                req = urllib.request.Request(raw_url, headers={'User-Agent': 'ABRA/1.0'})
                                with urllib.request.urlopen(req, timeout=5.0) as resp:
                                    image_bytes = resp.read()
                            except Exception as url_err:
                                print(f"[FaceProcess] URL get error for {raw_url}: {url_err}")

                        if not image_bytes:
                            continue

                        faces = extract_faces_from_image(image_bytes)
                        total_faces_found += len(faces)
                        photo_person_ids = []
                        photo_auto_matches = 0
                        photo_reviews = 0

                        for face_data in faces:
                            emb = face_data["embedding"]
                            avatar_data = face_data["avatar_data"]
                            
                            status, candidate_id, sim = classify_face_match(
                                emb, people_list, auto_threshold=similarity_threshold, review_threshold=review_threshold
                            )
                            
                            if status == "auto_match" and candidate_id:
                                photo_auto_matches += 1
                                if candidate_id not in photo_person_ids:
                                    photo_person_ids.append(candidate_id)
                                person_obj = next((p for p in people_list if p["id"] == candidate_id), None)
                                if person_obj and len(person_obj["embeddings"]) < 5 and sim < 0.90:
                                    person_obj["embeddings"].append(emb)
                                    cur.execute(
                                        "UPDATE abra_people SET embeddings = %s, updated_at = NOW() WHERE id = %s",
                                        (json.dumps(person_obj["embeddings"]), candidate_id)
                                    )
                            elif status == "needs_review" and candidate_id:
                                photo_reviews += 1
                                total_suggestions += 1
                                # Save pending suggestion for user review
                                cur.execute(
                                    """
                                    INSERT INTO abra_face_suggestions (photo_id, person_id, similarity, avatar_data, embedding, status, created_at)
                                    VALUES (%s, %s, %s, %s, %s, 'pending', NOW())
                                    """,
                                    (photo_id, candidate_id, sim, avatar_data, json.dumps(emb))
                                )
                            else:
                                # New distinct person (< review_threshold)
                                new_id = str(uuid.uuid4())
                                new_embeddings = [emb]
                                cur.execute(
                                    """
                                    INSERT INTO abra_people (id, name, avatar_data, embeddings, created_at, updated_at)
                                    VALUES (%s, %s, %s, %s, NOW(), NOW())
                                    """,
                                    (new_id, None, avatar_data, json.dumps(new_embeddings))
                                )
                                new_person = {
                                    "id": new_id,
                                    "name": None,
                                    "avatar_data": avatar_data,
                                    "embeddings": new_embeddings
                                }
                                people_list.append(new_person)
                                if new_id not in photo_person_ids:
                                    photo_person_ids.append(new_id)

                        cur.execute(
                            "UPDATE abragallery SET person_ids = %s WHERE id = %s",
                            (json.dumps(photo_person_ids), photo_id)
                        )
                        processed_count += 1
                        conn.commit()

                        del image_bytes
                        del faces
                        if (idx + 1) % 5 == 0:
                            gc.collect()

                        yield f"data: {json.dumps({'type': 'photo_done', 'index': idx + 1, 'total': total_photos, 'photo_id': photo_id, 'faces_found': len(photo_person_ids), 'auto_matches': photo_auto_matches, 'needs_review': photo_reviews, 'message': f'Photo {idx + 1}/{total_photos}: {len(photo_person_ids)} faces ({photo_auto_matches} matched, {photo_reviews} for review)'})}\n\n"

                    # Automatically merge any duplicate people created
                    merge_duplicate_people_records(conn, similarity_threshold=similarity_threshold)

                    yield f"data: {json.dumps({'type': 'complete', 'processed_photos': processed_count, 'total_faces_found': total_faces_found, 'total_people': len(people_list), 'total_suggestions': total_suggestions, 'message': f'Scan complete! Analyzed {processed_count} photos, identified {len(people_list)} people.'})}\n\n"

        except Exception as e:
            print(f"[FaceStream Error]: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

@app.post("/people/process_gallery")
async def process_gallery_faces(
    body: ProcessGalleryModel = ProcessGalleryModel(),
    token: HTTPAuthorizationCredentials = Depends(HTTPBearer())
):
    try:
        verify_access_token(token.credentials)
    except Exception as e:
        return {"status": "error", "message": str(e)}
    try:
        threshold = float(body.similarity_threshold if body.similarity_threshold is not None else 0.44)
        review_threshold = float(body.review_threshold if body.review_threshold is not None else 0.32)
        reindex_all = bool(body.reindex_all)

        with pool.connection() as conn:
            with conn.cursor() as cur:
                if reindex_all:
                    cur.execute("DELETE FROM abra_people WHERE name IS NULL OR TRIM(name) = ''")
                    cur.execute("UPDATE abra_people SET embeddings = '[]'::jsonb")
                    cur.execute("DELETE FROM abra_face_suggestions")
                    cur.execute("UPDATE abragallery SET person_ids = '[]'::jsonb")
                    conn.commit()

                cur.execute("SELECT id, name, avatar_data, embeddings FROM abra_people")
                people_rows = cur.fetchall()
                people_list = []
                for r in people_rows:
                    emb = r[3]
                    if isinstance(emb, str):
                        try:
                            emb = json.loads(emb)
                        except:
                            emb = []
                    people_list.append({
                        "id": str(r[0]),
                        "name": r[1],
                        "avatar_data": r[2],
                        "embeddings": emb or []
                    })

                if reindex_all:
                    cur.execute("SELECT id, object_key, url FROM abragallery ORDER BY timestamp DESC")
                else:
                    cur.execute("SELECT id, object_key, url FROM abragallery WHERE person_ids IS NULL OR person_ids = '[]'::jsonb ORDER BY timestamp DESC")
                
                photos_to_process = cur.fetchall()
                processed_count = 0
                total_faces_found = 0
                total_suggestions = 0

                for photo in photos_to_process:
                    photo_id, obj_key, raw_url = photo[0], photo[1], photo[2]
                    image_bytes = None
                    if obj_key:
                        res = get_or_fetch_image_bytes(obj_key, s3, B2_BUCKET_NAME)
                        if res:
                            image_bytes, _ = res

                    if not image_bytes and raw_url and str(raw_url).startswith("http"):
                        try:
                            req = urllib.request.Request(raw_url, headers={'User-Agent': 'ABRA/1.0'})
                            with urllib.request.urlopen(req, timeout=5.0) as resp:
                                image_bytes = resp.read()
                        except Exception as url_err:
                            print(f"[FaceProcess] URL get error for {raw_url}: {url_err}")

                    if not image_bytes:
                        continue

                    faces = extract_faces_from_image(image_bytes)
                    total_faces_found += len(faces)
                    photo_person_ids = []

                    for face_data in faces:
                        emb = face_data["embedding"]
                        avatar_data = face_data["avatar_data"]
                        
                        status, candidate_id, sim = classify_face_match(
                            emb, people_list, auto_threshold=threshold, review_threshold=review_threshold
                        )
                        
                        if status == "auto_match" and candidate_id:
                            if candidate_id not in photo_person_ids:
                                photo_person_ids.append(candidate_id)
                            person_obj = next((p for p in people_list if p["id"] == candidate_id), None)
                            if person_obj and len(person_obj["embeddings"]) < 5 and sim < 0.90:
                                person_obj["embeddings"].append(emb)
                                cur.execute(
                                    "UPDATE abra_people SET embeddings = %s, updated_at = NOW() WHERE id = %s",
                                    (json.dumps(person_obj["embeddings"]), candidate_id)
                                )
                        elif status == "needs_review" and candidate_id:
                            total_suggestions += 1
                            cur.execute(
                                """
                                INSERT INTO abra_face_suggestions (photo_id, person_id, similarity, avatar_data, embedding, status, created_at)
                                VALUES (%s, %s, %s, %s, %s, 'pending', NOW())
                                """,
                                (photo_id, candidate_id, sim, avatar_data, json.dumps(emb))
                            )
                        else:
                            new_id = str(uuid.uuid4())
                            new_embeddings = [emb]
                            cur.execute(
                                """
                                INSERT INTO abra_people (id, name, avatar_data, embeddings, created_at, updated_at)
                                VALUES (%s, %s, %s, %s, NOW(), NOW())
                                """,
                                (new_id, None, avatar_data, json.dumps(new_embeddings))
                            )
                            new_person = {
                                "id": new_id,
                                "name": None,
                                "avatar_data": avatar_data,
                                "embeddings": new_embeddings
                            }
                            people_list.append(new_person)
                            if new_id not in photo_person_ids:
                                photo_person_ids.append(new_id)

                    cur.execute(
                        "UPDATE abragallery SET person_ids = %s WHERE id = %s",
                        (json.dumps(photo_person_ids), photo_id)
                    )
                    processed_count += 1
                    del image_bytes
                    del faces
                    if processed_count % 5 == 0:
                        gc.collect()

                merge_duplicate_people_records(conn, similarity_threshold=threshold)
                conn.commit()

        return {
            "status": "success",
            "processed_photos": processed_count,
            "total_faces_found": total_faces_found,
            "total_people": len(people_list),
            "pending_suggestions": total_suggestions
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ====================================================
# Real-Time TomTom Traffic API Endpoints & Stats
# ====================================================
_traffic_cache = {
    "flow": {},
    "incidents": {}
}

@app.get("/api/traffic/config")
async def get_traffic_config():
    api_key = os.getenv("TOMTOM_API_KEY", "")
    return {
        "status": "success",
        "configured": bool(api_key),
        "api_key": api_key,
        "provider": "TomTom Traffic API",
        "default_flow_style": "relative",
        "default_incident_style": "s0"
    }

@app.get("/api/traffic/flow-segment")
async def get_traffic_flow_segment(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    zoom: int = Query(10, ge=0, le=22),
    style: str = Query("relative-delay"),
    unit: str = Query("KMPH")
):
    api_key = os.getenv("TOMTOM_API_KEY", "")
    if not api_key:
        return {"status": "error", "message": "TOMTOM_API_KEY not configured"}

    cache_key = f"{round(lat, 4)}_{round(lon, 4)}_{style}_{zoom}_{unit}"
    now_ts = datetime.now(timezone.utc).timestamp()
    cached = _traffic_cache["flow"].get(cache_key)
    if cached and (now_ts - cached["timestamp"] < 30):
        return cached["data"]

    try:
        url = f"https://api.tomtom.com/traffic/services/4/flowSegmentData/{style}/{zoom}/json?key={api_key}&point={lat},{lon}&unit={unit}"
        req = urllib.request.Request(url, headers={"User-Agent": "ABRA-Traffic-Service/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        raw = data.get("flowSegmentData", {})
        current_speed = float(raw.get("currentSpeed", 0))
        free_flow_speed = float(raw.get("freeFlowSpeed", 0))
        current_travel_time = float(raw.get("currentTravelTime", 0))
        free_flow_travel_time = float(raw.get("freeFlowTravelTime", 0))
        delay_seconds = max(0.0, current_travel_time - free_flow_travel_time)

        ratio = (current_speed / free_flow_speed) if free_flow_speed > 0 else 1.0
        congestion_level = "fluid"
        if raw.get("roadClosure"):
            congestion_level = "closed"
        elif ratio < 0.35:
            congestion_level = "jam"
        elif ratio < 0.65:
            congestion_level = "heavy"
        elif ratio < 0.85:
            congestion_level = "moderate"

        coords = []
        raw_coords = raw.get("coordinates", {}).get("coordinate", [])
        if isinstance(raw_coords, list):
            coords = [[c.get("longitude"), c.get("latitude")] for c in raw_coords if "longitude" in c and "latitude" in c]

        result = {
            "status": "success",
            "current_speed": current_speed,
            "free_flow_speed": free_flow_speed,
            "unit": unit,
            "current_travel_time": current_travel_time,
            "free_flow_travel_time": free_flow_travel_time,
            "delay_seconds": delay_seconds,
            "confidence": round(float(raw.get("confidence", 0)) * 100, 1),
            "road_closure": bool(raw.get("roadClosure", False)),
            "congestion_level": congestion_level,
            "coordinates": coords,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        _traffic_cache["flow"][cache_key] = {"timestamp": now_ts, "data": result}
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/traffic/incidents")
async def get_traffic_incidents(
    min_lon: float = Query(...),
    min_lat: float = Query(...),
    max_lon: float = Query(...),
    max_lat: float = Query(...),
    language: str = Query("en-GB")
):
    api_key = os.getenv("TOMTOM_API_KEY", "")
    if not api_key:
        return {"status": "error", "message": "TOMTOM_API_KEY not configured"}

    cache_key = f"{round(min_lon, 3)}_{round(min_lat, 3)}_{round(max_lon, 3)}_{round(max_lat, 3)}"
    now_ts = datetime.now(timezone.utc).timestamp()
    cached = _traffic_cache["incidents"].get(cache_key)
    if cached and (now_ts - cached["timestamp"] < 30):
        return cached["data"]

    try:
        fields = "{incidents{type,geometry{type,coordinates},properties{id,iconCategory,magnitudeOfDelay,events{description,code},startTime,endTime,from,to,length,delay,roadNumbers,probabilityOfOccurrence,timeValidity}}}"
        encoded_fields = urllib.parse.quote(fields)
        url = f"https://api.tomtom.com/traffic/services/5/incidentDetails?key={api_key}&bbox={min_lon},{min_lat},{max_lon},{max_lat}&language={language}&fields={encoded_fields}"

        req = urllib.request.Request(url, headers={"User-Agent": "ABRA-Traffic-Service/1.0"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        incidents = data.get("incidents", [])
        result = {
            "status": "success",
            "count": len(incidents),
            "incidents": incidents,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        _traffic_cache["incidents"][cache_key] = {"timestamp": now_ts, "data": result}
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/traffic/stats")
async def get_traffic_stats(
    lat: float = Query(..., description="Center latitude"),
    lon: float = Query(..., description="Center longitude"),
    radius_km: float = Query(8.0, ge=0.5, le=50.0)
):
    api_key = os.getenv("TOMTOM_API_KEY", "")
    if not api_key:
        return {"status": "error", "message": "TOMTOM_API_KEY not configured"}

    delta_deg = radius_km / 111.0
    min_lon = lon - delta_deg
    max_lon = lon + delta_deg
    min_lat = lat - (delta_deg / 1.1)
    max_lat = lat + (delta_deg / 1.1)

    try:
        fields = "{incidents{type,geometry{type,coordinates},properties{id,iconCategory,magnitudeOfDelay,events{description,code},startTime,endTime,from,to,length,delay,roadNumbers}}}"
        encoded_fields = urllib.parse.quote(fields)
        url = f"https://api.tomtom.com/traffic/services/5/incidentDetails?key={api_key}&bbox={min_lon},{min_lat},{max_lon},{max_lat}&language=en-GB&fields={encoded_fields}"
        req = urllib.request.Request(url, headers={"User-Agent": "ABRA-Traffic-Service/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            incidents_data = json.loads(resp.read().decode("utf-8"))

        incidents = incidents_data.get("incidents", [])
        total_delay_secs = sum(float(inc.get("properties", {}).get("delay", 0) or 0) for inc in incidents)
        jams = sum(1 for inc in incidents if inc.get("properties", {}).get("iconCategory") == 6)
        accidents = sum(1 for inc in incidents if inc.get("properties", {}).get("iconCategory") == 1)
        roadworks = sum(1 for inc in incidents if inc.get("properties", {}).get("iconCategory") == 9)
        closures = sum(1 for inc in incidents if inc.get("properties", {}).get("iconCategory") in (7, 8))
        major_delays = sum(1 for inc in incidents if (inc.get("properties", {}).get("magnitudeOfDelay") or 0) >= 3)

        return {
            "status": "success",
            "center": {"lat": lat, "lon": lon},
            "radius_km": radius_km,
            "total_incidents": len(incidents),
            "jams": jams,
            "accidents": accidents,
            "roadworks": roadworks,
            "closures": closures,
            "major_delays": major_delays,
            "total_delay_seconds": total_delay_secs,
            "total_delay_minutes": round(total_delay_secs / 60.0, 1),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ====================================================
# TomTom Places Search API (Next-Gen Orbis Places API)
# ====================================================
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import math

class PlacesSuggestRequest(BaseModel):
    query: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    origin: Optional[Dict[str, Any]] = None
    maxResults: Optional[int] = 10
    filters: Optional[Dict[str, Any]] = None
    preferences: Optional[Dict[str, Any]] = None

class PlacesDiscoverRequest(BaseModel):
    query: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    origin: Optional[Dict[str, Any]] = None
    radius: Optional[int] = None
    maxResults: Optional[int] = 30
    filters: Optional[Dict[str, Any]] = None
    preferences: Optional[Dict[str, Any]] = None
    category: Optional[str] = None
    category_set: Optional[str] = None

_places_cache = {
    "suggest": {},
    "discover": {},
    "details": {},
    "nearby": {},
    "search": {},
    "category": {},
    "geocode": {}
}

def normalize_orbis_place(item: dict, center_lat: Optional[float] = None, center_lon: Optional[float] = None) -> dict:
    item_id = item.get("id") or item.get("entityId") or ""
    title = item.get("title") or item.get("poi", {}).get("name") or "Place"
    
    # Coordinates: Orbis returns [lon, lat] in GeoJSON format
    coords = item.get("position", {}).get("coordinates")
    if coords and isinstance(coords, list) and len(coords) >= 2:
        lon, lat = float(coords[0]), float(coords[1])
    else:
        lat = item.get("position", {}).get("lat")
        lon = item.get("position", {}).get("lon")
    
    # Distance in meters
    dist = item.get("distanceInMeters") or item.get("dist")
    if dist is None and center_lat is not None and center_lon is not None and lat is not None and lon is not None:
        dlat = math.radians(lat - center_lat)
        dlon = math.radians(lon - center_lon)
        a = math.sin(dlat / 2)**2 + math.cos(math.radians(center_lat)) * math.cos(math.radians(lat)) * math.sin(dlon / 2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        dist = round(6371000 * c, 1)

    # Categories
    categories = []
    poi_types = item.get("poiTypes", [])
    if isinstance(poi_types, list):
        for pt in poi_types:
            name = pt.get("name") or pt.get("id")
            if name:
                categories.append(name)
    if not categories and "poi" in item and "categories" in item["poi"]:
        categories = item["poi"]["categories"]
    if not categories:
        categories = ["POI"]

    # Address
    raw_addr = item.get("address", {})
    parts = [
        raw_addr.get("houseNumber"),
        raw_addr.get("street"),
        raw_addr.get("neighborhood"),
        raw_addr.get("municipality"),
        raw_addr.get("countrySubdivision"),
        raw_addr.get("country")
    ]
    addr_str = ", ".join([p for p in parts if p]) or raw_addr.get("freeformAddress") or ", ".join(item.get("subtitles", [])) or "Address unavailable"

    # Contacts
    phone = None
    url = None
    contacts = item.get("contacts", [])
    if isinstance(contacts, list):
        for c in contacts:
            if not phone and c.get("phones"):
                phone = c["phones"][0] if isinstance(c["phones"], list) else str(c["phones"])
            if not url and c.get("websites"):
                url = c["websites"][0] if isinstance(c["websites"], list) else str(c["websites"])
    if not phone and "poi" in item:
        phone = item["poi"].get("phone")
    if not url and "poi" in item:
        url = item["poi"].get("url")

    # Path parameters for details
    more = item.get("more", {})
    path_params = {}
    if "pathParameters" in more:
        for p in more["pathParameters"]:
            path_params[p.get("parameter")] = p.get("argument")

    detail_type = path_params.get("type") or ("pois" if item.get("type") == "poi" else "areas")
    detail_id = path_params.get("id") or item_id

    return {
        "id": item_id,
        "title": title,
        "type": item.get("type", "poi"),
        "dist": dist,
        "distanceInMeters": dist,
        "position": {
            "lat": lat,
            "lon": lon
        },
        "address": {
            "freeformAddress": addr_str,
            "municipality": raw_addr.get("municipality", ""),
            "country": raw_addr.get("country", ""),
            "raw": raw_addr
        },
        "poi": {
            "name": title,
            "categories": categories,
            "phone": phone,
            "url": url,
            "brands": item.get("poiBrands") or (item.get("poi", {}).get("brands"))
        },
        "contacts": contacts,
        "poiTypes": poi_types,
        "more": more,
        "detailType": detail_type,
        "detailId": detail_id,
        "raw": item
    }

# -----------------------------------------------------------------
# 1. POST /places/suggest - Suggest a location (Autocomplete)
# -----------------------------------------------------------------
@app.post("/places/suggest")
@app.post("/api/places/suggest")
async def suggest_places(req: PlacesSuggestRequest):
    api_key = os.getenv("TOMTOM_API_KEY", "") or "YCWqMdqB0kPi0mLxLNN7WXMabGcCnQSd"
    if not api_key:
        return {"status": "error", "message": "TOMTOM_API_KEY not configured"}

    q = req.query.strip()
    if not q:
        return {"status": "success", "results": []}

    cache_key = f"{q.lower()}_{round(req.lat or 0, 3)}_{round(req.lon or 0, 3)}_{req.maxResults}"
    now_ts = datetime.now(timezone.utc).timestamp()
    cached = _places_cache["suggest"].get(cache_key)
    if cached and (now_ts - cached["timestamp"] < 60):
        return cached["data"]

    # Build Orbis suggest body
    body: Dict[str, Any] = {
        "query": q,
        "maxResults": min(max(req.maxResults or 10, 1), 20)
    }

    if req.origin:
        body["origin"] = req.origin
    elif req.lat is not None and req.lon is not None:
        body["origin"] = {"type": "point", "coordinates": [req.lon, req.lat]}

    if req.preferences:
        body["preferences"] = req.preferences
    elif req.lat is not None and req.lon is not None:
        body["preferences"] = {"geometry": {"type": "point", "coordinates": [req.lon, req.lat]}}

    if req.filters:
        body["filters"] = req.filters

    try:
        url = "https://api.tomtom.com/maps/orbis/places/suggest"
        post_data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=post_data,
            headers={
                "Content-Type": "application/json",
                "TomTom-Api-Key": api_key,
                "TomTom-Api-Version": "3",
                "Attributes": "results",
                "User-Agent": "ABRA-Places-Service/1.0"
            },
            method="POST"
        )
        with urllib.request.urlopen(request, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        results = data.get("results", [])
        payload = {
            "status": "success",
            "query": q,
            "count": len(results),
            "results": results,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        _places_cache["suggest"][cache_key] = {"timestamp": now_ts, "data": payload}
        return payload
    except Exception as e:
        return {"status": "error", "message": str(e)}

# -----------------------------------------------------------------
# 2. POST /places/discover - Discover locations
# -----------------------------------------------------------------
@app.post("/places/discover")
@app.post("/api/places/discover")
async def discover_places(req: PlacesDiscoverRequest):
    api_key = os.getenv("TOMTOM_API_KEY", "") or "YCWqMdqB0kPi0mLxLNN7WXMabGcCnQSd"
    if not api_key:
        return {"status": "error", "message": "TOMTOM_API_KEY not configured"}

    q = (req.query or "").strip()
    cache_key = f"{q.lower()}_{round(req.lat or 0, 3)}_{round(req.lon or 0, 3)}_{req.radius}_{req.maxResults}_{req.category or ''}"
    now_ts = datetime.now(timezone.utc).timestamp()
    cached = _places_cache["discover"].get(cache_key)
    if cached and (now_ts - cached["timestamp"] < 90):
        return cached["data"]

    # Construct request payload
    body: Dict[str, Any] = {
        "maxResults": min(max(req.maxResults or 30, 1), 100)
    }

    if q:
        body["query"] = q

    if req.origin:
        body["origin"] = req.origin
    elif req.lat is not None and req.lon is not None:
        body["origin"] = {"type": "point", "coordinates": [req.lon, req.lat]}

    if req.preferences:
        body["preferences"] = req.preferences
    elif req.lat is not None and req.lon is not None:
        body["preferences"] = {"geometry": {"type": "point", "coordinates": [req.lon, req.lat]}}

    # Filters
    filters = req.filters or {}
    if not filters.get("types"):
        filters["types"] = ["poi"]
    body["filters"] = filters

    # If query is empty and no poiTypes in filters, provide default category or query
    if not body.get("query") and not filters.get("poiTypes"):
        if req.category:
            body["query"] = req.category
        else:
            body["query"] = "popular places"

    try:
        url = "https://api.tomtom.com/maps/orbis/places/discover"
        post_data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=post_data,
            headers={
                "Content-Type": "application/json",
                "TomTom-Api-Key": api_key,
                "TomTom-Api-Version": "3",
                "Attributes": "results",
                "User-Agent": "ABRA-Places-Service/1.0"
            },
            method="POST"
        )
        with urllib.request.urlopen(request, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        raw_results = data.get("results", [])
        normalized = [normalize_orbis_place(r, req.lat, req.lon) for r in raw_results]

        payload = {
            "status": "success",
            "query": q,
            "count": len(normalized),
            "results": normalized,
            "center": {"lat": req.lat, "lon": req.lon} if req.lat and req.lon else None,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        _places_cache["discover"][cache_key] = {"timestamp": now_ts, "data": payload}
        return payload
    except Exception as e:
        # Fallback to TomTom Search API v2 if Orbis discover faces an error
        try:
            fallback_q = q or req.category or "places"
            encoded_query = urllib.parse.quote(fallback_q)
            fallback_url = f"https://api.tomtom.com/search/2/search/{encoded_query}.json?key={api_key}&limit={req.maxResults or 30}"
            if req.lat is not None and req.lon is not None:
                fallback_url += f"&lat={req.lat}&lon={req.lon}&radius={req.radius or 5000}"
            req_fb = urllib.request.Request(fallback_url, headers={"User-Agent": "ABRA-Places-Service/1.0"})
            with urllib.request.urlopen(req_fb, timeout=10) as resp_fb:
                fb_data = json.loads(resp_fb.read().decode("utf-8"))
            results_fb = fb_data.get("results", [])
            normalized_fb = [normalize_orbis_place(r, req.lat, req.lon) for r in results_fb]
            return {
                "status": "success",
                "query": q,
                "count": len(normalized_fb),
                "results": normalized_fb,
                "center": {"lat": req.lat, "lon": req.lon} if req.lat and req.lon else None,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e_fb:
            return {"status": "error", "message": f"{str(e)} | Fallback: {str(e_fb)}"}

# -----------------------------------------------------------------
# 3. GET /places/details/{type}/{id} - Details for a location
# -----------------------------------------------------------------
@app.get("/places/details/{type}/{id}")
@app.get("/api/places/details/{type}/{id}")
async def get_place_details(
    type: str,
    id: str,
    attributes: str = Query("contacts,address,poiTypes,title,position,openingHours,geometry")
):
    api_key = os.getenv("TOMTOM_API_KEY", "") or "YCWqMdqB0kPi0mLxLNN7WXMabGcCnQSd"
    if not api_key:
        return {"status": "error", "message": "TOMTOM_API_KEY not configured"}

    cache_key = f"{type}_{id}_{attributes}"
    now_ts = datetime.now(timezone.utc).timestamp()
    cached = _places_cache["details"].get(cache_key)
    if cached and (now_ts - cached["timestamp"] < 300):
        return cached["data"]

    try:
        url = f"https://api.tomtom.com/maps/orbis/places/details/{urllib.parse.quote(type)}/{urllib.parse.quote(id)}"
        request = urllib.request.Request(
            url,
            headers={
                "TomTom-Api-Key": api_key,
                "TomTom-Api-Version": "3",
                "Attributes": attributes,
                "User-Agent": "ABRA-Places-Service/1.0"
            }
        )
        with urllib.request.urlopen(request, timeout=10) as resp:
            details_data = json.loads(resp.read().decode("utf-8"))

        payload = {
            "status": "success",
            "type": type,
            "id": id,
            "details": details_data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        _places_cache["details"][cache_key] = {"timestamp": now_ts, "data": payload}
        return payload
    except urllib.error.HTTPError as e:
        # If specific attributes are rejected, try minimal safe attributes
        try:
            req_min = urllib.request.Request(
                f"https://api.tomtom.com/maps/orbis/places/details/{type}/{id}",
                headers={
                    "TomTom-Api-Key": api_key,
                    "TomTom-Api-Version": "3",
                    "Attributes": "title,position,address,contacts",
                    "User-Agent": "ABRA-Places-Service/1.0"
                }
            )
            with urllib.request.urlopen(req_min, timeout=8) as resp_min:
                details_data = json.loads(resp_min.read().decode("utf-8"))
            return {
                "status": "success",
                "type": type,
                "id": id,
                "details": details_data,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e_min:
            return {"status": "error", "message": f"HTTP {e.code}: {str(e_min)}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# -----------------------------------------------------------------
# Backwards-Compatible Search Endpoints
# -----------------------------------------------------------------
@app.get("/api/places/nearby")
async def get_nearby_places(
    lat: float = Query(...),
    lon: float = Query(...),
    radius: int = Query(5000, ge=100, le=50000),
    limit: int = Query(30, ge=1, le=100),
    category_set: str = Query(None, description="Comma-separated categorySet IDs, e.g. 7315,7311"),
    country_set: str = Query(None)
):
    discover_req = PlacesDiscoverRequest(
        lat=lat,
        lon=lon,
        radius=radius,
        maxResults=limit,
        category_set=category_set
    )
    return await discover_places(discover_req)

@app.get("/api/places/search")
async def search_places(
    query: str = Query(..., min_length=1),
    lat: float = Query(None),
    lon: float = Query(None),
    radius: int = Query(10000, ge=100, le=50000),
    limit: int = Query(30, ge=1, le=100),
    category_set: str = Query(None)
):
    discover_req = PlacesDiscoverRequest(
        query=query,
        lat=lat,
        lon=lon,
        radius=radius,
        maxResults=limit,
        category_set=category_set
    )
    return await discover_places(discover_req)

@app.get("/api/places/category")
async def search_places_by_category(
    category: str = Query(...),
    lat: float = Query(...),
    lon: float = Query(...),
    radius: int = Query(5000, ge=100, le=50000),
    limit: int = Query(30, ge=1, le=100)
):
    discover_req = PlacesDiscoverRequest(
        query=category,
        lat=lat,
        lon=lon,
        radius=radius,
        maxResults=limit,
        category=category
    )
    return await discover_places(discover_req)

@app.get("/api/places/reverse-geocode")
async def reverse_geocode_place(
    lat: float = Query(...),
    lon: float = Query(...)
):
    api_key = os.getenv("TOMTOM_API_KEY", "") or "YCWqMdqB0kPi0mLxLNN7WXMabGcCnQSd"
    if not api_key:
        return {"status": "error", "message": "TOMTOM_API_KEY not configured"}

    cache_key = f"{round(lat, 5)}_{round(lon, 5)}"
    now_ts = datetime.now(timezone.utc).timestamp()
    cached = _places_cache["geocode"].get(cache_key)
    if cached and (now_ts - cached["timestamp"] < 300):
        return cached["data"]

    try:
        url = f"https://api.tomtom.com/search/2/reverseGeocode/{lat},{lon}.json?key={api_key}"
        req = urllib.request.Request(url, headers={"User-Agent": "ABRA-Places-Service/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        addresses = data.get("addresses", [])
        primary = addresses[0] if addresses else {}
        addr_info = primary.get("address", {})

        payload = {
            "status": "success",
            "lat": lat,
            "lon": lon,
            "freeform_address": addr_info.get("freeformAddress") or "Unknown location",
            "municipality": addr_info.get("municipality") or addr_info.get("municipalitySubdivision") or "",
            "country": addr_info.get("country") or "",
            "postal_code": addr_info.get("postalCode") or "",
            "raw": primary
        }
        _places_cache["geocode"][cache_key] = {"timestamp": now_ts, "data": payload}
        return payload
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ====================================================
# TomTom Routing API (Calculate Route & Path Guidance)
# ====================================================
_routing_cache = {}

class RouteCalculateRequest(BaseModel):
    start_lat: float
    start_lon: float
    dest_lat: float
    dest_lon: float
    travel_mode: Optional[str] = "car"
    route_type: Optional[str] = "fastest"
    traffic: Optional[bool] = True
    depart_at: Optional[str] = None
    language: Optional[str] = "en-GB"

def format_route_duration(seconds: float) -> str:
    if not seconds or seconds <= 0:
        return "0 min"
    mins = round(seconds / 60)
    if mins < 60:
        return f"{mins} min"
    hrs = mins // 60
    rem_mins = mins % 60
    return f"{hrs}h {rem_mins}m" if rem_mins > 0 else f"{hrs}h"

def format_route_distance(meters: float) -> str:
    if not meters or meters <= 0:
        return "0 m"
    if meters < 1000:
        return f"{round(meters)} m"
    return f"{round(meters / 1000, 1)} km"

@app.get("/api/routing/calculate")
@app.post("/api/routing/calculate")
async def calculate_route(
    start_lat: Optional[float] = Query(None),
    start_lon: Optional[float] = Query(None),
    dest_lat: Optional[float] = Query(None),
    dest_lon: Optional[float] = Query(None),
    travel_mode: Optional[str] = Query("car"),
    route_type: Optional[str] = Query("fastest"),
    traffic: Optional[bool] = Query(True),
    language: Optional[str] = Query("en-GB"),
    body: Optional[RouteCalculateRequest] = None
):
    api_key = os.getenv("TOMTOM_API_KEY", "") or "YCWqMdqB0kPi0mLxLNN7WXMabGcCnQSd"
    if not api_key:
        return {"status": "error", "message": "TOMTOM_API_KEY not configured"}

    s_lat = body.start_lat if body else start_lat
    s_lon = body.start_lon if body else start_lon
    d_lat = body.dest_lat if body else dest_lat
    d_lon = body.dest_lon if body else dest_lon
    t_mode = (body.travel_mode if body else travel_mode) or "car"
    r_type = (body.route_type if body else route_type) or "fastest"
    use_traffic = (body.traffic if body else traffic)
    lang = (body.language if body else language) or "en-GB"

    if s_lat is None or s_lon is None or d_lat is None or d_lon is None:
        return {"status": "error", "message": "start_lat, start_lon, dest_lat, and dest_lon are required"}

    cache_key = f"{round(s_lat, 4)}_{round(s_lon, 4)}_{round(d_lat, 4)}_{round(d_lon, 4)}_{t_mode}_{r_type}_{use_traffic}"
    now_ts = datetime.now(timezone.utc).timestamp()
    cached = _routing_cache.get(cache_key)
    if cached and (now_ts - cached["timestamp"] < 45):
        return cached["data"]

    try:
        traffic_param = "true" if use_traffic else "false"
        url = (
            f"https://api.tomtom.com/routing/1/calculateRoute/{s_lat},{s_lon}:{d_lat},{d_lon}/json"
            f"?key={api_key}"
            f"&traffic={traffic_param}"
            f"&travelMode={urllib.parse.quote(t_mode)}"
            f"&routeType={urllib.parse.quote(r_type)}"
            f"&instructionsType=text"
            f"&language={urllib.parse.quote(lang)}"
            f"&computeTravelTimeFor=all"
        )

        req = urllib.request.Request(url, headers={"User-Agent": "ABRA-Routing-Service/1.0"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        routes = data.get("routes", [])
        if not routes:
            return {"status": "error", "message": "No routes found between these locations"}

        primary_route = routes[0]
        summary = primary_route.get("summary", {})
        legs = primary_route.get("legs", [])
        
        coordinates = []
        if legs and "points" in legs[0]:
            coordinates = [[p.get("longitude"), p.get("latitude")] for p in legs[0]["points"] if "longitude" in p and "latitude" in p]

        guidance = primary_route.get("guidance", {})
        raw_instructions = guidance.get("instructions", [])
        instructions = []
        for ins in raw_instructions:
            p = ins.get("point", {})
            instructions.append({
                "message": ins.get("message", ""),
                "street": ins.get("street", ""),
                "point": [p.get("longitude"), p.get("latitude")] if p else None,
                "type": ins.get("instructionType", ""),
                "length_meters": ins.get("routeOffsetInMeters", 0),
                "travel_time_seconds": ins.get("travelTimeInSeconds", 0)
            })

        length_meters = summary.get("lengthInMeters", 0)
        travel_time_secs = summary.get("travelTimeInSeconds", 0)
        traffic_delay_secs = summary.get("trafficDelayInSeconds", 0)

        payload = {
            "status": "success",
            "start": {"lat": s_lat, "lon": s_lon},
            "destination": {"lat": d_lat, "lon": d_lon},
            "travel_mode": t_mode,
            "route_type": r_type,
            "summary": {
                "length_meters": length_meters,
                "length_formatted": format_route_distance(length_meters),
                "travel_time_seconds": travel_time_secs,
                "travel_time_formatted": format_route_duration(travel_time_secs),
                "traffic_delay_seconds": traffic_delay_secs,
                "traffic_delay_formatted": f"+{format_route_duration(traffic_delay_secs)}" if traffic_delay_secs > 0 else "No delay",
                "departure_time": summary.get("departureTime"),
                "arrival_time": summary.get("arrivalTime")
            },
            "coordinates": coordinates,
            "geojson": {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": coordinates
                },
                "properties": {
                    "length_meters": length_meters,
                    "travel_time_seconds": travel_time_secs,
                    "traffic_delay_seconds": traffic_delay_secs,
                    "travel_mode": t_mode
                }
            },
            "instructions": instructions,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        _routing_cache[cache_key] = {"timestamp": now_ts, "data": payload}
        return payload
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        return {"status": "error", "message": f"HTTP {e.code}: {err_msg}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}