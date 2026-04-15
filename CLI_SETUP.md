# Supabase CLI Setup - Get Access Token

## Step 1: Get Your Access Token

1. **Go to:** https://supabase.com/dashboard/account/tokens

2. **Click:** "Generate new token"

3. **Name it:** "pokerhud-cli"

4. **Copy the token** (starts with `sbp_...`)

---

## Step 2: Set the Token

```bash
export SUPABASE_ACCESS_TOKEN="sbp_your_token_here"
```

---

## Step 3: Link and Push

```bash
cd /home/warrenabrahams

# Link to your project
/usr/local/bin/supabase-cli link --project-ref kzqrdtagpykoylhuqcyv

# Push migrations
/usr/local/bin/supabase-cli db push
```

---

## ✅ What This Does

- Creates all 8 database tables
- Sets up Row Level Security (RLS)
- Adds AI analysis functions
- Configures indexes and constraints

---

## Files Ready

- Migration: `supabase/migrations/20260413000000_initial_setup.sql`
- Tables: users, games, hands, unified_players, player_aliases, player_stats, player_notes, import_logs

---

**Next:** Once pushed, update the anon key and rebuild the extension.
