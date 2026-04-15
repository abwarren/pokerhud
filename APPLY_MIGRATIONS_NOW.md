# 🎯 Apply Supabase Migrations - STEP BY STEP

## Supabase Project Info
- **Project ID**: `ctwrdkipxuztjjbkbhqk`
- **URL**: https://ctwrdkipxuztjjbkbhqk.supabase.co
- **SQL Editor**: https://supabase.com/dashboard/project/ctwrdkipxuztjjbkbhqk/sql/new

---

## 📋 STEP 1: Open Supabase SQL Editor

Click this link (you'll need to be logged in):
```
https://supabase.com/dashboard/project/ctwrdkipxuztjjbkbhqk/sql/new
```

---

## 📋 STEP 2: Apply Migrations (in order)

You need to run **5 migration files** in this exact order:

### Migration 1: Initial Schema
**File**: `supabase/migrations/20260201000000_initial_schema.sql`
**Creates**: 8 tables (users, games, unified_players, player_aliases, hands, player_stats, player_notes, import_logs)

### Migration 2: Enable RLS
**File**: `supabase/migrations/20260201000001_enable_rls.sql`
**Sets up**: Row-level security so users only see their own data

### Migration 3: AI Analysis
**File**: `supabase/migrations/20260201000002_add_ai_analysis.sql`
**Adds**: AI-powered player analysis columns

### Migration 4: Enhanced Stats
**File**: `supabase/migrations/20260201000003_enhanced_stats_and_notes.sql`
**Adds**: Advanced statistics and note features

### Migration 5: Aggregate Stats
**File**: `supabase/migrations/20260201000004_add_aggregate_stats_jsonb.sql`
**Adds**: JSONB columns for flexible aggregate statistics

---

## 🔄 How to Run Each Migration

For each migration file:

1. **Open the file** (in this directory: `/opt/pokerhud/pokerhud/supabase/migrations/`)
2. **Copy the entire contents**
3. **Go to SQL Editor**: https://supabase.com/dashboard/project/ctwrdkipxuztjjbkbhqk/sql/new
4. **Paste** the SQL
5. **Click "Run"** (bottom-right button)
6. **Wait for success** message (green checkmark)
7. **Repeat** for next migration

---

## ✅ STEP 3: Verify Migrations

After running all 5 migrations, verify they worked:

### Quick Check
Run this in SQL Editor:
```sql
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public'
ORDER BY table_name;
```

**Expected output** (8 tables):
- games
- hands
- import_logs
- player_aliases
- player_notes
- player_stats
- unified_players
- users

### Check RLS
Run this:
```sql
SELECT tablename, rowsecurity 
FROM pg_tables 
WHERE schemaname = 'public' AND rowsecurity = true;
```

**Expected**: All 8 tables should show `rowsecurity = true`

---

## 🎯 Quick Command to Read Migration Files

From this directory (`/opt/pokerhud/pokerhud/`):

```bash
# View migration 1
cat supabase/migrations/20260201000000_initial_schema.sql

# View migration 2
cat supabase/migrations/20260201000001_enable_rls.sql

# View migration 3
cat supabase/migrations/20260201000002_add_ai_analysis.sql

# View migration 4
cat supabase/migrations/20260201000003_enhanced_stats_and_notes.sql

# View migration 5
cat supabase/migrations/20260201000004_add_aggregate_stats_jsonb.sql
```

---

## 🆘 Troubleshooting

### Error: "relation already exists"
**Solution**: Tables already created. Either:
- Skip to next migration
- Or run: `DROP TABLE table_name CASCADE;` and re-run

### Error: "permission denied"
**Solution**: Make sure you're logged into the correct Supabase account

### Error: "syntax error"
**Solution**: Make sure you copied the entire file contents

---

## 🎉 When Complete

After all migrations run successfully:

1. ✅ Extension can store player stats
2. ✅ Extension can track hands
3. ✅ Extension can use AI analysis
4. ✅ Data is private (RLS enabled)

Test the connection by loading the extension in Chrome!

---

## 📦 Supabase Credentials (for extension)

These are already in the code:
- **URL**: `https://ctwrdkipxuztjjbkbhqk.supabase.co`
- **Anon Key**: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...` (in apply-migrations.js)

No additional configuration needed - the extension will connect automatically!
