# src/execution_engine.py
from __future__ import annotations
import logging
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

from config import MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, SYMBOL


class ExecutionEngine:
    MAGIC = 20240101

    def __init__(self):
        self.connected = False
        if MT5_AVAILABLE:
            self._connect()

    def _connect(self) -> bool:
        if not mt5.initialize():
            logger.error(f"MT5 init failed: {mt5.last_error()}")
            return False
        if MT5_LOGIN and MT5_PASSWORD and MT5_SERVER:
            authorized = mt5.login(
                login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER)
            if not authorized:
                logger.error(f"MT5 login failed: {mt5.last_error()}")
                return False
        self.connected = True
        info = mt5.account_info()
        if info:
            logger.info(f"MT5 connected | account={info.login} | "
                        f"balance=${info.balance:.2f}")
        return True

    def is_connected(self) -> bool:
        if not MT5_AVAILABLE:
            return False
        try:
            info = mt5.account_info()
            if info is None:
                self.connected = False
                return self._connect()
            return True
        except Exception as e:
            logger.error(f"Connection check failed: {e}")
            return False

    def place_order(self, direction, lot_size, stop, target,
                    comment='VolmanBot') -> dict:
        if not self.is_connected():
            return {'success': False, 'error': 'Not connected to MT5'}

        symbol_info = mt5.symbol_info(SYMBOL)
        if symbol_info is None:
            return {'success': False, 'error': f'Symbol {SYMBOL} not found'}
        if not symbol_info.visible:
            mt5.symbol_select(SYMBOL, True)

        tick       = mt5.symbol_info_tick(SYMBOL)
        order_type = mt5.ORDER_TYPE_BUY if direction == 'BUY' else mt5.ORDER_TYPE_SELL
        price      = tick.ask if direction == 'BUY' else tick.bid

        if direction == 'BUY' and (stop >= price or target <= price):
            return {'success': False, 'error': 'Invalid BUY stop/target'}
        if direction == 'SELL' and (stop <= price or target >= price):
            return {'success': False, 'error': 'Invalid SELL stop/target'}

        request = {
            "action":       mt5.TRADE_ACTION_DEAL,
            "symbol":       SYMBOL,
            "volume":       float(lot_size),
            "type":         order_type,
            "price":        price,
            "sl":           stop,
            "tp":           target,
            "deviation":    10,
            "magic":        self.MAGIC,
            "comment":      comment,
            "type_time":    mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"Order placed | ticket={result.order} | "
                        f"{direction} {lot_size} lots @ {price:.5f}")
            return {'success': True, 'ticket': result.order,
                    'price': result.price, 'retcode': result.retcode,
                    'error': None}
        else:
            error = f"Order failed: retcode={result.retcode} | {result.comment}"
            logger.error(error)
            return {'success': False, 'ticket': None,
                    'retcode': result.retcode, 'error': error}

    def close_position(self, ticket: int) -> dict:
        if not self.is_connected():
            return {'success': False, 'error': 'Not connected'}
        position = None
        for pos in mt5.positions_get(symbol=SYMBOL):
            if pos.ticket == ticket:
                position = pos
                break
        if position is None:
            return {'success': False, 'error': f'Ticket {ticket} not found'}

        direction = (mt5.ORDER_TYPE_SELL
                     if position.type == mt5.POSITION_TYPE_BUY
                     else mt5.ORDER_TYPE_BUY)
        tick  = mt5.symbol_info_tick(SYMBOL)
        price = (tick.bid if position.type == mt5.POSITION_TYPE_BUY
                 else tick.ask)
        request = {
            "action":       mt5.TRADE_ACTION_DEAL,
            "symbol":       SYMBOL,
            "volume":       position.volume,
            "type":         direction,
            "position":     ticket,
            "price":        price,
            "deviation":    10,
            "magic":        self.MAGIC,
            "comment":      "VolmanBot Close",
            "type_time":    mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        success = result.retcode == mt5.TRADE_RETCODE_DONE
        return {'success': success, 'retcode': result.retcode}

    def close_all(self) -> int:
        positions = mt5.positions_get(symbol=SYMBOL) or []
        count = 0
        for pos in positions:
            if pos.magic == self.MAGIC:
                result = self.close_position(pos.ticket)
                if result['success']:
                    count += 1
        return count

    def get_open_positions(self) -> list:
        if not self.is_connected():
            return []
        positions = mt5.positions_get(symbol=SYMBOL) or []
        return [p for p in positions if p.magic == self.MAGIC]

    def get_account_balance(self) -> float:
        if not self.is_connected():
            return 0.0
        info = mt5.account_info()
        return info.balance if info else 0.0

    def get_spread_pips(self) -> float:
        tick = mt5.symbol_info_tick(SYMBOL)
        if tick is None:
            return 99.0
        from config import PIP_SIZE
        return round((tick.ask - tick.bid) / PIP_SIZE, 1)

    def shutdown(self):
        if MT5_AVAILABLE:
            mt5.shutdown()
        self.connected = False
        logger.info("MT5 shutdown")
