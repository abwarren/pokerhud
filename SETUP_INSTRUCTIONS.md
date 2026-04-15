# PokerBet HUD Setup Guide

**Date:** 2026-04-13  
**Location:** `/opt/pokerhud/pokerhud`  
**Time:** 10 minutes

---

## 🎯 What You're Setting Up

A Chrome extension that shows live poker stats (VPIP, PFR, 3-Bet, etc.) overlaid on PokerBet tables.

---

## Part 1: Database Setup (5 minutes)

### Option A: Manual (Supabase Dashboard)

1. **Open Supabase SQL Editor:**
   ```
   https://supabase.com/dashboard/project/ctwrdkipxuztjjbkbhqk/sql/new
   ```

2. **Run these 3 migration files in order:**
   
   **First:** `supabase/migrations/20260201000000_initial_schema.sql`
   - Click **+ New query**
   - Open the file in a text editor
   - Copy ALL content (242 lines)
   - Paste into SQL Editor
   - Click **RUN** button (bottom right)
   - Wait for "Success. No rows returned"

   **Second:** `supabase/migrations/20260201000001_enable_rls.sql`
   - Click **+ New query** again
   - Copy/paste this file
   - Click **RUN**

   **Third:** `supabase/migrations/20260201000002_add_ai_analysis.sql`
   - Click **+ New query** again
   - Copy/paste this file
   - Click **RUN**

3. **Verify it worked:**
   ```bash
   cd /opt/pokerhud/pokerhud
   node check-migrations.js
   ```
   Should show: "✅ All 8 tables exist"

### Option B: Automated (if you have Supabase CLI)

```bash
cd /opt/pokerhud/pokerhud
supabase db push
```

---

## Part 2: Load Chrome Extension (2 minutes)

1. **Open Chrome Extensions Page:**
   - Type in address bar: `chrome://extensions/`
   - Press Enter

2. **Enable Developer Mode:**
   - Look for toggle switch in top-right corner
   - Click it to turn ON (should turn blue)

3. **Load the Extension:**
   - Click **Load unpacked** button (top-left)
   - Navigate to: `/opt/pokerhud/pokerhud/extension/dist/`
   - Click **Select Folder**

4. **You should see:**
   - Extension appears in list: "PokerBet HUD v1.0.0"
   - Extension icon in Chrome toolbar (puzzle piece icon)

---

## Part 3: Test It (3 minutes)

1. **Login to Extension:**
   - Click extension icon in toolbar
   - Enter password: `aksuited`
   - Click **Login**

2. **Visit PokerBet:**
   ```
   https://poker-web.pokerbet.co.za/18751019/
   ```

3. **What You Should See:**
   - Bottom-right corner: Green badge saying "HUD Active"
   - Console logs: "[POKERBET]" with table data
   - (Stats won't show until you play hands to collect data)

---

## 🔧 Troubleshooting

### "Error creating user" in extension popup
- **Cause:** Supabase migrations not applied
- **Fix:** Go back to Part 1

### Extension not appearing in Chrome
- **Cause:** Wrong folder selected
- **Fix:** Make sure you selected `/extension/dist/` not just `/extension/`

### "HUD Loading..." stays gray
- **Cause:** Not logged in
- **Fix:** Click extension icon and enter password `aksuited`

### No data showing on PokerBet
- **Cause:** Need to play hands to collect stats
- **Fix:** This is normal - stats accumulate as you play

### Console shows "iframe not ready"
- **Cause:** PokerBet loads game in iframe, may take a moment
- **Fix:** Wait 5-10 seconds for table to load

---

## 📂 Quick Reference

**Extension Location:** `/opt/pokerhud/pokerhud/extension/dist/`  
**Migration Files:** `/opt/pokerhud/pokerhud/supabase/migrations/`  
**Password:** `aksuited`  
**Test URL:** https://poker-web.pokerbet.co.za/18751019/

---

## ✅ Success Checklist

- [ ] Ran all 3 Supabase migrations
- [ ] Verified with `node check-migrations.js`
- [ ] Loaded extension in Chrome (Developer mode ON)
- [ ] Logged in with password `aksuited`
- [ ] Visited PokerBet URL
- [ ] See green "HUD Active" badge

---

**Once complete, the HUD will start tracking stats as you play!** 🎯
