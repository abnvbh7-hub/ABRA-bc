import os
import psycopg
import dotenv
import hashlib

dotenv.load_dotenv()
DB_URL = os.getenv("DATABASE_URL")

def update_admin():
    # Adding .com to the email provided by user assuming it was a typo
    email = "abnvbh7@gmail.com"
    pwd = "Abnvbh7"
    pw_hash = hashlib.sha256(pwd.encode()).hexdigest()
    
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            # Update the existing admin account
            cur.execute("""
                UPDATE users 
                SET email = %s, password_hash = %s 
                WHERE username = 'admin' OR is_admin = TRUE
            """, (email, pw_hash))
            
            # If no admin existed for some reason, we create one
            if cur.rowcount == 0:
                cur.execute("""
                    INSERT INTO users (username, email, password_hash, is_admin)
                    VALUES ('admin', %s, %s, TRUE)
                """, (email, pw_hash))
                
            conn.commit()
            print("Admin credentials updated successfully.")

if __name__ == "__main__":
    update_admin()
