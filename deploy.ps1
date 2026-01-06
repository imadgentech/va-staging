# Deploy to Google Cloud Run
# Usage: .\deploy.ps1 -ProjectId "your-project-id" -DbPassword "your-db-pass"

param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectId,

    [Parameter(Mandatory = $true)]
    [SecureString]$DbPassword
)

$start = Get-Date
Write-Host "🚀 Starting deployment to Cloud Run..." -ForegroundColor Cyan

# 1. Build
Write-Host "📦 Building container image..." -ForegroundColor Yellow
gcloud builds submit --tag gcr.io/$ProjectId/va-backend .

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Build failed!" -ForegroundColor Red
    exit 1
}

# 2. Deploy
Write-Host "☁️  Deploying using Cloud Run..." -ForegroundColor Yellow
gcloud run deploy va-backend `
    --image gcr.io/$ProjectId/va-backend `
    --platform managed `
    --region us-central1 `
    --allow-unauthenticated `
    --set-env-vars="DATABASE_URL=postgresql://n8n-user:${DbPassword}@34.131.176.248:5432/test" `
    --set-env-vars="JWT_SECRET=production_secret_change_me"

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Deployment failed!" -ForegroundColor Red
    exit 1
}

$end = Get-Date
$duration = $end - $start
Write-Host "✅ Deployment Complete! (Time: $($duration.TotalMinutes.ToString("N2")) min)" -ForegroundColor Green
