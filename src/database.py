# src/database.py
from __future__ import annotations
import logging
import sqlite3
from datetime import datetime
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_PATH

logger = logging.getLogger(__name__)


class Database:
    def __init__(self):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self._create_tables()
        logger.info(f"Database connected: {DB_PATH}")

    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS trades (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket      INTEGER,
                setup_type  TEXT,
                direction   TEXT,
                entry       REAL,
                stop        REAL,
                target      REAL,
                lot_size    REAL,
                risk_pips   REAL,
                reward_pips REAL,
                risk_reward REAL,
                confidence  REAL,
                open_time   TEXT,
                close_time  TEXT,
                close_price REAL,
                pnl         REAL,
                pips        REAL,
                status      TEXT DEFAULT 'open'
            );
            CREATE TABLE IF NOT EXISTS bars (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                open      REAL,
                high      REAL,
                low       REAL,
                close     REAL,
                bar_time  TEXT,
                range_pip REAL
            );
            CREATE TABLE IF NOT EXISTS bot_log (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                level     TEXT,
                message   TEXT
            );
        """)
        self.conn.commit()

    def log_trade_open(self, ticket, setup, params) -> int:
        cursor = self.conn.execute("""
            INSERT INTO trades
            (ticket, setup_type, direction, entry, stop, target,
             lot_size, risk_pips, reward_pips, risk_reward,
             confidence, open_time, status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (ticket, setup.setup_type, params.direction,
              params.entry, params.stop, params.target,
              params.lot_size, params.risk_pips, params.reward_pips,
              params.risk_reward, setup.confidence,
              datetime.utcnow().isoformat(), 'open'))
        self.conn.commit()
        return cursor.lastrowid

    def log_trade_close(self, ticket, close_price, pnl, pips):
        self.conn.execute("""
            UPDATE trades SET status='closed', close_time=?,
            close_price=?, pnl=?, pips=? WHERE ticket=?
        """, (datetime.utcnow().isoformat(), close_price, pnl, pips, ticket))
        self.conn.commit()

    def log_bar(self, bar: dict):
        self.conn.execute("""
            INSERT INTO bars (open, high, low, close, bar_time, range_pip)
            VALUES (?,?,?,?,?,?)
        """, (bar['open'], bar['high'], bar['low'], bar['close'],
              bar.get('time', datetime.utcnow().isoformat())
              if isinstance(bar.get('time'), str)
              else str(bar.get('time', datetime.utcnow())),
              bar.get('range_pips', 0)))
        self.conn.commit()

    def get_daily_stats(self) -> dict:
        today = datetime.utcnow().date().isoformat()
        cursor = self.conn.execute("""
            SELECT COUNT(*), SUM(pnl),
                   SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END)
            FROM trades WHERE status='closed' AND date(close_time) = ?
        """, (today,))
        row = cursor.fetchone()
        return {'trades': row[0] or 0, 'pnl': row[1] or 0.0,
                'wins': row[2] or 0}

    def get_all_trades(self) -> list:
        cursor = self.conn.execute(
            "SELECT * FROM trades ORDER BY open_time DESC")
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def close(self):
        self.conn.close()
