# main.py — Volman Scalping Bot — Main Loop with Telegram Control
from __future__ import annotations
import logging
import time
import sys
import os
from datetime import datetime

os.makedirs('logs', exist_ok=True)
os.makedirs('data', exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    handlers=[
        logging.FileHandler('logs/bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('main')

from config import (
    MT5_LOGIN, MT5_PASSWORD, MT5_SERVER,
    SYMBOL, TICK_SIZE, RISK_PCT,
    TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
)
from src.tick_builder       import TickBarBuilder
from src.level_detector     import LevelDetector
from src.buildup_detector   import BuildupDetector
from src.setup_classifier   import SetupClassifier
from src.risk_engine        import RiskEngine
from src.execution_engine   import ExecutionEngine
from src.session_filter     import SessionFilter
from src.alert_system       import AlertSystem
from src.database           import Database
from src.telegram_controller import TelegramController
import MetaTrader5 as mt5


class VolmanBot:
    def __init__(self):
        logger.info("=" * 55)
        logger.info("  VOLMAN SCALPING BOT - STARTING UP")
        logger.info("=" * 55)

        self.bar_builder   = TickBarBuilder(tick_size=TICK_SIZE)
        self.level_det     = LevelDetector()
        self.buildup_det   = BuildupDetector()
        self.classifier    = SetupClassifier(min_confidence=0.55)
        self.session       = SessionFilter()
        self.alerts        = AlertSystem(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)
        self.db            = Database()
        self.executor      = ExecutionEngine()
        self.risk          = RiskEngine(
            account_balance=self.executor.get_account_balance() or 10000,
            risk_pct=RISK_PCT)

        # Telegram controller — lets you send commands from Telegram
        self.telegram = TelegramController(
            token=TELEGRAM_TOKEN, chat_id=TELEGRAM_CHAT_ID)
        self.telegram.set_bot(self)

        self.last_tick_time  = None
        self.bars_since_last_level_update = 0
        self.LEVEL_UPDATE_EVERY = 10
        self.active_ticket   = None
        self.running         = True

        logger.info("All modules initialized")
        self.alerts.session_start()

    def run(self):
        # Start Telegram listener in background
        self.telegram.start_listening()

        logger.info("Bot running | Send /help on Telegram for commands")
        logger.info("Press Ctrl+C to stop\n")

        try:
            while True:
                if self.running:
                    self._tick()
                time.sleep(0.05)
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
            self.alerts.error_alert(str(e))
        finally:
            self._shutdown()

    def _tick(self):
        tick = mt5.symbol_info_tick(SYMBOL)
        if tick is None or tick.time == self.last_tick_time:
            return

        self.last_tick_time = tick.time
        tick_data = {
            'ask': tick.ask, 'bid': tick.bid,
            'time': datetime.fromtimestamp(tick.time)
        }

        completed_bar = self.bar_builder.on_tick(tick_data)
        if completed_bar is None:
            return

        bar_dict = completed_bar.to_dict()
        self.db.log_bar(bar_dict)
        self.bars_since_last_level_update += 1

        bars = self.bar_builder.bars_as_dicts()
        if len(bars) < 20:
            return

        if self.bars_since_last_level_update >= self.LEVEL_UPDATE_EVERY:
            self.level_det.update(bars)
            self.bars_since_last_level_update = 0

        levels = self.level_det.levels
        if not levels:
            return

        spread   = self.executor.get_spread_pips()
        open_pos = len(self.executor.get_open_positions())
        tradeable, reason = self.session.is_tradeable(spread, open_pos)

        if not tradeable:
            return

        if self.active_ticket is not None:
            self._check_trade_status()
            return

        buildup = self.buildup_det.detect(bars, levels)
        if buildup is None:
            return

        logger.info(f"Buildup detected: {buildup}")

        setup = self.classifier.classify(
            buildup, bar_dict, bars, levels)
        if setup is None:
            return

        logger.info(f"Setup: {setup}")
        self.alerts.setup_detected(setup)

        self.risk.update_balance(
            self.executor.get_account_balance())
        params = self.risk.calculate(setup)
        if params is None:
            return

        result = self.executor.place_order(
            direction=params.direction, lot_size=params.lot_size,
            stop=params.stop, target=params.target,
            comment=f"Volman_{setup.setup_type}")

        if result['success']:
            self.active_ticket = result['ticket']
            self.db.log_trade_open(result['ticket'], setup, params)
            self.alerts.trade_opened(setup, params)
            logger.info(f"Trade open | ticket={result['ticket']}")
        else:
            logger.error(f"Order failed: {result['error']}")
            self.alerts.error_alert(f"Order failed: {result['error']}")

    def _check_trade_status(self):
        positions = self.executor.get_open_positions()
        tickets   = [p.ticket for p in positions]
        if self.active_ticket not in tickets:
            logger.info(f"Trade #{self.active_ticket} closed")
            deals = mt5.history_deals_get(ticket=self.active_ticket)
            pnl   = sum(d.profit for d in deals) if deals else 0.0
            pips  = pnl / (self.risk.PIP_VALUE_USD * 0.01)
            self.db.log_trade_close(self.active_ticket, 0.0, pnl, pips)
            self.alerts.trade_closed(self.active_ticket, pnl, pips)
            self.active_ticket = None

    def _shutdown(self):
        logger.info("Shutting down...")
        self.telegram.stop_listening()
        stats = self.db.get_daily_stats()
        self.alerts.session_end(stats)
        self.executor.shutdown()
        self.db.close()
        logger.info("Bot stopped cleanly")


if __name__ == "__main__":
    bot = VolmanBot()
    bot.run()
