import os
import urllib.parse
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from backend.core.models import Base

# Hardcoded for verification
# User provided: 34.131.176.248, n8n-user, h&qh5nW<
# Encoding: & -> %26, < -> %3C
DB_URL = "postgresql://n8n-user:h%26qh5nW%3C@34.131.176.248:5432/test"

def verify():
    print(f"Connecting to {DB_URL.split('@')[1]}...")
    try:
        engine = create_engine(DB_URL, connect_args={'connect_timeout': 10})
        connection = engine.connect()
        print("✅ Connection successful!")
        
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        print(f"Existing tables: {existing_tables}")
        
        # Try to create tables if they don't exist
        print("Attempting to create missing tables based on models...")
        Base.metadata.create_all(engine)
        
        # Check again
        inspector = inspect(engine)
        current_tables = inspector.get_table_names()
        print(f"Tables after creation attempt: {current_tables}")
        
        # Verify specific columns for 'users'
        if 'users' in current_tables:
            columns = [c['name'] for c in inspector.get_columns('users')]
            print(f"Columns in 'users' table: {columns}")
            
            required = ['business_name', 'status', 'password_hash']
            missing = [r for r in required if r not in columns]
            if missing:
                print(f"[!]  WARNING: 'users' table exists but is missing columns: {missing}")
            else:
                print("[OK] 'users' table schema looks correct (checked key columns).")

        connection.close()
        
    except Exception as e:
        print(f"[X] Connection failed: {e}")

if __name__ == "__main__":
    verify()
