from database import pool
import os
from fastapi import Depends, FastAPI, UploadFile, File, Query
from fastapi.responses import StreamingResponse
import uvicorn
from models import AbraModel, LoginModel, GalleryModel, PaymentModel, PersonUpdateModel, ProcessGalleryModel, ResolveSuggestionModel
from auth import create_access_token, verify_access_token
from facial import extract_faces_from_image, find_matching_person, cosine_similarity, classify_face_match
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

@app.get("/gallery")
async def get_gallery(token: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    try:
        verify_access_token(token.credentials)
    except Exception as e:
        return {"status": "error", "message": str(e)}
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM abragallery ORDER BY timestamp DESC")
                rows = cur.fetchall()
                columns = [desc[0] for desc in cur.description]
                result = [dict(zip(columns, row)) for row in rows]
                
                for item in result:
                    if item.get("object_key"):
                        item["url"] = s3.generate_presigned_url(
                            ClientMethod='get_object',
                            Params={'Bucket': B2_BUCKET_NAME, 'Key': item["object_key"]},
                            ExpiresIn=3600
                        )

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




@app.post("/upload_statement")
async def upload_statement(file: UploadFile = File(...), token: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    try:
        verify_access_token(token.credentials)
    except Exception as e:
        return {"status": "error", "message": str(e)}

    try:
        content = await file.read()
        text = content.decode("utf-8")
        reader = csv.reader(io.StringIO(text))
        
        # Skip until we find the header row
        header = None
        for row in reader:
            if row and row[0] == "Date":
                header = row
                break
        
        if not header:
            return {"status": "error", "message": "Invalid CSV format, could not find header."}
        
        grouped_payments = {}
        
        for row in reader:
            if not row or len(row) < 8:
                continue
            
            date_str = row[0]
            time_str = row[1]
            details = row[2]
            transaction_type = row[5]
            amount_str = row[7]
            
            if transaction_type != 'DEBIT':
                continue
                
            # Parse Date and Time (e.g. "Sept 24, 2026", "9:36 AM")
            date_str = date_str.replace("Sept", "Sep")
            
            try:
                dt = datetime.strptime(f"{date_str} {time_str}", "%b %d, %Y %I:%M %p")
            except ValueError as e:
                print(f"Error parsing date {date_str} {time_str}: {e}")
                continue
            
            dt_minute = dt.replace(second=0, microsecond=0)
            amount = float(amount_str)
            
            vendor = details.replace("Paid to ", "").replace("Transfer to ", "").strip()
            if vendor == "-":
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
                    amount = data['amount']
                    
                    # Find the nearest row within 15 minutes (900 seconds)
                    cur.execute("""
                        SELECT timestamp 
                        FROM abradb 
                        WHERE abs(EXTRACT(EPOCH FROM (timestamp - %(dt_minute)s::timestamp))) <= 900
                        ORDER BY abs(EXTRACT(EPOCH FROM (timestamp - %(dt_minute)s::timestamp))) ASC 
                        LIMIT 1
                    """, {'dt_minute': dt_minute})
                    
                    row = cur.fetchone()
                    if row:
                        closest_timestamp = row[0]
                        cur.execute("""
                            UPDATE abradb
                            SET amount = %(amount)s, vendor = %(vendor)s
                            WHERE timestamp = %(closest_timestamp)s
                        """, {
                            'amount': amount, 
                            'vendor': vendor_str, 
                            'closest_timestamp': closest_timestamp
                        })
                        processed_count += 1
                    else:
                        unmatched.append({
                            'timestamp': dt_minute.strftime("%b %d, %Y %I:%M %p"),
                            'vendor': vendor_str,
                            'amount': amount
                        })

        return {
            "status": "success", 
            "processed_minutes": processed_count,
            "unmatched_payments": unmatched
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
async def get_person_detail(person_id: str, token: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    try:
        verify_access_token(token.credentials)
    except Exception as e:
        return {"status": "error", "message": str(e)}
    try:
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
                        p["url"] = s3.generate_presigned_url(
                            ClientMethod='get_object',
                            Params={'Bucket': B2_BUCKET_NAME, 'Key': p["object_key"]},
                            ExpiresIn=3600
                        )

                person_info["photos"] = photos
                person_info["photo_count"] = len(photos)

        return {"status": "success", "data": person_info}
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
async def get_face_suggestions(token: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    """Returns all pending match suggestions where similarity was close to ~40% for user confirmation."""
    try:
        verify_access_token(token.credentials)
    except Exception as e:
        return {"status": "error", "message": str(e)}
    try:
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
                    
                    full_photo_url = raw_url
                    if obj_key:
                        try:
                            full_photo_url = s3.generate_presigned_url(
                                'get_object',
                                Params={'Bucket': B2_BUCKET_NAME, 'Key': obj_key},
                                ExpiresIn=3600
                            )
                        except Exception as e:
                            print(f"Error presigning suggestion photo {obj_key}: {e}")

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
    similarity_threshold: float = Query(0.50),
    review_threshold: float = Query(0.38),
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
                        cur.execute("DELETE FROM abra_people")
                        cur.execute("DELETE FROM abra_face_suggestions")
                        cur.execute("UPDATE abragallery SET person_ids = '[]'::jsonb")
                        conn.commit()
                        yield f"data: {json.dumps({'type': 'status', 'message': 'Reset previous face indexes...'})}\n\n"

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
                            try:
                                s3_obj = s3.get_object(Bucket=B2_BUCKET_NAME, Key=obj_key)
                                image_bytes = s3_obj['Body'].read()
                            except Exception as s3_err:
                                print(f"[FaceProcess] S3 get error for {obj_key}: {s3_err}")

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
                                if person_obj and len(person_obj["embeddings"]) < 3 and sim < 0.88:
                                    person_obj["embeddings"].append(emb)
                                    cur.execute(
                                        "UPDATE abra_people SET embeddings = %s, updated_at = NOW() WHERE id = %s",
                                        (json.dumps(person_obj["embeddings"]), candidate_id)
                                    )
                            elif status == "needs_review" and candidate_id:
                                photo_reviews += 1
                                total_suggestions += 1
                                # Save pending suggestion for user review (~40% match)
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
        threshold = float(body.similarity_threshold if body.similarity_threshold is not None else 0.50)
        review_threshold = float(body.review_threshold if body.review_threshold is not None else 0.38)
        reindex_all = bool(body.reindex_all)

        with pool.connection() as conn:
            with conn.cursor() as cur:
                if reindex_all:
                    cur.execute("DELETE FROM abra_people")
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
                        try:
                            s3_obj = s3.get_object(Bucket=B2_BUCKET_NAME, Key=obj_key)
                            image_bytes = s3_obj['Body'].read()
                        except Exception as s3_err:
                            print(f"[FaceProcess] S3 get error for {obj_key}: {s3_err}")

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
                            if person_obj and len(person_obj["embeddings"]) < 3 and sim < 0.88:
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