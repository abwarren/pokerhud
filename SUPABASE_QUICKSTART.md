# Supabase Setup - Quick Start

## 🎯 Current Status

✅ Supabase project: **kzqrdtagpykoylhuqcyv**  
✅ Migration SQL ready: `/opt/pokerhud/APPLY_THIS_MIGRATION.sql`  
✅ CLI linked to project  
⏳ Database tables: **Need to apply migration**

---

## Step 1: Apply Migration (2 minutes)

### Open SQL Editor:
```
https://supabase.com/dashboard/project/kzqrdtagpykoylhuqcyv/sql/new
```

### Copy & Run This SQL:

```sql
-- HUD Initial Schema Migration
-- Creates 6 tables: users, games, hands, unified_players, player_stats, tournaments

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    password_hash TEXT NOT NULL UNIQUE,
    device_id TEXT,
    settings JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now()
);

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

-- Enable RLS
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE games ENABLE ROW LEVEL SECURITY;
ALTER TABLE hands ENABLE ROW LEVEL SECURITY;
ALTER TABLE unified_players ENABLE ROW LEVEL SECURITY;
ALTER TABLE player_stats ENABLE ROW LEVEL SECURITY;
ALTER TABLE tournaments ENABLE ROW LEVEL SECURITY;

-- Policies (open access for single-user)
CREATE POLICY "Allow all on users" ON users FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on games" ON games FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on hands" ON hands FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on unified_players" ON unified_players FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on player_stats" ON player_stats FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on tournaments" ON tournaments FOR ALL USING (true) WITH CHECK (true);
```

**Click RUN** → Wait for "Success. No rows returned"

---

## Step 2: Get Anon Key (30 seconds)

### Open API Settings:
```
https://supabase.com/dashboard/project/kzqrdtagpykoylhuqcyv/settings/api
```

### Copy the "anon" key (starts with `eyJ...`)

---

## Step 3: Configure HUD (1 minute)

```bash
cd /opt/pokerhud/pokerhud

# Replace YOUR_KEY with the anon key you copied
sed -i 's|YOUR_ANON_KEY_HERE|eyJ_your_key_here|g' shared/utils/supabase.ts
sed -i 's|YOUR_ANON_KEY_HERE|eyJ_your_key_here|g' check-migrations.js

# Rebuild extension
npm run build:extension
```

---

## Step 4: Verify (30 seconds)

```bash
cd /opt/pokerhud/pokerhud
node check-migrations.js
```

Should show: **"✅ Supabase connection successful!"**

---

## Step 5: Load Extension (1 minute)

1. Open Chrome: `chrome://extensions/`
2. Toggle "Developer mode" ON
3. Click "Load unpacked"
4. Select: `/opt/pokerhud/pokerhud/extension/dist/`
5. Click extension icon → Enter password: `aksuited`

---

## 🎯 Total Time: 5 minutes

**After this, your HUD will be fully functional!**

---

## 📋 Quick Links

- **SQL Editor:** https://supabase.com/dashboard/project/kzqrdtagpykoylhuqcyv/sql/new
- **API Keys:** https://supabase.com/dashboard/project/kzqrdtagpykoylhuqcyv/settings/api
- **Table Editor:** https://supabase.com/dashboard/project/kzqrdtagpykoylhuqcyv/editor
- **Database:** https://supabase.com/dashboard/project/kzqrdtagpykoylhuqcyv/database/tables

---

**Start with Step 1 now!** 🚀
