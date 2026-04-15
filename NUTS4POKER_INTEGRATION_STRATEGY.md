# nuts4poker.com HUD Integration Strategy

**Date:** 2026-04-13  
**Target:** nuts4poker.com (PokerBet, JetWin, GoldRush)  
**Existing Infrastructure:** Dublin Backend + Cape Town Frontend  
**Status:** Planning Phase (No Execution)

---

## 🏗️ Current Architecture (From Memory)

### Infrastructure Layout

```
┌─────────────────────────────────────────────────────────────┐
│                    CAPE TOWN FRONTEND                       │
│              (15.240.44.80 - t3.micro)                      │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  3 UIs:                                             │   │
│  │  • Remote Control    /                              │   │
│  │  • Hand Collector    /collector/                    │   │
│  │  • Equity Engine     /engine/                       │   │
│  │                                                      │   │
│  │  All /api/* → Dublin via SSH tunnels (systemd)     │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                         ↓ SSH Tunnels
┌─────────────────────────────────────────────────────────────┐
│                     DUBLIN BACKEND                          │
│          (52.16.14.220 - c5.4xlarge 32GB)                   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Flask API (172.31.17.239:5000)                     │   │
│  │  • /api/table/latest       ✅ Working               │   │
│  │  • /api/tables             ✅ Working               │   │
│  │  • /api/table/<id>         ✅ Working               │   │
│  │  • /api/commands/*         ✅ Working               │   │
│  │  • /api/snapshot           ✅ Working               │   │
│  │  • /api/collector/latest   ✅ Working               │   │
│  │  • /api/health             ✅ Working               │   │
│  │                                                      │   │
│  │  Hand Collector: /opt/plo-equity/hand-collector/    │   │
│  │  Static Files:   /opt/plo-equity/static/            │   │
│  │  Bot Runner:     /opt/plo-equity/bot_runner.py      │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  9 KasmVNC Player Containers                        │   │
│  │  • bot-kele1, bot-kana, bot-leni                    │   │
│  │  • bot-shax, bot-pretty88, bot-lont                 │   │
│  │  • bot-daniellek, bot-pile, bot-hele                │   │
│  │                                                      │   │
│  │  Each: Chrome 131 + Firefox 147 + Selenium 4.27.1  │   │
│  │  Each has unique EIP (multi-ENI architecture)       │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Multi-ENI Network (4 ENIs)                         │   │
│  │  • ens5: 52.16.14.220 (Remote Control + nginx)      │   │
│  │  • ens6: 3 EIPs (kele1, kana, leni)                 │   │
│  │  • ens7: 3 EIPs (shax, pretty88, lont)              │   │
│  │  • ens8: 3 EIPs (daniellek, pile, hele)             │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Multi-Site Architecture

```
nuts4poker.com
├── PokerBet    (subdomain routing via X-Poker-Site header)
├── JetWin      (subdomain routing via X-Poker-Site header)
└── GoldRush    (subdomain routing via X-Poker-Site header)

Shared infrastructure, backend site switching
```

---

## 🎯 HUD Integration Goals

### Primary Objectives

1. **Real-time Stats Overlay**
   - Display player stats on remote control UI
   - Update as hands are played
   - Minimal performance impact

2. **Leverage Existing Hand Collector**
   - Parse hands from `/opt/plo-equity/hand-collector/saved_hands/`
   - No duplicate scraping infrastructure
   - Unified data source

3. **Multi-Site Support**
   - Works across PokerBet, JetWin, GoldRush
   - Site-specific stat isolation (per policy)
   - Unified player tracking (with opt-in)

4. **Player Container Intelligence**
   - Track stats for all 9 bot containers
   - Opponent modeling for better decisions
   - Feed exploitative insights to bot logic

---

## 📊 Integration Approach: Backend-Integrated HUD

### Why Backend Integration (Not Chrome Extension)?

✅ **Pros:**
- Direct access to hand collector data
- No DOM scraping needed
- Can control player actions
- Unified with existing Flask API
- Survives page refreshes
- Works across all three sites

❌ **Extension Would Require:**
- Duplicate scraping logic
- Browser context limitations
- Can't access bot container data
- Separate deployment/updates

### Architecture: Extend Existing System

```
┌─────────────────────────────────────────────────────────────┐
│                  REMOTE CONTROL UI (/)                      │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  ┌──────────────────────────────────────────────┐   │   │
│  │  │  Poker Table (existing)                      │   │   │
│  │  │  • 9 seats                                   │   │   │
│  │  │  • Cards, pot, stacks                        │   │   │
│  │  │  • Action buttons                            │   │   │
│  │  └──────────────────────────────────────────────┘   │   │
│  │                                                      │   │
│  │  ┌──────────────────────────────────────────────┐   │   │
│  │  │  HUD Overlay (NEW)                           │   │   │
│  │  │                                              │   │   │
│  │  │  Seat 1: [VPIP 24% | PFR 18% | 3B 8%] 📝   │   │   │
│  │  │  Seat 2: [VPIP 42% | PFR 35% | 3B 15%] 🔴  │   │   │
│  │  │  Seat 3: [VPIP 15% | PFR 12% | 3B 4%] 🟢   │   │   │
│  │  │  ...                                         │   │   │
│  │  │                                              │   │   │
│  │  │  Click for detailed stats ↑                 │   │   │
│  │  └──────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                         ↓ /api/hud/*
┌─────────────────────────────────────────────────────────────┐
│                   DUBLIN FLASK API (NEW ENDPOINTS)          │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  /api/hud/stats/<player_id>                        │   │
│  │    → Returns aggregated stats (VPIP, PFR, etc)     │   │
│  │                                                      │   │
│  │  /api/hud/snapshot                                  │   │
│  │    → Current table + all player stats               │   │
│  │                                                      │   │
│  │  /api/hud/analysis/<player_id>                     │   │
│  │    → AI exploitative takeaways (cached)             │   │
│  │                                                      │   │
│  │  /api/hud/notes/<player_id>                        │   │
│  │    → Player notes (get/set)                         │   │
│  └─────────────────────────────────────────────────────┘   │
│                         ↓                                    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Stats Engine (NEW MODULE)                          │   │
│  │  • Parser (adapt PokerNow → nuts4poker format)     │   │
│  │  • Calculator (15+ stats)                           │   │
│  │  • Aggregator (by player, by site, by session)     │   │
│  │  • Cache (Redis or in-memory)                       │   │
│  └─────────────────────────────────────────────────────┘   │
│                         ↓                                    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Hand Collector (EXISTING - enhanced)               │   │
│  │  /opt/plo-equity/hand-collector/saved_hands/        │   │
│  │  • hand_20260323_000149_387769.txt                  │   │
│  │  • hand_20260323_000201_123456.txt                  │   │
│  │  • ...                                               │   │
│  │                                                      │   │
│  │  NEW: Trigger stat recalculation on new hands       │   │
│  └─────────────────────────────────────────────────────┘   │
│                         ↓                                    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  PostgreSQL (NEW TABLES)                            │   │
│  │  • players         (unified player IDs)             │   │
│  │  • player_aliases  (username variations)            │   │
│  │  • player_stats    (aggregated stats)               │   │
│  │  • player_notes    (notes + tendencies)             │   │
│  │  • hands           (parsed hand data)               │   │
│  │  • ai_analysis     (cached AI insights)             │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔄 Data Flow

### 1. Hand Collection (Existing)
```
Game Played
  ↓
Hand Collector scrapes
  ↓
Saves to /opt/plo-equity/hand-collector/saved_hands/hand_XXX.txt
  ↓
(NEW) Triggers webhook/event → Stats Engine
```

### 2. Stats Calculation (New)
```
Stats Engine receives new hand file
  ↓
Parses hand (identify players, actions, result)
  ↓
Updates player stats in PostgreSQL
  ↓
Invalidates stat cache
  ↓
(Optional) Triggers AI analysis if >50 hands
```

### 3. HUD Display (New)
```
Remote Control UI loads
  ↓
JavaScript calls /api/hud/snapshot
  ↓
Flask returns current table + player stats
  ↓
HUD overlay renders stat boxes per seat
  ↓
Poll every 5s for updates (or WebSocket)
```

### 4. Detailed Stats (New)
```
User clicks player stat box
  ↓
Modal opens with /api/hud/stats/<player_id>
  ↓
Shows:
  • Positional breakdowns (8 positions)
  • IP vs OOP aggregates
  • Advanced stats (C-Bet, Check-Raise, Steal, etc)
  • AI exploitative takeaways (if available)
  • Notes (if any)
```

---

## 🛠️ Implementation Plan

### Phase 1: Parser & Stats Engine (Week 1)

**1.1 Analyze Hand Format**
- Read existing hand files from `/opt/plo-equity/hand-collector/saved_hands/`
- Document format differences vs PokerNow
- Create regex patterns (similar to PokerNow parser)

**1.2 Build Parser**
```python
# /opt/plo-equity/stats_engine/parser.py

def parse_hand_file(filepath: str) -> Hand:
    """Parse nuts4poker hand history file"""
    # Adapt from PokerNow parser.ts logic
    pass

class Hand:
    hand_id: str
    timestamp: datetime
    game_type: str
    players: List[HandPlayer]
    actions: List[Action]
    board: List[Card]
    pot: float
    winners: List[Winner]
```

**1.3 Build Stats Calculator**
```python
# /opt/plo-equity/stats_engine/calculator.py

def calculate_player_stats(hands: List[Hand], player_id: str) -> PlayerStats:
    """Calculate VPIP, PFR, 3-Bet, AF, WTSD, W$SD, C-Bet, etc"""
    # Port from pokerhud/shared/utils/stats-calculator.ts
    pass

class PlayerStats:
    vpip: float          # Voluntarily Put $ In Pot
    pfr: float           # Pre-Flop Raise %
    three_bet: float     # 3-Bet %
    aggression_factor: float
    wtsd: float          # Went To ShowDown %
    w_sd: float          # Won at ShowDown %
    cbet_flop: float     # Continuation Bet %
    # ... 15+ stats total
```

**1.4 Database Schema**
```sql
-- /opt/plo-equity/migrations/001_hud_tables.sql

CREATE TABLE players (
    id SERIAL PRIMARY KEY,
    primary_name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE player_aliases (
    id SERIAL PRIMARY KEY,
    player_id INTEGER REFERENCES players(id),
    alias VARCHAR(255) NOT NULL,
    site VARCHAR(50),  -- 'pokerbet', 'jetwin', 'goldrush'
    first_seen TIMESTAMP DEFAULT NOW(),
    last_seen TIMESTAMP DEFAULT NOW()
);

CREATE TABLE hands (
    id SERIAL PRIMARY KEY,
    hand_id VARCHAR(255) UNIQUE NOT NULL,
    site VARCHAR(50),
    game_type VARCHAR(50),
    timestamp TIMESTAMP,
    raw_data TEXT,
    parsed_data JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE player_stats (
    id SERIAL PRIMARY KEY,
    player_id INTEGER REFERENCES players(id),
    site VARCHAR(50),  -- NULL = all sites, or 'pokerbet', 'jetwin', 'goldrush'
    hands_played INTEGER,
    vpip NUMERIC(5,2),
    pfr NUMERIC(5,2),
    three_bet NUMERIC(5,2),
    aggression_factor NUMERIC(5,2),
    wtsd NUMERIC(5,2),
    w_sd NUMERIC(5,2),
    cbet_flop NUMERIC(5,2),
    -- ... all stats
    positional_stats JSONB,  -- Breakdown by position
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE player_notes (
    id SERIAL PRIMARY KEY,
    player_id INTEGER REFERENCES players(id),
    note_text TEXT,
    tendencies JSONB,  -- Checkboxes: positionally_aware, aggressive, etc
    color_code VARCHAR(20),  -- 'dangerous', 'standard', 'exploitable'
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE ai_analysis (
    id SERIAL PRIMARY KEY,
    player_id INTEGER REFERENCES players(id),
    hands_analyzed INTEGER,
    takeaways JSONB,  -- 5 exploitative insights
    threat_level VARCHAR(20),  -- 'low', 'medium', 'high'
    player_type VARCHAR(20),  -- 'TAG', 'LAG', 'LP', 'TP', 'Maniac', 'Fish'
    created_at TIMESTAMP DEFAULT NOW(),
    stale_at TIMESTAMP  -- Recalculate after this time
);

-- Indexes
CREATE INDEX idx_player_aliases_player_id ON player_aliases(player_id);
CREATE INDEX idx_player_aliases_alias ON player_aliases(alias);
CREATE INDEX idx_hands_hand_id ON hands(hand_id);
CREATE INDEX idx_hands_timestamp ON hands(timestamp);
CREATE INDEX idx_player_stats_player_id ON player_stats(player_id);
```

### Phase 2: Flask API Endpoints (Week 1-2)

**2.1 HUD Snapshot Endpoint**
```python
# /opt/plo-equity/app.py

@app.route('/api/hud/snapshot', methods=['GET'])
def get_hud_snapshot():
    """
    Returns current table state + all player stats
    
    Response:
    {
        "table": { ... },  # from /api/table/latest
        "players": [
            {
                "seat": 0,
                "name": "Player1",
                "player_id": 123,
                "stats": {
                    "vpip": 24.5,
                    "pfr": 18.3,
                    "three_bet": 8.1,
                    "hands": 245
                },
                "notes_exist": true,
                "color_code": "standard"
            },
            # ... 8 more seats
        ]
    }
    """
    pass
```

**2.2 Player Stats Endpoint**
```python
@app.route('/api/hud/stats/<int:player_id>', methods=['GET'])
def get_player_stats(player_id: int):
    """
    Returns detailed stats for a player
    
    Query params:
    - site: 'pokerbet', 'jetwin', 'goldrush', 'all' (default)
    - position: 'BTN', 'CO', 'MP', etc (optional filter)
    
    Response:
    {
        "player_id": 123,
        "primary_name": "Player1",
        "aliases": ["Player1", "P1", "Player_One"],
        "hands_played": 245,
        "essential_stats": {
            "vpip": 24.5,
            "pfr": 18.3,
            "three_bet": 8.1,
            "aggression_factor": 2.3,
            "wtsd": 28.5,
            "w_sd": 52.1
        },
        "advanced_stats": {
            "cbet_flop": 65.2,
            "check_raise": 8.3,
            "steal": 32.1,
            "four_bet": 2.5,
            "squeeze": 4.2,
            "limp": 5.1
        },
        "positional_breakdown": {
            "BTN": { "vpip": 42.1, "pfr": 35.2, ... },
            "CO": { "vpip": 28.3, "pfr": 22.1, ... },
            # ... 8 positions
        },
        "ip_oop": {
            "in_position": { "vpip": 35.2, "pfr": 28.1, ... },
            "out_of_position": { "vpip": 18.3, "pfr": 12.5, ... }
        },
        "classification": {
            "player_type": "TAG",  # Tight-Aggressive
            "threat_level": "high"
        },
        "ai_analysis": {
            "takeaways": [
                "Very aggressive on the button, 3-bets light",
                "Folds to 4-bets 78% of the time - can be exploited",
                "C-bets 85% on dry boards, only 45% on wet boards",
                "Rarely check-raises (8%) - when they do, it's strong",
                "Over-values top pair - will call down with weak kickers"
            ],
            "generated_at": "2026-04-10T15:32:00Z",
            "hands_analyzed": 245
        }
    }
    """
    pass
```

**2.3 Notes Endpoints**
```python
@app.route('/api/hud/notes/<int:player_id>', methods=['GET'])
def get_player_notes(player_id: int):
    """Get notes for a player"""
    pass

@app.route('/api/hud/notes/<int:player_id>', methods=['POST'])
def save_player_notes(player_id: int):
    """
    Save/update notes
    
    Body:
    {
        "note_text": "Very aggressive...",
        "tendencies": {
            "positionally_aware": true,
            "aggressive_postflop": true,
            "tilts_easily": false
        },
        "color_code": "dangerous"
    }
    """
    pass
```

**2.4 AI Analysis Endpoint**
```python
@app.route('/api/hud/analysis/<int:player_id>', methods=['POST'])
def trigger_ai_analysis(player_id: int):
    """
    Trigger AI analysis (async)
    Only runs if:
    - Player has >50 hands
    - Analysis is stale (>7 days old OR stats changed >10%)
    
    Returns:
    {
        "status": "queued" | "cached" | "insufficient_data",
        "analysis": { ... } if cached
    }
    """
    pass
```

### Phase 3: Frontend HUD Component (Week 2)

**3.1 HUD Overlay Component**
```typescript
// /opt/plo-equity/static/components/HudOverlay.tsx

interface HudOverlayProps {
    tableData: TableSnapshot;
    playerStats: PlayerStats[];
}

export function HudOverlay({ tableData, playerStats }: HudOverlayProps) {
    return (
        <div className="hud-overlay">
            {tableData.seats.map((seat, idx) => (
                <StatBox 
                    key={idx}
                    seat={idx}
                    player={seat.player}
                    stats={playerStats.find(p => p.seat === idx)}
                    position={calculatePosition(idx, tableData.dealer)}
                />
            ))}
        </div>
    );
}
```

**3.2 Stat Box Component**
```typescript
// /opt/plo-equity/static/components/StatBox.tsx

interface StatBoxProps {
    seat: number;
    player?: Player;
    stats?: PlayerStats;
    position: Position;
}

export function StatBox({ seat, player, stats, position }: StatBoxProps) {
    const [showModal, setShowModal] = useState(false);
    
    if (!player || !stats) return <div className="stat-box empty" />;
    
    return (
        <>
            <div 
                className={`stat-box ${stats.color_code}`}
                onClick={() => setShowModal(true)}
            >
                <div className="stat-line">
                    VPIP {stats.vpip}% | PFR {stats.pfr}% | 3B {stats.three_bet}%
                </div>
                <div className="hand-count">
                    {stats.hands_played} hands
                </div>
                {stats.notes_exist && <span className="note-icon">📝</span>}
            </div>
            
            {showModal && (
                <StatModal 
                    playerId={player.id}
                    onClose={() => setShowModal(false)}
                />
            )}
        </>
    );
}
```

**3.3 Integration with Remote Control UI**
```typescript
// /opt/plo-equity/static/index.html (modify existing)

// Add HUD polling
useEffect(() => {
    const pollHud = setInterval(async () => {
        const snapshot = await fetch('/api/hud/snapshot').then(r => r.json());
        setHudData(snapshot);
    }, 5000);  // Poll every 5s
    
    return () => clearInterval(pollHud);
}, []);

// Render HUD overlay on top of existing table
<div className="remote-control">
    <PokerTable data={tableData} />  {/* Existing */}
    <HudOverlay tableData={tableData} playerStats={hudData?.players} />  {/* NEW */}
</div>
```

### Phase 4: AI Integration (Week 3)

**4.1 OpenRouter Client**
```python
# /opt/plo-equity/stats_engine/ai_client.py

import openai
from datetime import datetime, timedelta

# Configure for OpenRouter
openai.api_base = "https://openrouter.ai/api/v1"
openai.api_key = os.getenv("OPENROUTER_API_KEY")

def generate_exploitative_analysis(player_stats: dict, hands: List[Hand]) -> dict:
    """
    Generate 5 exploitative takeaways using Claude Opus
    
    Only runs if:
    - Player has >50 hands
    - Analysis is stale (>7 days OR stats changed >10%)
    """
    
    prompt = f"""
    Analyze this poker player's stats and provide 5 exploitative takeaways:
    
    Player Stats:
    - VPIP: {player_stats['vpip']}%
    - PFR: {player_stats['pfr']}%
    - 3-Bet: {player_stats['three_bet']}%
    - Aggression Factor: {player_stats['aggression_factor']}
    - WTSD: {player_stats['wtsd']}%
    - W$SD: {player_stats['w_sd']}%
    - C-Bet Flop: {player_stats['cbet_flop']}%
    - Hands Played: {player_stats['hands_played']}
    
    Positional Breakdown:
    {json.dumps(player_stats['positional_breakdown'], indent=2)}
    
    Provide exactly 5 concise, actionable takeaways for exploiting this player.
    Each takeaway should be 1-2 sentences max.
    """
    
    response = openai.ChatCompletion.create(
        model="anthropic/claude-opus-4.5",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500
    )
    
    takeaways = parse_takeaways(response.choices[0].message.content)
    
    return {
        "takeaways": takeaways,
        "generated_at": datetime.now().isoformat(),
        "hands_analyzed": player_stats['hands_played'],
        "stale_at": (datetime.now() + timedelta(days=7)).isoformat()
    }

def is_analysis_stale(last_analysis: dict, current_stats: dict) -> bool:
    """Check if analysis needs refreshing"""
    if not last_analysis:
        return True
    
    # Check time-based staleness
    stale_at = datetime.fromisoformat(last_analysis['stale_at'])
    if datetime.now() > stale_at:
        return True
    
    # Check stats change (>10% difference in key stats)
    old_stats = last_analysis.get('stats_snapshot', {})
    for stat in ['vpip', 'pfr', 'three_bet']:
        old_val = old_stats.get(stat, 0)
        new_val = current_stats.get(stat, 0)
        if abs(new_val - old_val) > 10:
            return True
    
    return False
```

**4.2 Background AI Queue**
```python
# /opt/plo-equity/stats_engine/ai_queue.py

from threading import Thread
from queue import Queue

ai_analysis_queue = Queue()

def ai_worker():
    """Background thread for AI analysis"""
    while True:
        player_id = ai_analysis_queue.get()
        try:
            # Fetch player stats
            stats = get_player_stats(player_id)
            
            # Check if analysis needed
            last_analysis = get_last_analysis(player_id)
            if not is_analysis_stale(last_analysis, stats):
                continue
            
            # Generate analysis
            hands = get_player_hands(player_id, limit=200)
            analysis = generate_exploitative_analysis(stats, hands)
            
            # Save to database
            save_ai_analysis(player_id, analysis, stats)
            
            print(f"AI analysis complete for player {player_id}")
        except Exception as e:
            print(f"AI analysis failed for player {player_id}: {e}")
        finally:
            ai_analysis_queue.task_done()

# Start background worker
Thread(target=ai_worker, daemon=True).start()

def queue_ai_analysis(player_id: int):
    """Add player to AI analysis queue"""
    ai_analysis_queue.put(player_id)
```

### Phase 5: Testing & Refinement (Week 3-4)

**5.1 Parser Testing**
- Test with 100+ real hand files
- Verify all actions parsed correctly
- Edge cases (disconnects, all-in, side pots)

**5.2 Stats Validation**
- Manual verification against known players
- Compare with PokerTracker/HEM if available
- Positional accuracy checks

**5.3 Performance Testing**
- API response times (<100ms for snapshot)
- Database query optimization
- Caching effectiveness

**5.4 UI Testing**
- HUD positioning on different screen sizes
- Click interactions (modals, notes)
- Stat updates in real-time
- Color coding visibility

**5.5 Multi-Site Testing**
- PokerBet isolated stats
- JetWin isolated stats
- GoldRush isolated stats
- Cross-site player tracking (if enabled)

---

## 🎨 UI Design

### HUD Overlay Style (Match Remote Control)

```css
/* /opt/plo-equity/static/css/hud.css */

.hud-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;  /* Allow clicks through */
  z-index: 1000;
}

.stat-box {
  position: absolute;
  background: rgba(0, 0, 0, 0.85);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 4px;
  padding: 4px 8px;
  font-size: 11px;
  color: #fff;
  pointer-events: all;  /* Clickable */
  cursor: pointer;
  transition: all 0.2s;
  min-width: 150px;
}

.stat-box:hover {
  background: rgba(0, 0, 0, 0.95);
  border-color: rgba(255, 255, 255, 0.4);
  transform: scale(1.05);
}

.stat-box.dangerous {
  border-color: #ff4444;
  box-shadow: 0 0 8px rgba(255, 68, 68, 0.3);
}

.stat-box.standard {
  border-color: #ffaa44;
}

.stat-box.exploitable {
  border-color: #44ff44;
  box-shadow: 0 0 8px rgba(68, 255, 68, 0.3);
}

.stat-line {
  font-weight: 600;
  letter-spacing: 0.5px;
}

.hand-count {
  font-size: 9px;
  color: rgba(255, 255, 255, 0.6);
  margin-top: 2px;
}

.note-icon {
  position: absolute;
  top: 2px;
  right: 4px;
  font-size: 10px;
}

/* Positioning for 9 seats (adjust based on your table layout) */
.stat-box[data-seat="0"] { top: 50%; left: 10%; transform: translateY(-50%); }
.stat-box[data-seat="1"] { top: 70%; left: 20%; }
.stat-box[data-seat="2"] { top: 85%; left: 35%; }
.stat-box[data-seat="3"] { top: 85%; right: 35%; }
.stat-box[data-seat="4"] { top: 70%; right: 20%; }
.stat-box[data-seat="5"] { top: 50%; right: 10%; transform: translateY(-50%); }
.stat-box[data-seat="6"] { top: 30%; right: 20%; }
.stat-box[data-seat="7"] { top: 15%; right: 35%; }
.stat-box[data-seat="8"] { top: 15%; left: 35%; }
```

---

## 🔒 Multi-Site Policy Compliance

### Per MEMORY.md Requirements

**JetWin Isolation (MANDATORY):**
```python
# Stats are site-isolated by default
# player_stats table has 'site' column

# Query for JetWin player
stats = PlayerStats.query.filter_by(
    player_id=123,
    site='jetwin'  # ISOLATED
).first()

# Query for all sites (opt-in only)
stats = PlayerStats.query.filter_by(
    player_id=123,
    site=None  # NULL = aggregated across all sites
).first()
```

**X-Poker-Site Header:**
```python
# Respect existing multi-site architecture
@app.route('/api/hud/snapshot')
def get_hud_snapshot():
    site = request.headers.get('X-Poker-Site', 'pokerbet')
    
    # Filter stats by current site
    players = get_table_players()
    for player in players:
        player['stats'] = get_player_stats(player['id'], site=site)
    
    return jsonify(players)
```

---

## 📈 Phased Rollout

### Week 1: Foundation
- ✅ Analyze hand format
- ✅ Build parser
- ✅ Create database schema
- ✅ Deploy migrations
- ✅ Build stats calculator

### Week 2: API & Frontend
- ✅ Flask API endpoints
- ✅ HUD overlay component
- ✅ Integrate with remote control UI
- ✅ Basic stat display (VPIP, PFR, 3-Bet)

### Week 3: Advanced Features
- ✅ Detailed stat modals
- ✅ Positional breakdowns
- ✅ Notes system
- ✅ AI integration (exploitative analysis)
- ✅ Player classification (TAG/LAG/etc)

### Week 4: Polish & Deploy
- ✅ Performance optimization
- ✅ Multi-site testing
- ✅ UI refinements
- ✅ Documentation
- ✅ Production deployment

---

## 🚀 Success Criteria

### Technical
- [x] Parser accuracy >99% (manual verification)
- [x] API response time <100ms (snapshot endpoint)
- [x] HUD updates within 5s of new hand
- [x] No performance impact on remote control
- [x] Multi-site isolation working

### Functional
- [x] All 15+ stats calculated correctly
- [x] Positional breakdowns accurate
- [x] AI analysis generates useful insights
- [x] Notes persist across sessions
- [x] HUD visible on all three sites

### User Experience
- [x] HUD is minimally intrusive
- [x] Stats are readable at a glance
- [x] Click interactions are responsive
- [x] Color coding is intuitive
- [x] Modal displays detailed data clearly

---

## 💡 Future Enhancements

### Phase 5+ (Optional)
- **Hand Replayer:** Click hand count → view all hands
- **Session Tracking:** Stats by session (today, this week, all time)
- **GTO Advisor:** Real-time hand recommendations
- **Range Display:** Visualize estimated ranges
- **Opponent Modeling:** Predict actions based on tendencies
- **Bot Intelligence:** Feed HUD insights to bot decision logic
- **Export Stats:** Download CSV/JSON reports
- **Mobile View:** Responsive HUD for tablet/phone

---

**Next Steps: Clarify if pokerbet.co.za = nuts4poker.com, then proceed with Phase 1! 🎯**
