# src/telegram_controller.py
"""
Telegram Bot Controller — control your Volman bot from Telegram.

Commands you can send:
  /start    - Start the bot
  /stop     - Stop the bot
  /status   - Show bot status (running, balance, open trades)
  /balance  - Show account balance
  /trades   - Show today's trade history
  /levels   - Show current S/R levels
  /spread   - Show current spread
  /close    - Close all open positions (emergency)
  /help     - Show all commands
"""
from __future__ import annotations
import logging
import threading
from datetime import datetime
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

try:
    from telegram import Update, Bot
    from telegram.ext import (
        Updater, CommandHandler, CallbackContext, Filters, MessageHandler
    )
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    logger.warning("python-telegram-bot not installed. "
                   "Run: pip install python-telegram-bot==13.15")


class TelegramController:
    """
    Runs a Telegram bot that listens for commands.
    You send commands from your phone/desktop Telegram.
    The bot controls the trading engine.
    """

    def __init__(self, token: str, chat_id: str, volman_bot=None):
        """
        Args:
            token:      Telegram bot token from @BotFather
            chat_id:    Your personal chat ID
            volman_bot: Reference to the main VolmanBot instance
        """
        self.token      = token
        self.chat_id    = chat_id
        self.volman_bot = volman_bot  # Will be set after bot starts
        self.updater    = None
        self._thread    = None

        if not TELEGRAM_AVAILABLE:
            logger.error("Cannot start TelegramController: "
                         "python-telegram-bot not installed")
            return

        if not token or not chat_id:
            logger.warning("Telegram token/chat_id not configured. "
                           "Telegram controller disabled.")
            return

        self.bot = Bot(token=token)
        self.updater = Updater(token=token, use_context=True)
        dp = self.updater.dispatcher

        # Register all command handlers
        dp.add_handler(CommandHandler("start",   self._cmd_start))
        dp.add_handler(CommandHandler("stop",    self._cmd_stop))
        dp.add_handler(CommandHandler("status",  self._cmd_status))
        dp.add_handler(CommandHandler("balance", self._cmd_balance))
        dp.add_handler(CommandHandler("trades",  self._cmd_trades))
        dp.add_handler(CommandHandler("levels",  self._cmd_levels))
        dp.add_handler(CommandHandler("spread",  self._cmd_spread))
        dp.add_handler(CommandHandler("close",   self._cmd_close_all))
        dp.add_handler(CommandHandler("help",    self._cmd_help))
        dp.add_handler(MessageHandler(
            Filters.text & ~Filters.command, self._unknown))
        dp.add_error_handler(self._error_handler)

        logger.info("TelegramController initialized")

    def set_bot(self, volman_bot):
        """Set the reference to the main bot after it's created"""
        self.volman_bot = volman_bot

    def start_listening(self):
        """Start listening for Telegram commands in a background thread"""
        if self.updater is None:
            logger.warning("Telegram updater not available")
            return

        def _run():
            logger.info("Telegram listener started")
            self.updater.start_polling(drop_pending_updates=True)
            # Keep thread alive without using signal (signal only works in main thread)
            import time
            while True:
                time.sleep(1)

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        self._send("Bot controller connected. Send /help for commands.")

    def stop_listening(self):
        """Stop the Telegram listener"""
        if self.updater:
            self.updater.stop()
            logger.info("Telegram listener stopped")

    # ─────────────────────────────────────────
    # SECURITY — only respond to your chat ID
    # ─────────────────────────────────────────

    def _is_authorized(self, update: Update) -> bool:
        """Only respond to messages from the configured chat_id"""
        sender = str(update.effective_chat.id)
        if sender != str(self.chat_id):
            logger.warning(f"Unauthorized access attempt from chat_id: {sender}")
            update.message.reply_text("Not authorized.")
            return False
        return True

    # ─────────────────────────────────────────
    # COMMAND HANDLERS
    # ─────────────────────────────────────────

    def _cmd_start(self, update: Update, context: CallbackContext):
        if not self._is_authorized(update):
            return
        if self.volman_bot and not self.volman_bot.running:
            self.volman_bot.running = True
            update.message.reply_text(
                "Bot STARTED\n"
                "Scanning EUR/USD for setups...\n"
                "Send /status to check progress")
        else:
            update.message.reply_text("Bot is already running.")

    def _cmd_stop(self, update: Update, context: CallbackContext):
        if not self._is_authorized(update):
            return
        if self.volman_bot:
            self.volman_bot.running = False
            update.message.reply_text(
                "Bot STOPPED\n"
                "No new trades will be placed.\n"
                "Open positions remain active.\n"
                "Send /start to resume.")
        else:
            update.message.reply_text("Bot not initialized yet.")

    def _cmd_status(self, update: Update, context: CallbackContext):
        if not self._is_authorized(update):
            return

        if not self.volman_bot:
            update.message.reply_text("Bot not initialized.")
            return

        running = "RUNNING" if self.volman_bot.running else "STOPPED"
        bars = self.volman_bot.bar_builder.total_bars_built()
        progress = self.volman_bot.bar_builder.current_bar_progress()
        levels = len(self.volman_bot.level_det.levels)

        # Get balance and positions if MT5 is connected
        balance = "N/A"
        positions = 0
        spread = "N/A"
        if self.volman_bot.executor.is_connected():
            balance = f"${self.volman_bot.executor.get_account_balance():.2f}"
            positions = len(self.volman_bot.executor.get_open_positions())
            spread = f"{self.volman_bot.executor.get_spread_pips():.1f} pips"

        # Get daily stats
        stats = self.volman_bot.db.get_daily_stats()

        msg = (
            f"VOLMAN BOT STATUS\n"
            f"{'='*30}\n"
            f"State    : {running}\n"
            f"Balance  : {balance}\n"
            f"Spread   : {spread}\n"
            f"Positions: {positions}\n"
            f"{'='*30}\n"
            f"Bars built  : {bars}\n"
            f"Current bar : {progress['ticks_in']}/{progress['ticks_in'] + progress['ticks_left']} ticks\n"
            f"S/R levels  : {levels}\n"
            f"{'='*30}\n"
            f"TODAY'S STATS\n"
            f"Trades : {stats['trades']}\n"
            f"Wins   : {stats['wins']}\n"
            f"P&L    : ${stats['pnl']:+.2f}\n"
            f"{'='*30}\n"
            f"Time: {datetime.utcnow().strftime('%H:%M:%S')} UTC")

        update.message.reply_text(msg)

    def _cmd_balance(self, update: Update, context: CallbackContext):
        if not self._is_authorized(update):
            return
        if self.volman_bot and self.volman_bot.executor.is_connected():
            bal = self.volman_bot.executor.get_account_balance()
            update.message.reply_text(f"Account Balance: ${bal:.2f}")
        else:
            update.message.reply_text("MT5 not connected.")

    def _cmd_trades(self, update: Update, context: CallbackContext):
        if not self._is_authorized(update):
            return
        if not self.volman_bot:
            update.message.reply_text("Bot not initialized.")
            return

        trades = self.volman_bot.db.get_all_trades()
        if not trades:
            update.message.reply_text("No trades recorded yet.")
            return

        msg = f"TRADE HISTORY (last 10)\n{'='*30}\n"
        for t in trades[:10]:
            status = t.get('status', '?')
            pnl = t.get('pnl', 0) or 0
            msg += (f"\n#{t['ticket']} | {t['setup_type']} "
                    f"{t['direction']} | {status} | "
                    f"P&L: ${pnl:+.2f}")
        update.message.reply_text(msg)

    def _cmd_levels(self, update: Update, context: CallbackContext):
        if not self._is_authorized(update):
            return
        if not self.volman_bot:
            update.message.reply_text("Bot not initialized.")
            return

        levels = self.volman_bot.level_det.levels
        if not levels:
            update.message.reply_text("No S/R levels detected yet.\n"
                                      "Need more bars to form.")
            return

        msg = f"S/R LEVELS ({len(levels)})\n{'='*30}\n"
        for i, l in enumerate(levels[:15], 1):
            tag = "R" if l.level_type == 'resistance' else "S"
            rnd = " [ROUND]" if l.is_round else ""
            msg += f"\n{i}. {tag} {l.price:.5f}{rnd} | score={l.score:.1f}"
        update.message.reply_text(msg)

    def _cmd_spread(self, update: Update, context: CallbackContext):
        if not self._is_authorized(update):
            return
        if self.volman_bot and self.volman_bot.executor.is_connected():
            spread = self.volman_bot.executor.get_spread_pips()
            status = "OK" if spread <= 1.5 else "TOO WIDE"
            update.message.reply_text(
                f"Current Spread: {spread:.1f} pips [{status}]")
        else:
            update.message.reply_text("MT5 not connected.")

    def _cmd_close_all(self, update: Update, context: CallbackContext):
        if not self._is_authorized(update):
            return
        if not self.volman_bot:
            update.message.reply_text("Bot not initialized.")
            return

        count = self.volman_bot.executor.close_all()
        self.volman_bot.active_ticket = None
        update.message.reply_text(
            f"EMERGENCY CLOSE\n"
            f"Closed {count} position(s).\n"
            f"Bot is still running — send /stop to pause.")

    def _cmd_help(self, update: Update, context: CallbackContext):
        if not self._is_authorized(update):
            return
        msg = (
            "VOLMAN BOT COMMANDS\n"
            "========================\n"
            "/start   - Start the bot\n"
            "/stop    - Stop the bot\n"
            "/status  - Full bot status\n"
            "/balance - Account balance\n"
            "/trades  - Trade history\n"
            "/levels  - S/R levels\n"
            "/spread  - Current spread\n"
            "/close   - Close all positions\n"
            "/help    - This message")
        update.message.reply_text(msg)

    def _unknown(self, update: Update, context: CallbackContext):
        if not self._is_authorized(update):
            return
        update.message.reply_text(
            "Unknown command. Send /help for available commands.")

    # ─────────────────────────────────────────
    # ERROR HANDLER
    # ─────────────────────────────────────────

    def _error_handler(self, update, context: CallbackContext):
        """Log Telegram errors and let the updater retry automatically"""
        logger.warning(f"Telegram error: {context.error}")

    # ─────────────────────────────────────────
    # SEND MESSAGES TO YOU
    # ─────────────────────────────────────────

    def _send(self, message: str):
        """Send a message to the configured chat"""
        if self.bot and self.chat_id:
            try:
                self.bot.send_message(chat_id=self.chat_id, text=message)
            except Exception as e:
                logger.error(f"Telegram send failed: {e}")
