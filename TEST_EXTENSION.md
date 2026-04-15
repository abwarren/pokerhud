# Test PokerBet HUD Extension - Scraper Pipeline

## 🎯 Goal: Validate Data Extraction

Skip database/MCP. Focus only on: **Chrome Extension → JSON → Console**

---

## Step 1: Start Test Server (30 seconds)

**In a terminal, run:**
```bash
cd /opt/pokerhud
python3 test_server.py
```

**You should see:**
```
PokerBet HUD Test Server
Listening on: http://127.0.0.1:8888
```

**Leave this running!**

---

## Step 2: Load Extension (1 minute)

1. **Open Chrome:** `chrome://extensions/`
2. **Toggle "Developer mode" ON** (top-right)
3. **Click "Load unpacked"**
4. **Select:** `/opt/pokerhud/pokerhud/extension/dist/`

**You should see:** "PokerBet HUD" extension loaded

---

## Step 3: Open PokerBet Table (30 seconds)

**Visit:**
```
https://poker-web.pokerbet.co.za/18751019/
```

**Or any PokerBet table URL**

---

## Step 4: Check Console Logs (30 seconds)

**Open Chrome DevTools:**
- Press `F12` or `Ctrl+Shift+I`
- Go to **Console** tab

**Look for:**
```
[PokerBet] scraper loaded
[POKERBET] { site: "pokerbet", url: "...", ... }
```

**Should appear every ~2 seconds**

---

## Step 5: Check Test Server (30 seconds)

**In the terminal running test_server.py, you should see:**
```
=== SNAPSHOT RECEIVED ===
Timestamp: ...
Site: pokerbet
URL: https://poker-web.pokerbet.co.za/...

Table:
  Player Count: 9
  Dealer Position: 3
  Pot: R150

Players: 5
  - Pos 0: PlayerName (R5000)
  ...

Board Cards: 3
  - Th
  - Jc
  - 5d

--- RAW JSON ---
{
  "site": "pokerbet",
  "ts": 1776084123456,
  ...
}
```

---

## ✅ Success Criteria

**You should see ALL of these:**

1. ✅ Extension loaded (chrome://extensions)
2. ✅ Console logs `[POKERBET]` every ~2s
3. ✅ Test server receives POST requests
4. ✅ JSON contains:
   - `table.playerCount`
   - `table.dealerPosition`
   - `players[].position`
   - `players[].name`
   - `players[].stack`
   - `board.cards[]`

---

## 🚨 Troubleshooting

### No console logs?
→ Extension not injected
→ Check manifest matches `pokerbet.co.za`
→ Reload extension and refresh page

### No server logs?
→ background.js not sending
→ Check port 8888 running: `curl http://127.0.0.1:8888/api/health`
→ Check Chrome DevTools → Network tab for failed requests

### Empty data?
→ Selectors need refinement (expected on first pass)
→ PokerBet HTML structure may have changed
→ Iframe not loading

---

## 📋 Next Step

**Once you see snapshots arriving, copy ONE complete JSON snapshot here.**

I will:
- ✅ Decode card format properly
- ✅ Map to HUD schema
- ✅ Build VPIP/PFR calculator
- ✅ Wire up stat tracking

---

## 🎯 Build Order (Correct)

1. ✅ **Scraper works** ← WE ARE HERE
2. ⏳ JSON stable
3. ⏳ Parser works
4. ⏳ Stats calculate
5. ⏳ HUD renders
6. ⏳ DB stores (optional)
7. ⏳ MCP (optional)

---

**Start test_server.py now and load the extension!** 🚀
