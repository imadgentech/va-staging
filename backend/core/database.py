import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Get DB URL from env
# Priority: Explicit DATABASE_URL -> Constructed from components
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

if not SQLALCHEMY_DATABASE_URL:
    db_user = os.getenv("DB_USER", "n8n-user")
    db_pass = os.getenv("DB_POSTGRESDB_PASSWORD") or os.getenv("DB_PASS")
    # Default to internal IP provided or cloudsql socket if host starts with /
    db_host = os.getenv("DB_HOST", "172.27.80.9") 
    db_port = os.getenv("DB_PORT", "5678")
    db_name = os.getenv("DB_NAME", "test")

    if db_user and db_pass and db_host:
         # Handle URL encoding for password if needed, usually recommended
         # but strict quoting might be needed. 
         # For simple usage:
         import urllib.parse
         encoded_pass = urllib.parse.quote_plus(db_pass)
         SQLALCHEMY_DATABASE_URL = f"postgresql://{db_user}:{encoded_pass}@{db_host}:{db_port}/{db_name}"
    else:
         # Fallback or leave None to fail later
         pass

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    # pool_pre_ping=True checks for stale connections
    pool_pre_ping=True
) if SQLALCHEMY_DATABASE_URL else None

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    """Dependency for FastAPI routes."""
    if engine is None:
        raise RuntimeError("DATABASE_URL is not set in environment variables.")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
