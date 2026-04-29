"""
BLM — Basketball League Manager Database
SQLite backend for tracking Cyber Basketball 2K26 games, bets, and performance.
"""

import sqlite3
import os
import json
from datetime import datetime

BLM_DB_PATH = os.getenv('BLM_DB_PATH', '/opt/plo-w4p/blm.db')

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id         TEXT UNIQUE NOT NULL,
    league          TEXT DEFAULT 'Cyber Basketball 2K26',
    home_team       TEXT NOT NULL,
    away_team       TEXT NOT NULL,
    home_score      INTEGER,
    away_score      INTEGER,
    total_score     INTEGER,
    q1_home         INTEGER,
    q1_away         INTEGER,
    q2_home         INTEGER,
    q2_away         INTEGER,
    q3_home         INTEGER,
    q3_away         INTEGER,
    q4_home         INTEGER,
    q4_away         INTEGER,
    ot_home         INTEGER,
    ot_away         INTEGER,
    status          TEXT DEFAULT 'scheduled' CHECK(status IN ('scheduled','live','final','cancelled')),
    game_date       TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_games_date ON games(game_date);
CREATE INDEX IF NOT EXISTS idx_games_status ON games(status);
CREATE INDEX IF NOT EXISTS idx_games_teams ON games(home_team, away_team);

CREATE TABLE IF NOT EXISTS bets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id         TEXT NOT NULL,
    quarter         TEXT DEFAULT 'FG',
    market_line     REAL NOT NULL,
    fair_line       REAL,
    final_total     REAL,
    gap             REAL,
    z_score         REAL,
    kelly_pct       REAL,
    accuracy        REAL,
    direction       TEXT DEFAULT 'under' CHECK(direction IN ('over','under')),
    stake           REAL DEFAULT 0,
    odds            REAL,
    result          TEXT DEFAULT 'PENDING' CHECK(result IN ('WIN','LOSS','PUSH','PENDING','VOID')),
    profit          REAL DEFAULT 0,
    notes           TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    settled_at      TEXT,
    FOREIGN KEY (game_id) REFERENCES games(game_id)
);
CREATE INDEX IF NOT EXISTS idx_bets_game ON bets(game_id);
CREATE INDEX IF NOT EXISTS idx_bets_result ON bets(result);
CREATE INDEX IF NOT EXISTS idx_bets_date ON bets(created_at);

CREATE TABLE IF NOT EXISTS fair_lines (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id         TEXT NOT NULL,
    quarter         TEXT DEFAULT 'FG',
    fair_line       REAL NOT NULL,
    model_version   TEXT DEFAULT 'v1',
    confidence      REAL,
    factors         TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (game_id) REFERENCES games(game_id)
);
CREATE INDEX IF NOT EXISTS idx_fair_game ON fair_lines(game_id);
"""


def get_db():
    db = sqlite3.connect(BLM_DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def init_db():
    db = get_db()
    db.executescript(SCHEMA)
    db.commit()
    db.close()


# ── Game CRUD ──────────────────────────────────────────────────────────────

def add_game(data):
    db = get_db()
    home_score = data.get('home_score')
    away_score = data.get('away_score')
    total = (home_score or 0) + (away_score or 0) if home_score is not None else None
    status = 'final' if home_score is not None else data.get('status', 'scheduled')

    try:
        db.execute("""
            INSERT INTO games (game_id, league, home_team, away_team,
                home_score, away_score, total_score,
                q1_home, q1_away, q2_home, q2_away,
                q3_home, q3_away, q4_home, q4_away,
                ot_home, ot_away, status, game_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data['game_id'], data.get('league', 'Cyber Basketball 2K26'),
            data['home_team'], data['away_team'],
            home_score, away_score, total,
            data.get('q1_home'), data.get('q1_away'),
            data.get('q2_home'), data.get('q2_away'),
            data.get('q3_home'), data.get('q3_away'),
            data.get('q4_home'), data.get('q4_away'),
            data.get('ot_home'), data.get('ot_away'),
            status, data.get('game_date')
        ))
        db.commit()
        return {'status': 'ok', 'game_id': data['game_id']}
    except sqlite3.IntegrityError:
        # Update existing
        db.execute("""
            UPDATE games SET home_score=?, away_score=?, total_score=?,
                q1_home=?, q1_away=?, q2_home=?, q2_away=?,
                q3_home=?, q3_away=?, q4_home=?, q4_away=?,
                ot_home=?, ot_away=?, status=?, updated_at=datetime('now')
            WHERE game_id=?
        """, (
            home_score, away_score, total,
            data.get('q1_home'), data.get('q1_away'),
            data.get('q2_home'), data.get('q2_away'),
            data.get('q3_home'), data.get('q3_away'),
            data.get('q4_home'), data.get('q4_away'),
            data.get('ot_home'), data.get('ot_away'),
            status, data['game_id']
        ))
        db.commit()
        return {'status': 'ok', 'game_id': data['game_id'], 'updated': True}
    finally:
        db.close()


def get_games(status=None, limit=100, offset=0):
    db = get_db()
    query = "SELECT * FROM games"
    params = []
    if status:
        query += " WHERE status = ?"
        params.append(status)
    query += " ORDER BY game_date DESC, created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = db.execute(query, params).fetchall()
    db.close()
    return [dict(r) for r in rows]


def get_game(game_id):
    db = get_db()
    row = db.execute("SELECT * FROM games WHERE game_id = ?", (game_id,)).fetchone()
    db.close()
    return dict(row) if row else None


# ── Bet CRUD ──────────────────────────────────────────────────────────────

def add_bet(data):
    db = get_db()
    market_line = data['market_line']
    fair_line = data.get('fair_line')
    gap = round(market_line - fair_line, 2) if fair_line else None

    db.execute("""
        INSERT INTO bets (game_id, quarter, market_line, fair_line, final_total,
            gap, z_score, kelly_pct, accuracy, direction, stake, odds,
            result, profit, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data['game_id'], data.get('quarter', 'FG'),
        market_line, fair_line, data.get('final_total'),
        gap, data.get('z_score'), data.get('kelly_pct'),
        data.get('accuracy'), data.get('direction', 'under'),
        data.get('stake', 0), data.get('odds'),
        data.get('result', 'PENDING'), data.get('profit', 0),
        data.get('notes')
    ))
    db.commit()
    bet_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    db.close()
    return {'status': 'ok', 'bet_id': bet_id}


def get_bets(game_id=None, result=None, limit=200, offset=0):
    db = get_db()
    query = """
        SELECT b.*, g.home_team, g.away_team, g.home_score, g.away_score, g.total_score
        FROM bets b
        LEFT JOIN games g ON b.game_id = g.game_id
    """
    conditions = []
    params = []
    if game_id:
        conditions.append("b.game_id = ?")
        params.append(game_id)
    if result:
        conditions.append("b.result = ?")
        params.append(result)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY b.created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = db.execute(query, params).fetchall()
    db.close()
    return [dict(r) for r in rows]


def settle_bet(bet_id, result, final_total=None, profit=None):
    db = get_db()
    db.execute("""
        UPDATE bets SET result=?, final_total=?, profit=?,
            settled_at=datetime('now')
        WHERE id=?
    """, (result, final_total, profit, bet_id))
    db.commit()
    db.close()


def get_stats():
    db = get_db()
    rows = db.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN result='WIN' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN result='LOSS' THEN 1 ELSE 0 END) as losses,
            SUM(CASE WHEN result='PUSH' THEN 1 ELSE 0 END) as pushes,
            SUM(CASE WHEN result='PENDING' THEN 1 ELSE 0 END) as pending,
            SUM(CASE WHEN result='VOID' THEN 1 ELSE 0 END) as voided,
            SUM(profit) as total_profit,
            SUM(stake) as total_staked,
            AVG(CASE WHEN result IN ('WIN','LOSS') THEN gap END) as avg_gap,
            AVG(CASE WHEN result IN ('WIN','LOSS') THEN z_score END) as avg_z_score,
            AVG(CASE WHEN result IN ('WIN','LOSS') THEN kelly_pct END) as avg_kelly
        FROM bets
    """).fetchone()
    stats = dict(rows)
    decided = (stats['wins'] or 0) + (stats['losses'] or 0)
    stats['win_pct'] = round((stats['wins'] or 0) / decided * 100, 1) if decided > 0 else 0
    stats['roi'] = round((stats['total_profit'] or 0) / (stats['total_staked'] or 1) * 100, 1)
    db.close()
    return stats


def auto_settle_bets():
    """Auto-settle pending bets where the game is final."""
    db = get_db()
    pending = db.execute("""
        SELECT b.id, b.game_id, b.market_line, b.direction, b.stake, b.odds,
               g.total_score
        FROM bets b
        JOIN games g ON b.game_id = g.game_id
        WHERE b.result = 'PENDING' AND g.status = 'final' AND g.total_score IS NOT NULL
    """).fetchall()

    settled = 0
    for bet in pending:
        total = bet['total_score']
        line = bet['market_line']
        direction = bet['direction']

        if total == line:
            result = 'PUSH'
            profit = 0
        elif (direction == 'under' and total < line) or (direction == 'over' and total > line):
            result = 'WIN'
            profit = round(bet['stake'] * ((bet['odds'] or 1.9) - 1), 2)
        else:
            result = 'LOSS'
            profit = -bet['stake']

        db.execute("""
            UPDATE bets SET result=?, final_total=?, profit=?, settled_at=datetime('now')
            WHERE id=?
        """, (result, total, profit, bet['id']))
        settled += 1

    db.commit()
    db.close()
    return settled
