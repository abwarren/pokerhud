-- HUD Initial Schema Migration
-- Project: kzqrdtagpykoylhuqcyv
-- Date: 2026-04-13
--
-- Tables: users, games, hands, unified_players, player_stats, tournaments

-- ============================================
-- 1. USERS
-- ============================================
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    password_hash TEXT NOT NULL UNIQUE,
    device_id TEXT,
    settings JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now()
);
-- ============================================
-- 2. GAMES
-- ============================================
CREATE TABLE IF NOT EXISTS games (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    game_id TEXT NOT NULL,
    name TEXT DEFAULT '',
    game_url TEXT DEFAULT '',
    game_type TEXT DEFAULT 'PLO',
    total_hands INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, game_id)
);
CREATE INDEX IF NOT EXISTS idx_games_user ON games(user_id);
-- ============================================
-- 3. HANDS
-- ============================================
CREATE TABLE IF NOT EXISTS hands (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id UUID REFERENCES games(id) ON DELETE CASCADE,
    hand_id TEXT NOT NULL,
    hand_number INTEGER NOT NULL,
    game_type TEXT DEFAULT 'PLO',
    played_at TIMESTAMPTZ DEFAULT now(),
    players JSONB DEFAULT '[]'::jsonb,
    board JSONB DEFAULT '[]'::jsonb,
    result JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(game_id, hand_number)
);
CREATE INDEX IF NOT EXISTS idx_hands_game ON hands(game_id);
CREATE INDEX IF NOT EXISTS idx_hands_played ON hands(played_at);
-- ============================================
-- 4. UNIFIED PLAYERS (cross-game tracking)
-- ============================================
CREATE TABLE IF NOT EXISTS unified_players (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    primary_name TEXT NOT NULL,
    total_hands INTEGER DEFAULT 0,
    aggregate_stats JSONB DEFAULT '{}'::jsonb,
    positional_stats JSONB DEFAULT '{}'::jsonb,
    ip_oop_stats JSONB DEFAULT '{}'::jsonb,
    ai_analysis JSONB,
    updated_at TIMESTAMPTZ DEFAULT now(),
    last_seen TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, primary_name)
);
CREATE INDEX IF NOT EXISTS idx_unified_user ON unified_players(user_id);
CREATE INDEX IF NOT EXISTS idx_unified_name ON unified_players(primary_name);
-- ============================================
-- 5. PLAYER STATS (per-game breakdown)
-- ============================================
CREATE TABLE IF NOT EXISTS player_stats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    unified_player_id UUID REFERENCES unified_players(id) ON DELETE CASCADE,
    game_id UUID REFERENCES games(id) ON DELETE CASCADE,
    pokernow_id TEXT DEFAULT '',
    hands_played INTEGER DEFAULT 0,
    vpip REAL DEFAULT 0,
    pfr REAL DEFAULT 0,
    three_bet REAL DEFAULT 0,
    af REAL DEFAULT 0,
    wtsd REAL DEFAULT 0,
    w_sd REAL DEFAULT 0,
    cbet_flop REAL DEFAULT 0,
    cbet_turn REAL DEFAULT 0,
    cbet_river REAL DEFAULT 0,
    fold_to_cbet_flop REAL DEFAULT 0,
    fold_to_cbet_turn REAL DEFAULT 0,
    fold_to_cbet_river REAL DEFAULT 0,
    positional_stats JSONB DEFAULT '{}'::jsonb,
    aggregate_stats JSONB DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(unified_player_id, game_id)
);
CREATE INDEX IF NOT EXISTS idx_pstats_player ON player_stats(unified_player_id);
CREATE INDEX IF NOT EXISTS idx_pstats_game ON player_stats(game_id);
-- ============================================
-- 6. TOURNAMENTS (scraped from poker sites)
-- ============================================
CREATE TABLE IF NOT EXISTS tournaments (
    id BIGSERIAL PRIMARY KEY,
    site TEXT NOT NULL DEFAULT 'pokerbet',
    source TEXT NOT NULL DEFAULT 'cms',
    external_id TEXT,
    name TEXT NOT NULL,
    buy_in_entry_zar REAL,
    buy_in_fee_zar REAL,
    buy_in_total_zar REAL,
    prize_pool_guaranteed_zar REAL,
    start_time TEXT,
    schedule_day TEXT,
    game_type TEXT,
    status TEXT,
    players_registered INTEGER,
    players_max INTEGER,
    is_satellite BOOLEAN DEFAULT false,
    has_rebuy BOOLEAN DEFAULT false,
    has_late_reg BOOLEAN DEFAULT false,
    satellite_min_buy_in_zar REAL,
    rakeback_pct REAL,
    min_payout_zar REAL,
    max_payout_zar REAL,
    description TEXT DEFAULT '',
    image_url TEXT DEFAULT '',
    link_url TEXT DEFAULT '',
    raw_data JSONB,
    scraped_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(site, name, source)
);
CREATE INDEX IF NOT EXISTS idx_tournaments_site ON tournaments(site);
CREATE INDEX IF NOT EXISTS idx_tournaments_scraped ON tournaments(scraped_at);
-- ============================================
-- 7. ROW LEVEL SECURITY (RLS)
-- ============================================
-- Enable RLS on all tables
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE games ENABLE ROW LEVEL SECURITY;
ALTER TABLE hands ENABLE ROW LEVEL SECURITY;
ALTER TABLE unified_players ENABLE ROW LEVEL SECURITY;
ALTER TABLE player_stats ENABLE ROW LEVEL SECURITY;
ALTER TABLE tournaments ENABLE ROW LEVEL SECURITY;
-- Permissive policies for service_role (backend) and anon (for now)
-- Users: anyone can read/write (single-user mode, tighten later)
CREATE POLICY "Allow all on users" ON users FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on games" ON games FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on hands" ON hands FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on unified_players" ON unified_players FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on player_stats" ON player_stats FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on tournaments" ON tournaments FOR ALL USING (true) WITH CHECK (true);
