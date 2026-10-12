import os
import psycopg
import dotenv
from psycopg_pool import ConnectionPool

dotenv.load_dotenv()

pool = ConnectionPool(
    conninfo=os.getenv("DATABASE_URL"),
    min_size=1,
    max_size=1
)

def create_table():
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS abragallery (
                    id SERIAL PRIMARY KEY,
                    url TEXT NOT NULL,
                    latitude FLOAT,
                    longitude FLOAT,
                    timestamp TIMESTAMP,
                    speed FLOAT,
                    battery_level FLOAT,
                    is_charging BOOLEAN,
                    network_type VARCHAR(50)
                );
            """)
            conn.commit()
    print("Table abragallery created successfully")

if __name__ == "__main__":
    create_table()
