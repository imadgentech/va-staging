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
         import urllib.parse
         encoded_pass = urllib.parse.quote_plus(db_pass)
         
         if db_host.startswith("/"):
             # Unix socket (Cloud SQL)
             # Format: postgresql://user:pass@/dbname?host=/path/to/socket/dir
             SQLALCHEMY_DATABASE_URL = f"postgresql://{db_user}:{encoded_pass}@/{db_name}?host={db_host}"
         else:
             # Standard TCP
             SQLALCHEMY_DATABASE_URL = f"postgresql://{db_user}:{encoded_pass}@{db_host}:{db_port}/{db_name}"
    else:
         # Fallback or leave None to fail later
         pass

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    # pool_pre_ping=True checks for stale connections
    pool_pre_ping=True,
    connect_args={'connect_timeout': 5} # Fast fail if DB unreachable
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
