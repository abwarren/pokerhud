# PokerBet HUD - Final Setup Steps

**Date:** 2026-04-13  
**Time Required:** 5 minutes

---

## ✅ What's Ready

- ✅ Extension built and ready: `/opt/pokerhud/pokerhud/extension/dist/`
- ✅ Supabase project linked: `kzqrdtagpykoylhuqcyv`
- ✅ Migrations consolidated into single file
- ✅ Configuration updated for your project

---

## 🎯 Step 1: Apply Database Migration (2 minutes)

### Option A: Run Consolidated Migration (EASIEST)

1. **Open Supabase SQL Editor:**
   ```
   https://supabase.com/dashboard/project/kzqrdtagpykoylhuqcyv/sql/new
   ```

2. **Copy this file:**
   ```bash
   /opt/pokerhud/pokerhud/supabase/migrations/consolidated_migration.sql
   ```

3. **In SQL Editor:**
   - Click **+ New query**
   - Paste the entire file content
   - Click **RUN** button (bottom right)
   - Wait for "Success" message

### Option B: Run Individual Migrations

Run these 3 files in order (same SQL Editor):
1. `20260201000000_initial_schema.sql`
2. `20260201000001_enable_rls.sql`
3. `20260201000002_add_ai_analysis.sql`

---

## 🎯 Step 2: Get Supabase Anon Key (1 minute)

1. **Go to API Settings:**
   ```
   https://supabase.com/dashboard/project/kzqrdtagpykoylhuqcyv/settings/api
   ```

2. **Copy the "anon / public" key** (starts with `eyJ...`)

3. **Update the code:**
   ```bash
   cd /opt/pokerhud/pokerhud
   
   # Replace YOUR_KEY with the actual key you copied
   sed -i 's|YOUR_ANON_KEY_HERE|eyJhbGc...|g' shared/utils/supabase.ts
   sed -i 's|YOUR_ANON_KEY_HERE|eyJhbGc...|g' check-migrations.js
   ```

---

## 🎯 Step 3: Rebuild Extension (1 minute)

```bash
cd /opt/pokerhud/pokerhud
npm run build:extension
```

---

## 🎯 Step 4: Verify Database (30 seconds)

```bash
cd /opt/pokerhud/pokerhud
node check-migrations.js
```

Should show: "✅ Supabase connection successful!"

---

## 🎯 Step 5: Load in Chrome (1 minute)

**On your local machine (where Chrome runs):**

1. **Copy extension to local:**
   ```bash
   scp -r ubuntu@YOUR_IP:/opt/pokerhud/pokerhud/extension/dist ~/Desktop/pokerbet-hud
   ```

2. **In Chrome:**
   - Go to: `chrome://extensions/`
   - Toggle "Developer mode" ON (top-right)
   - Click "Load unpacked"
   - Select `~/Desktop/pokerbet-hud` folder

3. **Test:**
   - Click extension icon
   - Enter password: `aksuited`
   - Visit: https://poker-web.pokerbet.co.za/18751019/
   - See green "HUD Active" badge

---

## 📋 Quick Commands Reference

```bash
# Navigate to project
cd /opt/pokerhud/pokerhud

# Update Supabase key
sed -i 's|YOUR_ANON_KEY_HERE|YOUR_KEY|g' shared/utils/supabase.ts

# Rebuild
npm run build:extension

# Verify database
node check-migrations.js

# Copy to local (replace IP)
scp -r ubuntu@52.16.14.220:/opt/pokerhud/pokerhud/extension/dist ~/Desktop/pokerbet-hud
```

---

## 🚀 You're Almost Done!

1. ⬜ Run SQL migration in Supabase dashboard
2. ⬜ Get anon key and update code
3. ⬜ Rebuild extension
4. ⬜ Load in Chrome
5. ⬜ Test on PokerBet

**Total time: 5 minutes** 🎯
