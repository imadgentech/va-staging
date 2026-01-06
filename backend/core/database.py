import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Get DB URL from env, or default to a local placeholder for safety (user must override)
# Format: postgresql://user:password@host:port/dbname
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

if not SQLALCHEMY_DATABASE_URL:
    # Fallback/Warning if not set
    # Using sqlite for local dev if they forget, or just error out? 
    # Better to default to None and let it fail if they try completely without config.
    # But for now let's allow it to be imported even if None.
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
