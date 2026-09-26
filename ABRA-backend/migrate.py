import os
import psycopg
import dotenv

dotenv.load_dotenv()
DB_URL = os.getenv("DATABASE_URL")

def migrate():
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            # Create users table
            cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR UNIQUE,
                email VARCHAR UNIQUE,
                password_hash VARCHAR,
                is_admin BOOLEAN DEFAULT FALSE
            )
            """)
            
            # Create OTP table
            cur.execute("""
            CREATE TABLE IF NOT EXISTS otps (
                email VARCHAR PRIMARY KEY,
                otp VARCHAR,
                expires_at TIMESTAMP
            )
            """)
            
            # Check if user_id exists in abradb
            cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='abradb' and column_name='user_id';
            """)
            if not cur.fetchone():
                print("Adding user_id to abradb")
                cur.execute("ALTER TABLE abradb ADD COLUMN user_id INTEGER REFERENCES users(id)")
                
            # Check if user_id exists in abragallery
            cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='abragallery' and column_name='user_id';
            """)
            if not cur.fetchone():
                print("Adding user_id to abragallery")
                cur.execute("ALTER TABLE abragallery ADD COLUMN user_id INTEGER REFERENCES users(id)")
                
            # Create a default admin user if none exists
            cur.execute("SELECT id FROM users WHERE username = 'admin'")
            admin_user = cur.fetchone()
            if not admin_user:
                print("Creating default admin user")
                # Using a simple hash for 'admin123' just for the default admin
                import hashlib
                pw_hash = hashlib.sha256('admin123'.encode()).hexdigest()
                cur.execute("INSERT INTO users (username, email, password_hash, is_admin) VALUES ('admin', 'admin@abra.com', %s, TRUE) RETURNING id", (pw_hash,))
                admin_id = cur.fetchone()[0]
                # Update existing records to belong to admin
                cur.execute("UPDATE abradb SET user_id = %s WHERE user_id IS NULL", (admin_id,))
                cur.execute("UPDATE abragallery SET user_id = %s WHERE user_id IS NULL", (admin_id,))
            else:
                print("Admin user already exists")
                admin_id = admin_user[0]
                cur.execute("UPDATE abradb SET user_id = %s WHERE user_id IS NULL", (admin_id,))
                cur.execute("UPDATE abragallery SET user_id = %s WHERE user_id IS NULL", (admin_id,))
                
            conn.commit()
            print("Migration complete.")

if __name__ == "__main__":
    migrate()
