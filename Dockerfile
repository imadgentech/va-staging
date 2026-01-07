FROM python:3.10-slim

WORKDIR /app

# Install system dependencies for potential psycopg2 compilation if needed (binary usually suffices)
# RUN apt-get update && apt-get install -y gcc libpq-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default port for Cloud Run (updated to 8090 for local compatibility)
ENV PORT=8090

CMD ["sh", "-c", "uvicorn backend.server:app --host 0.0.0.0 --port ${PORT}"]
