-- 1. Create Users Table
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR PRIMARY KEY,
    email VARCHAR UNIQUE NOT NULL,
    business_name VARCHAR,
    full_name VARCHAR,
    occupation VARCHAR,
    phone VARCHAR,
    password_hash VARCHAR,
    status VARCHAR DEFAULT 'pending',
    restaurant_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Create Restaurants Table
CREATE TABLE IF NOT EXISTS restaurants (
    id SERIAL PRIMARY KEY,
    name VARCHAR NOT NULL,
    phone_number VARCHAR UNIQUE,
    owner_id VARCHAR REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Create Reservations Table
CREATE TABLE IF NOT EXISTS reservations (
    id SERIAL PRIMARY KEY,
    restaurant_id INTEGER REFERENCES restaurants(id),
    guest_name VARCHAR,
    guest_phone VARCHAR,
    date VARCHAR,
    time VARCHAR,
    guests INTEGER,
    special_requests TEXT,
    status VARCHAR DEFAULT 'Confirmed',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Create Pending Reservations Table
CREATE TABLE IF NOT EXISTS pending_reservations (
    id SERIAL PRIMARY KEY,
    data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Create Call Logs Table
CREATE TABLE IF NOT EXISTS call_logs (
    id SERIAL PRIMARY KEY,
    restaurant_id INTEGER REFERENCES restaurants(id),
    call_uuid VARCHAR,
    intent VARCHAR,
    outcome VARCHAR,
    agent_summary TEXT,
    recording_url TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create Indexes (Optional but recommended)
CREATE INDEX IF NOT EXISTS ix_users_email ON users(email);
CREATE INDEX IF NOT EXISTS ix_restaurants_phone_number ON restaurants(phone_number);
CREATE INDEX IF NOT EXISTS ix_call_logs_call_uuid ON call_logs(call_uuid);
