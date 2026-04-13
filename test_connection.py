# test_connection.py — Quick MT5 connection test
import sys

try:
    import MetaTrader5 as mt5
except ImportError:
    print("MetaTrader5 not installed. Run: pip install MetaTrader5")
    sys.exit(1)

from config import MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, SYMBOL, PIP_SIZE


def test_connection():
    # Initialize MT5
    if not mt5.initialize():
        print("MT5 failed to initialize")
        print(mt5.last_error())
        return False

    # Login
    authorized = mt5.login(
        login=MT5_LOGIN,
        password=MT5_PASSWORD,
        server=MT5_SERVER
    )

    if not authorized:
        print("Login failed:", mt5.last_error())
        mt5.shutdown()
        return False

    # Account info
    info = mt5.account_info()
    print(f"Connected!")
    print(f"  Account : {info.login}")
    print(f"  Balance : ${info.balance:.2f}")
    print(f"  Equity  : ${info.equity:.2f}")
    print(f"  Broker  : {info.company}")
    print(f"  Server  : {info.server}")

    # Symbol info
    symbol_info = mt5.symbol_info(SYMBOL)
    if symbol_info is None:
        print(f"\n  {SYMBOL} not found -- check symbol name")
    else:
        print(f"\n  Symbol  : {SYMBOL}")
        print(f"  Digits  : {symbol_info.digits}")
        print(f"  Min lot : {symbol_info.volume_min}")
        print(f"  Max lot : {symbol_info.volume_max}")

    # Tick data
    tick = mt5.symbol_info_tick(SYMBOL)
    if tick:
        spread = (tick.ask - tick.bid) / PIP_SIZE
        print(f"  Ask     : {tick.ask}")
        print(f"  Bid     : {tick.bid}")
        print(f"  Spread  : {spread:.1f} pips")
    else:
        print(f"\n  Could not get tick for {SYMBOL}")

    mt5.shutdown()
    print("\nMT5 disconnected")
    return True


if __name__ == "__main__":
    test_connection()
