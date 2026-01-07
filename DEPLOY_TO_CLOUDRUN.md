# Deployment Guide: Cloud Run & PostgreSQL

This project is configured to run as a containerized FastAPI application on Google Cloud Run, connecting to a PostgreSQL database.

## 1. Environment Variables

You must configure the following environment variables in your Cloud Run service for the application to function:

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | (Recommended) Full connection string: `postgresql://user:password@host:port/dbname` |
| `DB_HOST` | Database Host (if `DATABASE_URL` is not provided) |
| `DB_USER` | Database User |
| `DB_PASS` | Database Password |
| `DB_NAME` | Database Name |
| `DB_PORT` | Database Port (default 5432) |
| `PORT` | The port the container listens on (default 8080) |
| `JWT_SECRET` | Secret key for JWT tokens |

## 2. Building the Image

### Using GitHub Actions (Recommended)
If you push this to GitHub, you or the user can set up a workflow to build and push to Google Artifact Registry.

### Using Google Cloud Build (Manual)
Run this command from the project root:
```bash
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/voice-orchestrator
```

## 3. Database Connection (Cloud SQL)

If using **Google Cloud SQL**:
1. Enable the **Cloud SQL Admin API**.
2. Add the **Cloud SQL Client** role to the Service Account used by Cloud Run.
3. In the Cloud Run service configuration, add the Cloud SQL instance connection.
4. Set `DB_HOST` to `/cloudsql/PROJECT_ID:REGION:INSTANCE_ID`.
5. Set `DB_PORT` to `5432`.

## 4. Notes
- The `Dockerfile` is located in the root directory.
- Static assets/frontend are currently excluded from the container build via `.dockerignore` as the backend serves as a standalone API.
- The `verify_db.py` script can be used to test the connection within the container if needed (by running `python verify_db.py` inside the container).
