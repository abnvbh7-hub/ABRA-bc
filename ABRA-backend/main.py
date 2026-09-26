from database import pool
import os
from fastapi import Depends, FastAPI, UploadFile, File
import uvicorn
from models import AbraModel,LoginModel,GalleryModel
from auth import create_access_token, verify_access_token
import csv
import io
from datetime import datetime, date
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import boto3
from botocore.client import Config
import uuid

app = FastAPI()

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
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
)


@app.get("/")
async def read_root():
    return {"Adaptive Behavioral Reasoning Assistant": "ABRA"}

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
    # Verify the token
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
    # Verify the token
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
async def get_payments(token: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    try:
        verify_access_token(token.credentials)
    except Exception as e:
        return {"status": "error", "message": str(e)}
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM abradb WHERE amount IS NOT NULL AND vendor IS NOT NULL ORDER BY timestamp DESC LIMIT 500")
                rows = cur.fetchall()
                columns = [desc[0] for desc in cur.description]
                result = [dict(zip(columns, row)) for row in rows]

        return {"status": "success", "data": result}
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
                        network_type
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
                        %(network_type)s
                    )
                    """,
                    data.model_dump()
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