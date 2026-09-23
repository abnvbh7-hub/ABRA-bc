import os
import psycopg
from psycopg_pool import ConnectionPool
import dotenv

dotenv.load_dotenv()

pool = ConnectionPool(
    conninfo=os.getenv("DATABASE_URL"),
    min_size=0,
    max_size=20,
    timeout=30.0,
    max_idle=30
)