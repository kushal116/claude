# backtest.py — Replay historical data through the Volman pipeline
"""
Usage:
    python backtest.py                    # Default: last 5 days of XAUUSD M1
    python backtest.py --days 10          # Last 10 days
    python backtest.py --tick-size 70     # Custom tick size
    python backtest.py --no-session       # Ignore session filter (trade any time)
"""
from __future__ import annotations
import argparse
import logging
import sys
import os
from datetime import datetime, timedelta
from dataclasses import dataclass, field

logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s | %(levelname)-8s | %(message)s'
)
logger = logging.getLogger('backtest')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import SYMBOL, TICK_SIZE, RISK_PCT, PIP_SIZE, PIP_VALUE
from src.tick_builder import TickBarBuilder
from src.level_detector import LevelDetector
from src.buildup_detector import BuildupDetector
from src.setup_classifier import SetupClassifier
from src.risk_engine import RiskEngine

PIP = PIP_SIZE


@dataclass
class BacktestTrade:
    setup_type:  str
    direction:   str
    entry:       float
    stop:        float
    target:      float
    lot_size:    float
    risk_pips:   float
    reward_pips: float
    risk_reward: float
    confidence:  float
    entry_time:  datetime
    exit_time:   datetime = None
    exit_price:  float = 0.0
    pnl:         float = 0.0
    pips:        float = 0.0
    result:      str = 'open'  # 'win', 'loss', 'open'


class Backtester:
    def __init__(self, tick_size=70, risk_pct=1.0, balance=100000.0,
                 use_session_filter=True):
        self.tick_size = tick_size
        self.initial_balance = balance
        self.balance = balance
        self.risk_pct = risk_pct
        self.use_session_filter = use_session_filter

        self.bar_builder = TickBarBuilder(tick_size=tick_size)
        self.level_det = LevelDetector()
        self.buildup_det = BuildupDetector()
        self.classifier = SetupClassifier(min_confidence=0.55)
        self.risk = RiskEngine(account_balance=balance, risk_pct=risk_pct)

        self.trades: list[BacktestTrade] = []
        self.active_trade: BacktestTrade = None
        self.bars_since_level_update = 0
        self.total_bars = 0

    def run(self, rates):
        """
        Run backtest on historical M1 rates from MT5.

        Args:
            rates: numpy structured array from mt5.copy_rates_from_pos()
        """
        print(f"\nBacktesting {SYMBOL} | {len(rates)} M1 bars | "
              f"tick_size={self.tick_size}")
        print(f"Balance: ${self.balance:.2f} | Risk: {self.risk_pct}%")
        print(f"Session filter: {'ON' if self.use_session_filter else 'OFF'}")
        print(f"{'='*60}")

        for i, rate in enumerate(rates):
            bar_time = datetime.utcfromtimestamp(rate['time'])

            # Check if active trade hit SL/TP on this M1 bar
            if self.active_trade:
                self._check_exit(rate, bar_time)

            # Simulate ticks from M1 bar (open -> high/low -> close)
            self._simulate_ticks_from_bar(rate, bar_time)

        # Close any remaining trade at last price
        if self.active_trade:
            last_rate = rates[-1]
            self.active_trade.exit_price = last_rate['close']
            self.active_trade.exit_time = datetime.utcfromtimestamp(
                last_rate['time'])
            self._calc_trade_pnl(self.active_trade)
            self.active_trade = None

        self._print_results()

    def _simulate_ticks_from_bar(self, rate, bar_time):
        """Convert M1 OHLC bar into simulated tick sequence"""
        spread = 0.18  # Approximate XAUUSD spread ($0.18)
        prices = [rate['open'], rate['high'], rate['low'], rate['close']]

        for price in prices:
            tick = {
                'ask': price + spread / 2,
                'bid': price - spread / 2,
                'time': bar_time
            }
            completed_bar = self.bar_builder.on_tick(tick)

            if completed_bar:
                self.total_bars += 1
                self._on_bar_complete(completed_bar.to_dict(), bar_time)

    def _on_bar_complete(self, bar_dict, bar_time):
        """Process a completed tick bar through the pipeline"""
        self.bars_since_level_update += 1
        bars = self.bar_builder.bars_as_dicts()

        if len(bars) < 20:
            return

        # Update levels every 10 bars
        if self.bars_since_level_update >= 10:
            self.level_det.update(bars)
            self.bars_since_level_update = 0

        levels = self.level_det.levels
        if not levels:
            return

        # Session filter (13:00-17:00 UTC)
        if self.use_session_filter:
            hour = bar_time.hour
            if hour < 13 or hour >= 17:
                return

        # Already in a trade
        if self.active_trade:
            return

        # Detect buildup
        buildup = self.buildup_det.detect(bars, levels)
        if buildup is None:
            return
        print(f"  [DBG] Buildup found at {bar_time}: {buildup.direction} "
              f"score={buildup.quality_score:.1f} "
              f"level={buildup.nearest_level.price:.2f}")

        # Classify setup
        setup = self.classifier.classify(buildup, bar_dict, bars, levels)
        if setup is None:
            level = buildup.nearest_level
            close = bar_dict['close']
            if self.total_bars < 200:  # Only debug first few
                print(f"    [REJ] close={close:.2f} level={level.price:.2f} "
                      f"dir={buildup.direction}")
            return

        # Calculate trade params
        self.risk.update_balance(self.balance)
        params = self.risk.calculate(setup)
        if params is None:
            if self.total_bars < 200:
                print(f"    [RISK-REJ] R:R too low for {setup.setup_type}")
            return

        # Debug: show we got here
        print(f"  ** Setup found: {setup.setup_type} {params.direction} "
              f"entry={params.entry:.2f} stop={params.stop:.2f} "
              f"target={params.target:.2f}")

        # Open trade
        trade = BacktestTrade(
            setup_type=setup.setup_type,
            direction=params.direction,
            entry=params.entry,
            stop=params.stop,
            target=params.target,
            lot_size=params.lot_size,
            risk_pips=params.risk_pips,
            reward_pips=params.reward_pips,
            risk_reward=params.risk_reward,
            confidence=setup.confidence,
            entry_time=bar_time,
        )
        self.active_trade = trade
        self.trades.append(trade)
        print(f"  OPEN  {trade.direction} {trade.setup_type} @ "
              f"{trade.entry:.2f} | SL={trade.stop:.2f} "
              f"TP={trade.target:.2f} | {bar_time.strftime('%Y-%m-%d %H:%M')}")

    def _check_exit(self, rate, bar_time):
        """Check if M1 bar hits stop or target"""
        trade = self.active_trade
        if trade is None:
            return

        hit_stop = False
        hit_target = False

        if trade.direction == 'BUY':
            if rate['low'] <= trade.stop:
                hit_stop = True
            elif rate['high'] >= trade.target:
                hit_target = True
        else:  # SELL
            if rate['high'] >= trade.stop:
                hit_stop = True
            elif rate['low'] <= trade.target:
                hit_target = True

        if hit_stop:
            trade.exit_price = trade.stop
            trade.exit_time = bar_time
            trade.result = 'loss'
            self._calc_trade_pnl(trade)
            emoji = 'LOSS'
            print(f"  CLOSE {emoji} @ {trade.exit_price:.2f} | "
                  f"P&L: ${trade.pnl:+.2f} ({trade.pips:+.1f} pips) | "
                  f"{bar_time.strftime('%Y-%m-%d %H:%M')}")
            self.active_trade = None

        elif hit_target:
            trade.exit_price = trade.target
            trade.exit_time = bar_time
            trade.result = 'win'
            self._calc_trade_pnl(trade)
            emoji = 'WIN '
            print(f"  CLOSE {emoji} @ {trade.exit_price:.2f} | "
                  f"P&L: ${trade.pnl:+.2f} ({trade.pips:+.1f} pips) | "
                  f"{bar_time.strftime('%Y-%m-%d %H:%M')}")
            self.active_trade = None

    def _calc_trade_pnl(self, trade: BacktestTrade):
        if trade.direction == 'BUY':
            trade.pips = (trade.exit_price - trade.entry) / PIP
        else:
            trade.pips = (trade.entry - trade.exit_price) / PIP
        trade.pnl = trade.pips * PIP_VALUE * trade.lot_size
        self.balance += trade.pnl

    def _print_results(self):
        print(f"\n{'='*60}")
        print(f"  BACKTEST RESULTS")
        print(f"{'='*60}")

        closed = [t for t in self.trades if t.result != 'open']
        wins = [t for t in closed if t.result == 'win']
        losses = [t for t in closed if t.result == 'loss']

        total_pnl = sum(t.pnl for t in closed)
        total_pips = sum(t.pips for t in closed)

        print(f"  Total trades  : {len(closed)}")

        if closed:
            win_rate = len(wins) / len(closed) * 100
            print(f"  Wins          : {len(wins)}")
            print(f"  Losses        : {len(losses)}")
            print(f"  Win rate      : {win_rate:.1f}%")
            print(f"  Total pips    : {total_pips:+.1f}")
            print(f"  Total P&L     : ${total_pnl:+.2f}")
            print(f"  Start balance : ${self.initial_balance:.2f}")
            print(f"  End balance   : ${self.balance:.2f}")
            print(f"  Return        : {(self.balance/self.initial_balance-1)*100:+.2f}%")

            if wins:
                avg_win = sum(t.pnl for t in wins) / len(wins)
                print(f"  Avg win       : ${avg_win:+.2f}")
            if losses:
                avg_loss = sum(t.pnl for t in losses) / len(losses)
                print(f"  Avg loss      : ${avg_loss:+.2f}")
            if wins and losses:
                avg_win_pips = sum(t.pips for t in wins) / len(wins)
                avg_loss_pips = sum(t.pips for t in losses) / len(losses)
                print(f"  Avg win pips  : {avg_win_pips:+.1f}")
                print(f"  Avg loss pips : {avg_loss_pips:+.1f}")

            # By setup type
            setup_types = set(t.setup_type for t in closed)
            if len(setup_types) > 1:
                print(f"\n  BY SETUP TYPE:")
                for st in sorted(setup_types):
                    st_trades = [t for t in closed if t.setup_type == st]
                    st_wins = [t for t in st_trades if t.result == 'win']
                    st_pnl = sum(t.pnl for t in st_trades)
                    wr = len(st_wins) / len(st_trades) * 100 if st_trades else 0
                    print(f"    {st}: {len(st_trades)} trades | "
                          f"{wr:.0f}% win | ${st_pnl:+.2f}")

            # Trade list
            print(f"\n  TRADE LOG:")
            for i, t in enumerate(closed, 1):
                emoji = 'W' if t.result == 'win' else 'L'
                print(f"    {i:3}. [{emoji}] {t.setup_type} {t.direction} | "
                      f"entry={t.entry:.2f} exit={t.exit_price:.2f} | "
                      f"{t.pips:+.1f} pips ${t.pnl:+.2f} | "
                      f"{t.entry_time.strftime('%m-%d %H:%M')}")
        else:
            print(f"  No trades taken.")
            print(f"\n  Possible reasons:")
            print(f"  - Session filter blocking (try --no-session)")
            print(f"  - Not enough bars to form levels/buildups")
            print(f"  - Parameters too tight for {SYMBOL}")

        print(f"\n  Tick bars built : {self.total_bars}")
        print(f"  S/R levels      : {len(self.level_det.levels)}")
        print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description='Volman Bot Backtester')
    parser.add_argument('--days', type=int, default=5,
                        help='Number of days of history (default: 5)')
    parser.add_argument('--tick-size', type=int, default=TICK_SIZE,
                        help=f'Tick bar size (default: {TICK_SIZE})')
    parser.add_argument('--risk', type=float, default=RISK_PCT,
                        help=f'Risk percent (default: {RISK_PCT})')
    parser.add_argument('--balance', type=float, default=100000.0,
                        help='Starting balance (default: 100000)')
    parser.add_argument('--no-session', action='store_true',
                        help='Disable session time filter')
    args = parser.parse_args()

    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("MetaTrader5 not installed")
        sys.exit(1)

    if not mt5.initialize():
        print("MT5 failed to initialize -- is MetaTrader 5 running?")
        sys.exit(1)

    from config import MT5_LOGIN, MT5_PASSWORD, MT5_SERVER
    mt5.login(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER)

    # Fetch historical M1 data
    bars_count = args.days * 24 * 60  # 1 bar per minute
    print(f"Fetching {bars_count} M1 bars ({args.days} days) for {SYMBOL}...")

    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M1, 0, bars_count)
    mt5.shutdown()

    if rates is None or len(rates) == 0:
        print(f"No data returned for {SYMBOL}")
        sys.exit(1)

    print(f"Got {len(rates)} bars from "
          f"{datetime.utcfromtimestamp(rates[0]['time']).strftime('%Y-%m-%d')} to "
          f"{datetime.utcfromtimestamp(rates[-1]['time']).strftime('%Y-%m-%d')}")

    bt = Backtester(
        tick_size=args.tick_size,
        risk_pct=args.risk,
        balance=args.balance,
        use_session_filter=not args.no_session,
    )
    bt.run(rates)


if __name__ == "__main__":
    main()
