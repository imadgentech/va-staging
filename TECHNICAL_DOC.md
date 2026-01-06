# Voice Orchestrator Technical Documentation

This document provides a technical overview of the **Voice Orchestrator** project, a system designed to automate front-desk operations (like restaurant reservations) using AI voice agents.

## Project Overview

Voice Orchestrator uses AI to handle incoming customer calls, extract relevant details (name, date, time, guest count), and manage these details in a structured way using Airtable. It features a modern React-based frontend for business owners to track calls and reservations.

---

## Tech Stack

### Backend
- **Framework**: [FastAPI](https://fastapi.tiangolo.com/) (Python)
- **Database/Storage**: [Airtable](https://airtable.com/) (via `pyairtable`)
- **Authentication**: JWT (JSON Web Tokens) with email/password hashing (SHA-256)
- **Integration**: [Vapi](https://vapi.ai/) (for Voice AI orchestration)
- **Deployment**: Heroku/Cloud Run (via `Procfile`)

### Frontend
- **Framework**: [React](https://react.dev/) (Vite)
- **Styling**: [Tailwind CSS](https://tailwindcss.com/)
- **Icons**: [Lucide React](https://lucide.dev/)
- **Charts**: [Recharts](https://recharts.org/)
- **Voice Simulation**: Web Speech API (`webkitSpeechRecognition`) for local demos.

---

## Architecture & Modules

### Backend Structure (`/backend`)

- **`server.py`**: The entry point. Handles API routing, CORS, and authentication.
- **`core/airtable_client.py`**: Manages all interactions with Airtable bases (Restaurants, Reservations, Call Logs).
- **`core/users_airtable.py`**: Specifically handles user signups, logins, and profiles stored in Airtable.
- **`core/reservation_mapper.py`**: A utility to normalize raw AI output (e.g., "7pm") into structured formats (e.g., "19:00").
- **`core/prompts.py`**: Generates dynamic system prompts for the AI agent based on the business type (Restaurant, Hotel, etc.).
- **`core/extract_from_transcript.py`**: Uses AI/Logic to pull reservation details from a raw call transcript.

### Frontend Structure (`/frontend-react`)

- **`src/App.jsx`**: A monolithic React application managing multiple views:
    - **Hero View**: Landing page with a live "Voice Simulation" demo.
    - **Signup/Login**: User onboarding and authentication.
    - **Dashboard**: Real-time stats and call logs for the authenticated business.
- **Hash-based Routing**: Simple client-side routing using window location hashes.

---

## Data Flow

1. **User Onboarding**: A user signs up → Data is stored in Airtable → Admin manually sets `status` to `done` and assigns a `restaurant_id`.
2. **The Call**: An incoming call is handled by Vapi (configured with prompts from the backend).
3. **Data Extraction**: After the call, the transcript is sent to the backend. The backend extracts reservation details and logs the call.
4. **Dashboard Update**: The frontend polls or refreshes to show new call logs and updated statistics fetched from Airtable.

---

## Setup & Local Development

### Backend Setup
1. Create a virtual environment: `python -m venv venv`
2. Install dependencies: `pip install -r requirements.txt`
3. Configure `.env`:
   ```env
   AIRTABLE_API_KEY=xxx
   AIRTABLE_BASE_ID=xxx
   AIRTABLE_USERS_BASE_ID=xxx
   VAPI_API_KEY=xxx
   JWT_SECRET=xxx
   ```
4. Run server: `uvicorn backend.server:app --reload`

### Frontend Setup
1. Navigate to directory: `cd frontend-react`
2. Install dependencies: `npm install`
3. Configure environment: Create `.env` with `VITE_API_BASE=http://localhost:8000`
4. Run development server: `npm run dev`

---

## Key Integrations

### Vapi
Used for the real-time voice interaction. The backend provides the `system_prompt` which guides the AI to collect specific details without confirming the reservation prematurely.

### Airtable
Acts as the primary CRM and database.
- **Restaurants Table**: Stores business details and configurations.
- **Reservations Table**: Stores confirmed customer bookings.
- **Call Logs Table**: Tracks every interaction for analytics.
