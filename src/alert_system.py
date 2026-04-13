# src/alert_system.py
from __future__ import annotations
import logging
from datetime import datetime
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)


class AlertSystem:
    def __init__(self, token: str = None, chat_id: str = None):
        self.token   = token
        self.chat_id = chat_id
        self.enabled = False
        self.bot     = None

        if token and chat_id:
            try:
                import telegram
                self.bot = telegram.Bot(token=token)
                self.enabled = True
                logger.info("AlertSystem: Telegram enabled")
            except ImportError:
                logger.info("AlertSystem: python-telegram-bot not installed")

        if not self.enabled:
            logger.info("AlertSystem: Console-only mode")

    def trade_opened(self, setup, params):
        emoji = "BUY" if params.direction == 'BUY' else "SELL"
        msg = (
            f"TRADE OPENED - {setup.setup_type}\n"
            f"{'='*30}\n"
            f"Direction : {params.direction}\n"
            f"Entry     : {params.entry:.5f}\n"
            f"Stop      : {params.stop:.5f} ({params.risk_pips:.1f} pip)\n"
            f"Target    : {params.target:.5f} ({params.reward_pips:.1f} pip)\n"
            f"Lots      : {params.lot_size}\n"
            f"R:R       : {params.risk_reward:.2f}\n"
            f"Risk $    : ${params.risk_amount:.2f}\n"
            f"Confidence: {setup.confidence:.0%}\n"
            f"{'='*30}\n"
            f"Time: {datetime.utcnow().strftime('%H:%M:%S')} UTC")
        self._send(msg)

    def trade_closed(self, ticket: int, pnl: float, pips: float):
        result = "WIN" if pnl >= 0 else "LOSS"
        msg = (
            f"TRADE CLOSED - {result}\n"
            f"{'='*30}\n"
            f"Ticket : #{ticket}\n"
            f"P&L    : ${pnl:+.2f}\n"
            f"Pips   : {pips:+.1f}\n"
            f"{'='*30}\n"
            f"Time: {datetime.utcnow().strftime('%H:%M:%S')} UTC")
        self._send(msg)

    def session_start(self):
        from config import SYMBOL
        msg = (f"VOLMAN BOT - SESSION STARTED\n"
               f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC\n"
               f"Watching {SYMBOL} for setups...")
        self._send(msg)

    def session_end(self, daily_stats: dict):
        pnl    = daily_stats.get('pnl', 0)
        trades = daily_stats.get('trades', 0)
        wins   = daily_stats.get('wins', 0)
        msg = (
            f"SESSION ENDED - DAILY SUMMARY\n"
            f"{'='*30}\n"
            f"Trades : {trades}\n"
            f"Wins   : {wins}/{trades}\n"
            f"P&L    : ${pnl:+.2f}\n"
            f"{'='*30}")
        self._send(msg)

    def error_alert(self, error_msg: str):
        msg = (f"BOT ERROR\n{error_msg}\n"
               f"Time: {datetime.utcnow().strftime('%H:%M:%S')} UTC")
        self._send(msg)

    def setup_detected(self, setup):
        msg = (
            f"SETUP DETECTED - {setup.setup_type}\n"
            f"Direction  : {setup.direction}\n"
            f"Entry      : {setup.entry_price:.5f}\n"
            f"Confidence : {setup.confidence:.0%}")
        self._send(msg)

    def send_custom(self, message: str):
        self._send(message)

    def _send(self, message: str):
        print(f"\n[ALERT] {message}\n")
        logger.info(f"Alert: {message[:80]}...")
        if self.enabled and self.bot:
            try:
                self.bot.send_message(chat_id=self.chat_id, text=message)
            except Exception as e:
                logger.error(f"Telegram send failed: {e}")
