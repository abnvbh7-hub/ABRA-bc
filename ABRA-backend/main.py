from database import pool
import os
from fastapi import Depends, FastAPI, UploadFile, File
import uvicorn
from models import AbraModel, LoginModel, GalleryModel, SignupOTPModel, VerifyOTPModel
from auth import create_access_token, verify_access_token, hash_password, verify_password
from email_utils import send_email
import csv
import io
from datetime import datetime, date
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import boto3
from botocore.client import Config
import uuid
import random

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
                cur.execute("SELECT id, username, password_hash, is_admin FROM users WHERE email = %s", (data.email,))
                user = cur.fetchone()
                if user and verify_password(data.password, user[2]):
                    token = create_access_token({
                        "user_id": user[0],
                        "username": user[1],
                        "email": data.email,
                        "is_admin": user[3]
                    })
                    return {"status": "success", "token": token, "is_admin": user[3], "username": user[1]}
                else:
                    return {"status": "error", "message": "Invalid email or password"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/signup/request_otp")
async def request_otp(data: SignupOTPModel):
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM users WHERE email = %s", (data.email,))
                if cur.fetchone():
                    return {"status": "error", "message": "Email already exists"}
                
                otp = str(random.randint(100000, 999999))
                
                # Send OTP via email
                email_body = f"""
                <div style="font-family: Arial, sans-serif; padding: 20px; max-width: 600px; margin: 0 auto; border: 1px solid #eaeaea; border-radius: 10px;">
                    <h2 style="color: #3b82f6;">Welcome to ABRA!</h2>
                    <p style="font-size: 16px; color: #333;">Hello {data.username},</p>
                    <p style="font-size: 16px; color: #333;">Your One-Time Password (OTP) for signup is:</p>
                    <div style="background-color: #f3f4f6; padding: 15px; border-radius: 8px; text-align: center; margin: 20px 0;">
                        <strong style="font-size: 32px; letter-spacing: 5px; color: #1f2937;">{otp}</strong>
                    </div>
                    <p style="font-size: 14px; color: #666;">This OTP will expire in 10 minutes.</p>
                </div>
                """
                send_email(data.email, "ABRA - Your Signup OTP", email_body)
                
                # Print OTP to console for development backup
                print(f"\n======================\nOTP for {data.email}: {otp}\n======================\n")
                
                cur.execute("""
                    INSERT INTO otps (email, otp, expires_at) 
                    VALUES (%s, %s, CURRENT_TIMESTAMP + INTERVAL '10 minutes')
                    ON CONFLICT (email) DO UPDATE SET otp = EXCLUDED.otp, expires_at = EXCLUDED.expires_at
                """, (data.email, otp))
                
                # Also temporarily store requested username
                cur.execute("UPDATE otps SET otp = %s WHERE email = %s", (f"{otp}|{data.username}", data.email))
                conn.commit()
                return {"status": "success", "message": "OTP generated. Check console."}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/signup/verify_otp")
async def verify_otp(data: VerifyOTPModel):
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT otp, expires_at FROM otps WHERE email = %s", (data.email,))
                row = cur.fetchone()
                if not row or row[1] < datetime.utcnow():
                    return {"status": "error", "message": "Invalid or expired OTP"}
                
                stored_otp, username = row[0].split('|')
                if stored_otp != data.otp:
                    return {"status": "error", "message": "Invalid OTP"}
                
                pw_hash = hash_password(data.password)
                
                cur.execute("INSERT INTO users (email, username, password_hash) VALUES (%s, %s, %s)", (data.email, username, pw_hash))
                cur.execute("DELETE FROM otps WHERE email = %s", (data.email,))
                conn.commit()
                return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/punch")
async def log_punch(data: AbraModel, token: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    try:
        payload = verify_access_token(token.credentials)
        user_id = payload.get("user_id")
    except Exception as e:
        return {"status": "error", "message": str(e)}
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                data_dict = data.model_dump()
                data_dict['user_id'] = user_id
                cur.execute(
                    """
                    INSERT INTO abradb (
                        user_id,
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
                        %(user_id)s,
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
                    data_dict
                )
                conn.commit()

        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/pick")
async def pick_data(token: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    try:
        payload = verify_access_token(token.credentials)
        user_id = payload.get("user_id")
    except Exception as e:
        return {"status": "error", "message": str(e)}
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM abradb WHERE user_id = %s ORDER BY timestamp DESC LIMIT 100", (user_id,))
                rows = cur.fetchall()
                columns = [desc[0] for desc in cur.description]
                result = [dict(zip(columns, row)) for row in rows]

        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/payments")
async def get_payments(token: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    try:
        payload = verify_access_token(token.credentials)
        user_id = payload.get("user_id")
    except Exception as e:
        return {"status": "error", "message": str(e)}
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM abradb WHERE user_id = %s AND amount IS NOT NULL AND vendor IS NOT NULL ORDER BY timestamp DESC LIMIT 500", (user_id,))
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
        payload = verify_access_token(token.credentials)
        user_id = payload.get("user_id")
    except Exception as e:
        return {"status": "error", "message": str(e)}
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM abragallery WHERE user_id = %s ORDER BY timestamp DESC", (user_id,))
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
        payload = verify_access_token(token.credentials)
        user_id = payload.get("user_id")
    except Exception as e:
        return {"status": "error", "message": str(e)}
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                data_dict = data.model_dump()
                data_dict['user_id'] = user_id
                cur.execute(
                    """
                    INSERT INTO abragallery (
                        user_id,
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
                        %(user_id)s,
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
                    data_dict
                )
                conn.commit()
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.delete("/gallery/{item_id}")
async def delete_gallery(item_id: int, token: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    try:
        payload = verify_access_token(token.credentials)
        user_id = payload.get("user_id")
    except Exception as e:
        return {"status": "error", "message": str(e)}
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT object_key FROM abragallery WHERE id = %s AND user_id = %s", (item_id, user_id))
                row = cur.fetchone()
                if row and row[0]:
                    try:
                        s3.delete_object(Bucket=B2_BUCKET_NAME, Key=row[0])
                    except Exception as e:
                        print("Failed to delete from B2:", e)
                cur.execute("DELETE FROM abragallery WHERE id = %s AND user_id = %s", (item_id, user_id))
                conn.commit()
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/history")
async def history_data(range: str = "today", token: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    try:
        payload = verify_access_token(token.credentials)
        user_id = payload.get("user_id")
    except Exception as e:
        return {"status": "error", "message": str(e)}
        
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                if range == "yesterday":
                    cur.execute("SELECT * FROM abradb WHERE user_id = %s AND DATE(timestamp) = CURRENT_DATE - INTERVAL '1 day' ORDER BY timestamp ASC", (user_id,))
                elif range == "today":
                    cur.execute("SELECT * FROM abradb WHERE user_id = %s AND DATE(timestamp) = CURRENT_DATE ORDER BY timestamp ASC", (user_id,))
                else:
                    cur.execute("SELECT * FROM abradb WHERE user_id = %s AND DATE(timestamp) = %s ORDER BY timestamp ASC", (user_id, range))
                    
                rows = cur.fetchall()
                columns = [desc[0] for desc in cur.description]
                result = [dict(zip(columns, row)) for row in rows]
                
        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/upload_statement")
async def upload_statement(file: UploadFile = File(...), token: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    try:
        payload = verify_access_token(token.credentials)
        user_id = payload.get("user_id")
    except Exception as e:
        return {"status": "error", "message": str(e)}

    try:
        content = await file.read()
        text = content.decode("utf-8")
        reader = csv.reader(io.StringIO(text))
        
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
                    
                    cur.execute("""
                        SELECT timestamp 
                        FROM abradb 
                        WHERE user_id = %(user_id)s AND abs(EXTRACT(EPOCH FROM (timestamp - %(dt_minute)s::timestamp))) <= 900
                        ORDER BY abs(EXTRACT(EPOCH FROM (timestamp - %(dt_minute)s::timestamp))) ASC 
                        LIMIT 1
                    """, {'user_id': user_id, 'dt_minute': dt_minute})
                    
                    row = cur.fetchone()
                    if row:
                        closest_timestamp = row[0]
                        cur.execute("""
                            UPDATE abradb
                            SET amount = %(amount)s, vendor = %(vendor)s
                            WHERE user_id = %(user_id)s AND timestamp = %(closest_timestamp)s
                        """, {
                            'amount': amount, 
                            'vendor': vendor_str, 
                            'user_id': user_id,
                            'closest_timestamp': closest_timestamp
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
            "unmatched_payments": unmatched
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/admin/users")
async def get_admin_users(token: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    try:
        payload = verify_access_token(token.credentials)
        is_admin = payload.get("is_admin")
        if not is_admin:
            return {"status": "error", "message": "Unauthorized"}
            
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, username, email, is_admin FROM users ORDER BY id")
                rows = cur.fetchall()
                columns = [desc[0] for desc in cur.description]
                result = [dict(zip(columns, row)) for row in rows]
                
                # Fetch basic stats per user
                for user in result:
                    cur.execute("SELECT COUNT(*) FROM abradb WHERE user_id = %s", (user['id'],))
                    user['punch_count'] = cur.fetchone()[0]
                    
        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/admin/history/{target_user_id}")
async def get_admin_history(target_user_id: int, range: str = "today", token: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    try:
        payload = verify_access_token(token.credentials)
        if not payload.get("is_admin"):
            return {"status": "error", "message": "Unauthorized"}
            
        with pool.connection() as conn:
            with conn.cursor() as cur:
                if range == "yesterday":
                    cur.execute("SELECT * FROM abradb WHERE user_id = %s AND DATE(timestamp) = CURRENT_DATE - INTERVAL '1 day' ORDER BY timestamp ASC", (target_user_id,))
                elif range == "today":
                    cur.execute("SELECT * FROM abradb WHERE user_id = %s AND DATE(timestamp) = CURRENT_DATE ORDER BY timestamp ASC", (target_user_id,))
                else:
                    cur.execute("SELECT * FROM abradb WHERE user_id = %s AND DATE(timestamp) = %s ORDER BY timestamp ASC", (target_user_id, range))
                    
                rows = cur.fetchall()
                columns = [desc[0] for desc in cur.description]
                result = [dict(zip(columns, row)) for row in rows]
                
        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}