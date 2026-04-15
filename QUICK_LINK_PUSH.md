# Quick: Link & Push Supabase Migrations

## Step 1: Get Access Token (30 seconds)

**Go to:** https://supabase.com/dashboard/account/tokens

- Click **"Generate new token"**
- Name: `pokerhud`
- Copy the token (starts with `sbp_...`)

---

## Step 2: Run Commands (30 seconds)

### Option A: Use the Script (EASIEST)

```bash
bash /opt/pokerhud/RUN_MIGRATION.sh sbp_your_token_here
```

### Option B: Manual Commands

```bash
cd /opt/pokerhud

# Link (replace YOUR_TOKEN)
npx supabase link --project-ref kzqrdtagpykoylhuqcyv --token sbp_YOUR_TOKEN

# Push migrations
npx supabase db push
```

---

## ✅ What Gets Created

**Tables:**
- `tournaments` - Tournament listings
- `tournament_results` - Final standings
- `promotions` - CMS promotional data
- `cash_tables` - Lobby snapshots
- `scrape_runs` - Scrape audit log

**Enums:**
- tournament_type
- tournament_status
- game_variant

**Sample Data:**
- Sunday Slam R200k
- Satellite data

---

## 🎯 Verify

After pushing, check your tables:
```
https://supabase.com/dashboard/project/kzqrdtagpykoylhuqcyv/editor
```

---

**Go get your token and run the script!** 🚀
