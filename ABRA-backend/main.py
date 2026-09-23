from database import pool
import os
from fastapi import Depends, FastAPI
import uvicorn
from models import AbraModel,LoginModel
from auth import create_access_token, verify_access_token
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


app = FastAPI()

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
                        %(timestamp)s,
                        %(day)s,
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