-- Quick HUD Login Fix - Create users table only
-- Apply this in Supabase SQL Editor to enable login

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    password_hash TEXT NOT NULL UNIQUE,
    device_id TEXT,
    settings JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all on users" ON users FOR ALL USING (true) WITH CHECK (true);
