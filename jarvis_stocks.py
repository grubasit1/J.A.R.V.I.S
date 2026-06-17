#!/usr/bin/env python3
"""Jarvis Stock Trading Module — real-time data, technical analysis, trade execution.
Uses Alpaca (paper trading) for orders and yfinance for market data.

Setup: Get free Alpaca paper trading keys at https://alpaca.markets
Then set in ~/.config/jarvis/environment:
  ALPACA_API_KEY=your_key
  ALPACA_SECRET_KEY=your_secret
"""
import os, json, time
from datetime import datetime, timedelta

import yfinance as yf
import pandas as pd
import ta

# Alpaca config — paper trading (safe, no real money)
ALPACA_KEY = os.environ.get("ALPACA_API_KEY", "")
ALPACA_SECRET = os.environ.get("ALPACA_SECRET_KEY", "")
PAPER_URL = "https://paper-api.alpaca.markets"

WATCHLIST_FILE = os.path.expanduser("~/jarvis_watchlist.json")
TRADES_LOG = os.path.expanduser("~/jarvis_trades.log")
STOCK_STATE = "/tmp/jarvis_stocks.json"

def _load_watchlist():
    try:
        with open(WATCHLIST_FILE) as f:
            return json.load(f)
    except:
        return ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN", "META", "GOOGL", "AMD", "SPY", "QQQ"]

def _save_watchlist(symbols):
    with open(WATCHLIST_FILE, "w") as f:
        json.dump(symbols, f)

def _log_trade(msg):
    with open(TRADES_LOG, "a") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")

# ═══════════════════════════════════════════
# MARKET DATA
# ═══════════════════════════════════════════

def get_price(symbol):
    """Get current price + daily change."""
    try:
        df = yf.download(symbol.upper(), period="5d", progress=False)
        if df.empty:
            return {"error": "No data"}
        price = float(df["Close"].iloc[-1].iloc[0]) if hasattr(df["Close"].iloc[-1], 'iloc') else float(df["Close"].iloc[-1])
        prev = float(df["Close"].iloc[-2].iloc[0]) if len(df) > 1 and hasattr(df["Close"].iloc[-2], 'iloc') else (float(df["Close"].iloc[-2]) if len(df) > 1 else price)
        change = ((price - prev) / prev) * 100 if prev else 0
        return {"symbol": symbol.upper(), "price": round(price, 2),
                "change": round(change, 2), "prev_close": round(prev, 2)}
    except Exception as e:
        return {"error": str(e)}

def get_multi_prices(symbols=None):
    """Get prices for all watchlist stocks."""
    if symbols is None:
        symbols = _load_watchlist()
    results = []
    for s in symbols[:15]:  # Cap at 15 to avoid rate limits
        r = get_price(s)
        if "error" not in r:
            results.append(r)
        time.sleep(0.2)
    # Save to state file for HUD
    with open(STOCK_STATE, "w") as f:
        json.dump({"updated": datetime.now().isoformat(), "stocks": results}, f)
    return results

def get_analysis(symbol):
    """Full technical analysis from TradingView — the industry standard."""
    from tradingview_ta import TA_Handler, Interval
    try:
        # Try common exchanges
        for exchange in ["NASDAQ", "NYSE", "AMEX"]:
            try:
                h = TA_Handler(symbol=symbol.upper(), screener="america", exchange=exchange, interval=Interval.INTERVAL_1_DAY)
                a = h.get_analysis()
                break
            except:
                continue
        else:
            return {"error": f"Can't find {symbol} on TradingView"}
        
        ind = a.indicators
        # Also get 1h timeframe for short-term signal
        try:
            h1 = TA_Handler(symbol=symbol.upper(), screener="america", exchange=exchange, interval=Interval.INTERVAL_1_HOUR)
            a1 = h1.get_analysis()
            rec_1h = a1.summary["RECOMMENDATION"]
        except:
            rec_1h = "N/A"
        
        signals = []
        rsi = ind.get("RSI", 50)
        if rsi < 30: signals.append("OVERSOLD — potential buy")
        elif rsi > 70: signals.append("OVERBOUGHT — potential sell")
        macd = ind.get("MACD.macd", 0)
        macd_sig = ind.get("MACD.signal", 0)
        if macd > macd_sig: signals.append("MACD bullish")
        else: signals.append("MACD bearish")
        if ind.get("close", 0) > ind.get("SMA50", 0): signals.append("Above SMA50 (bullish)")
        else: signals.append("Below SMA50 (bearish)")
        
        return {
            "symbol": symbol.upper(), "price": round(ind.get("close", 0), 2),
            "rsi": round(rsi, 1),
            "macd": round(macd, 3), "macd_signal": round(macd_sig, 3),
            "sma20": round(ind.get("SMA20", 0), 2), "sma50": round(ind.get("SMA50", 0), 2),
            "volume": int(ind.get("volume", 0)), "avg_volume": int(ind.get("average_volume_10d_calc", 0)),
            "signals": signals,
            "sentiment": a.summary["RECOMMENDATION"],
            "buy_signals": a.summary["BUY"], "sell_signals": a.summary["SELL"],
            "rec_1h": rec_1h
        }
    except Exception as e:
        return {"error": str(e)}

def get_movers():
    """Get today's biggest gainers/losers from watchlist."""
    prices = get_multi_prices()
    if not prices:
        return "No data available."
    sorted_p = sorted(prices, key=lambda x: x.get("change", 0), reverse=True)
    gainers = [f"{s['symbol']} +{s['change']}%" for s in sorted_p[:3] if s.get("change", 0) > 0]
    losers = [f"{s['symbol']} {s['change']}%" for s in sorted_p[-3:] if s.get("change", 0) < 0]
    return {"gainers": gainers, "losers": losers}

# ═══════════════════════════════════════════
# TRADING (Alpaca Paper)
# ═══════════════════════════════════════════

def _get_client():
    """Get Alpaca trading client. Validates keys are set."""
    if not ALPACA_KEY or not ALPACA_SECRET:
        return None
    if len(ALPACA_KEY) < 10 or len(ALPACA_SECRET) < 10:
        return None  # Keys look invalid
    from alpaca.trading.client import TradingClient
    return TradingClient(ALPACA_KEY, ALPACA_SECRET, paper=True)

def get_account():
    """Get account balance, buying power, P&L."""
    client = _get_client()
    if not client:
        return {"error": "Alpaca keys not configured. Set ALPACA_API_KEY and ALPACA_SECRET_KEY."}
    try:
        acc = client.get_account()
        return {
            "equity": float(acc.equity),
            "cash": float(acc.cash),
            "buying_power": float(acc.buying_power),
            "pnl_today": float(acc.equity) - float(acc.last_equity),
            "pnl_percent": round(((float(acc.equity) - float(acc.last_equity)) / float(acc.last_equity)) * 100, 2)
        }
    except Exception as e:
        return {"error": str(e)}

def get_positions():
    """Get all open positions."""
    client = _get_client()
    if not client:
        return {"error": "Alpaca not configured"}
    try:
        positions = client.get_all_positions()
        return [{"symbol": p.symbol, "qty": float(p.qty), "avg_entry": float(p.avg_entry_price),
                 "current": float(p.current_price), "pnl": float(p.unrealized_pl),
                 "pnl_pct": float(p.unrealized_plpc) * 100} for p in positions]
    except Exception as e:
        return {"error": str(e)}

def _round_price(price):
    """Round price: 2 decimals for >$1, 4 decimals for penny stocks."""
    return round(price, 2) if price > 1 else round(price, 4)

def _check_asset(symbol):
    """Query asset details — check if tradable and fractionable."""
    client = _get_client()
    if not client:
        return None
    try:
        asset = client.get_asset(symbol.upper())
        return {"tradable": asset.tradable, "fractionable": asset.fractionable,
                "symbol": asset.symbol, "name": asset.name, "exchange": asset.exchange}
    except:
        return None

def _validate_qty(symbol, qty):
    """Ensure qty is whole number if asset isn't fractionable."""
    if qty == int(qty):
        return int(qty)
    asset = _check_asset(symbol)
    if asset and asset.get("fractionable"):
        return qty  # Fractional OK
    return int(qty)  # Round down to whole shares

def buy_stock(symbol, qty=1, order_type="market", limit_price=None, notional=None):
    """Buy shares. Supports market/limit, fractional, and notional orders. Paper trading only."""
    client = _get_client()
    if not client:
        return "Alpaca not configured. Set ALPACA_API_KEY and ALPACA_SECRET_KEY env vars. Get free keys at https://alpaca.markets"
    from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
    try:
        sym = symbol.upper()
        # Validate fractional qty
        qty = _validate_qty(sym, qty)
        if qty <= 0:
            return f"Can't buy 0 shares of {sym}. Asset may not support fractional orders."

        if order_type == "limit" and limit_price:
            lp = _round_price(float(limit_price))
            req = LimitOrderRequest(symbol=sym, qty=qty, side=OrderSide.BUY,
                                    time_in_force=TimeInForce.DAY, limit_price=lp)
            order = client.submit_order(req)
            msg = f"BUY {qty}x {sym} @ limit ${lp} — Order {order.id}"
        elif notional:
            # Buy by dollar amount (e.g. "$500 of AAPL")
            req = MarketOrderRequest(symbol=sym, notional=round(float(notional), 2),
                                     side=OrderSide.BUY, time_in_force=TimeInForce.DAY)
            order = client.submit_order(req)
            msg = f"BUY ${notional} of {sym} @ market — Order {order.id}"
        else:
            req = MarketOrderRequest(symbol=sym, qty=qty, side=OrderSide.BUY, time_in_force=TimeInForce.DAY)
            order = client.submit_order(req)
            msg = f"BUY {qty}x {sym} @ market — Order {order.id}"
        _log_trade(msg)
        return msg
    except Exception as e:
        err = str(e)
        if "403" in err or "forbidden" in err.lower():
            return f"Buy failed: 403 Forbidden — API keys may be invalid or lack trading permissions. Verify at https://app.alpaca.markets/paper/dashboard/overview"
        if "sub-penny" in err.lower() or "minimum pricing" in err.lower():
            return f"Buy failed: Price ${limit_price} has too many decimals. Use whole cents (e.g. $290.12 not $290.123)."
        if "fractionable" in err.lower() or "fractional" in err.lower():
            return f"Buy failed: {sym} doesn't support fractional shares. Use whole numbers only."
        return f"Buy failed: {e}"

def sell_stock(symbol, qty=1, order_type="market", limit_price=None):
    """Sell shares. Supports market and limit orders. Paper trading only."""
    client = _get_client()
    if not client:
        return "Alpaca not configured. Set ALPACA_API_KEY and ALPACA_SECRET_KEY env vars."
    from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
    try:
        sym = symbol.upper()
        qty = _validate_qty(sym, qty)
        if qty <= 0:
            return f"Can't sell 0 shares of {sym}."

        if order_type == "limit" and limit_price:
            lp = _round_price(float(limit_price))
            req = LimitOrderRequest(symbol=sym, qty=qty, side=OrderSide.SELL,
                                    time_in_force=TimeInForce.DAY, limit_price=lp)
            order = client.submit_order(req)
            msg = f"SELL {qty}x {sym} @ limit ${lp} — Order {order.id}"
        else:
            req = MarketOrderRequest(symbol=sym, qty=qty, side=OrderSide.SELL, time_in_force=TimeInForce.DAY)
            order = client.submit_order(req)
            msg = f"SELL {qty}x {sym} @ market — Order {order.id}"
        _log_trade(msg)
        return msg
    except Exception as e:
        err = str(e)
        if "403" in err or "forbidden" in err.lower():
            return f"Sell failed: 403 Forbidden — API keys may be invalid or lack trading permissions."
        if "sub-penny" in err.lower():
            return f"Sell failed: Price ${limit_price} has too many decimals. Use whole cents."
        return f"Sell failed: {e}"

def close_position(symbol):
    """Close entire position in a stock."""
    client = _get_client()
    if not client:
        return "Alpaca not configured."
    try:
        client.close_position(symbol.upper())
        msg = f"CLOSED all {symbol.upper()} positions"
        _log_trade(msg)
        return msg
    except Exception as e:
        return f"Close failed: {e}"

# ═══════════════════════════════════════════
# WATCHLIST
# ═══════════════════════════════════════════

def add_to_watchlist(symbol):
    wl = _load_watchlist()
    s = symbol.upper()
    if s not in wl:
        wl.append(s)
        _save_watchlist(wl)
    return f"{s} added to watchlist."

def remove_from_watchlist(symbol):
    wl = _load_watchlist()
    s = symbol.upper()
    wl = [x for x in wl if x != s]
    _save_watchlist(wl)
    return f"{s} removed from watchlist."

# ═══════════════════════════════════════════
# VOICE COMMAND ROUTER
# ═══════════════════════════════════════════

def handle_stock_command(text):
    """Omnidirectional — catches ANY natural stock speech. Returns None if not stock-related."""
    t = text.lower().strip()
    
    NAME_MAP = {"apple": "AAPL", "tesla": "TSLA", "nvidia": "NVDA", "microsoft": "MSFT",
                "amazon": "AMZN", "meta": "META", "google": "GOOGL", "alphabet": "GOOGL",
                "amd": "AMD", "netflix": "NFLX", "disney": "DIS", "coinbase": "COIN",
                "palantir": "PLTR", "spotify": "SPOT", "uber": "UBER", "airbnb": "ABNB",
                "boeing": "BA", "intel": "INTC", "walmart": "WMT", "nike": "NKE",
                "spy": "SPY", "qqq": "QQQ", "gamestop": "GME", "nio": "NIO",
                "sofi": "SOFI", "rivian": "RIVN", "lucid": "LCID", "arm": "ARM"}
    
    def _sym(txt):
        words = txt.lower().replace(",", " ").replace("?", "").replace(".", "").split()
        skip = {"price","of","stock","the","is","what","how","much","check","buy","sell",
                "close","share","shares","analyze","analysis","should","i","add","to","from",
                "remove","watchlist","my","a","for","get","show","me","at","it","up","down",
                "going","doing","about","tell","give","plan","trade","trading","market","can",
                "you","look","into","right","now","think","good","bad","any","all","do"}
        for w in words:
            if w in NAME_MAP: return NAME_MAP[w]
        for w in reversed(words):
            if w not in skip and 1 < len(w) <= 5 and w.upper().isalpha(): return w.upper()
        return None
    
    # Price
    if any(w in t for w in ["price","how much","what's","what is","how is","where is","check","quote","trading at","worth"]):
        sym = _sym(t)
        if sym:
            r = get_price(sym)
            if "error" not in r:
                d = "up" if r["change"] > 0 else "down"
                return f"{r['symbol']} is at ${r['price']}, {d} {abs(r['change'])}% today."
    
    # Analysis
    if any(w in t for w in ["analyze","analysis","should i","what do you think","signals","technical","looks like","look at","opinion","thoughts","good buy"]):
        sym = _sym(t)
        if sym:
            r = get_analysis(sym)
            if "error" not in r:
                return f"{r['symbol']}: RSI {r['rsi']}, TradingView says {r['sentiment']} ({r.get('buy_signals',0)} buy vs {r.get('sell_signals',0)} sell). {'. '.join(r['signals'][:2])}. 1h: {r.get('rec_1h','N/A')}."
    
    # Buy
    if any(w in t for w in ["buy","purchase","get some","pick up","go long","enter"]):
        sym = _sym(t)
        qty = 1
        for w in t.split():
            if w.isdigit(): qty = int(w)
        if sym and sym not in ["SOME","LONG","UP"]: return buy_stock(sym, qty)
    
    # Sell
    if any(w in t for w in ["sell","dump","exit","close position","get rid","take profit"]):
        sym = _sym(t)
        qty = 1
        for w in t.split():
            if w.isdigit(): qty = int(w)
        if sym and sym not in ["RID"]:
            if "close" in t or "all" in t: return close_position(sym)
            return sell_stock(sym, qty)
    
    # Portfolio
    if any(w in t for w in ["portfolio","positions","holdings","what do i own","my stocks","what am i holding","open trades"]):
        pos = get_positions()
        if isinstance(pos, dict) and "error" in pos: return pos["error"]
        if not pos: return "No open positions, sir."
        return "Your positions: " + ". ".join(f"{p['symbol']}: {p['qty']} shares, P&L ${p['pnl']:.2f} ({p['pnl_pct']:.1f}%)" for p in pos[:5])
    
    # Account
    if any(w in t for w in ["account","balance","buying power","how much money","equity","cash available","funds"]):
        acc = get_account()
        if "error" in acc: return acc["error"]
        return f"Equity ${acc['equity']:.2f}, cash ${acc['cash']:.2f}, buying power ${acc['buying_power']:.2f}. Today: ${acc['pnl_today']:.2f}."
    
    # Movers
    if any(w in t for w in ["movers","gainers","losers","what's hot","trending","what's moving","biggest moves","top stocks"]):
        m = get_movers()
        if isinstance(m, str): return m
        g = ", ".join(m["gainers"]) if m["gainers"] else "none"
        l = ", ".join(m["losers"]) if m["losers"] else "none"
        return f"Top gainers: {g}. Biggest losers: {l}."
    
    # Scan
    if any(w in t for w in ["scan","find plays","find trades","opportunities","what should i trade","find me","any setups","what looks good","any plays"]):
        result = full_market_scan()
        picks = result.get("top_picks", [])
        return ("Scan complete. " + ". ".join(picks[:4])) if picks else "No strong signals right now."
    
    # Trade plan
    if any(w in t for w in ["trade plan","plan for","how to trade","give me a play","entry and exit","setup for"]):
        sym = _sym(t)
        if sym: return get_ai_trade_plan(sym)
    
    # Watchlist
    if "watchlist" in t or "watch list" in t:
        if any(w in t for w in ["add","put"]):
            sym = _sym(t)
            if sym: return add_to_watchlist(sym)
        elif any(w in t for w in ["remove","delete","take off"]):
            sym = _sym(t)
            if sym: return remove_from_watchlist(sym)
        else: return f"Your watchlist: {', '.join(_load_watchlist())}"
    
    # Stop loss
    if any(w in t for w in ["stop loss","stop-loss","stoploss","set stop","protect"]):
        sym = _sym(t)
        price = None
        import re as _re
        m = _re.search(r'\$?([\d.]+)', t.replace(sym.lower() if sym else "", ""))
        if m: price = float(m.group(1))
        if sym and price: return set_stop_loss(sym, price)
        if sym: return f"Set stop loss for {sym} at what price?"
    
    # Price alerts
    if any(w in t for w in ["alert","notify","tell me when","let me know"]):
        sym = _sym(t)
        import re as _re
        m = _re.search(r'\$?([\d.]+)', t.replace(sym.lower() if sym else "", ""))
        direction = "below" if any(w in t for w in ["below","under","drops","falls","dips"]) else "above"
        if sym and m: return set_alert(sym, float(m.group(1)), direction)
    
    # Check alerts
    if any(w in t for w in ["check alert","my alert","active alert","any alert"]):
        triggered = check_alerts()
        if triggered:
            return "Triggered alerts: " + ". ".join(f"{a['symbol']} hit ${a['triggered_at']}" for a in triggered)
        return "No alerts triggered yet."
    
    # Dollar-amount buy ("buy $500 of AAPL")
    if any(w in t for w in ["buy","purchase"]):
        import re as _re
        m = _re.search(r'\$(\d+(?:\.\d+)?)\s+(?:of|worth|in)\s+', t)
        if m:
            sym = _sym(t)
            if sym: return buy_stock(sym, notional=float(m.group(1)))
    
    return None  # Not stock-related



# ═══════════════════════════════════════════
# AGGRESSIVE SCANNER — finds money-making setups
# ═══════════════════════════════════════════

SCAN_UNIVERSE = [
    "TSLA", "NVDA", "AMD", "MARA", "COIN", "PLTR", "SOFI", "NIO", "RIVN",
    "GME", "AMC", "MSTR", "SMCI", "ARM", "IONQ", "RGTI", "QUBT",
    "SPY", "QQQ", "TQQQ", "SQQQ", "SOXL", "UVXY",
    "RIOT", "BITF", "HUT", "AI", "BBAI", "SYM",
]

ALERTS_FILE = os.path.expanduser("~/jarvis_alerts.json")

def _save_alert(alert):
    try:
        alerts = json.load(open(ALERTS_FILE))
    except:
        alerts = []
    alerts.append(alert)
    json.dump(alerts[-50:], open(ALERTS_FILE, "w"), indent=2)

def scan_momentum():
    """TradingView-powered scan — find STRONG BUY signals across multiple timeframes."""
    from tradingview_ta import TA_Handler, Interval
    results = []
    for sym in list(set(SCAN_UNIVERSE)):
        try:
            for exchange in ["NASDAQ", "NYSE", "AMEX"]:
                try:
                    h = TA_Handler(symbol=sym, screener="america", exchange=exchange, interval=Interval.INTERVAL_1_HOUR)
                    a = h.get_analysis()
                    break
                except:
                    continue
            else:
                continue
            rec = a.summary["RECOMMENDATION"]
            buys = a.summary["BUY"]
            sells = a.summary["SELL"]
            rsi = a.indicators.get("RSI", 50)
            price = a.indicators.get("close", 0)
            change = a.indicators.get("change", 0)
            
            # Strong signal = lots of buy or sell indicators agreeing
            if buys >= 14 or sells >= 14:
                direction = "LONG" if buys > sells else "SHORT"
                confidence = min(95, int(max(buys, sells) * 5))
                results.append({"symbol": sym, "signal": direction, "confidence": confidence,
                    "move_pct": round(change, 2), "vol_spike": round(buys / max(sells, 1), 1),
                    "rsi": round(rsi, 1), "price": round(price, 2), "rec": rec})
        except:
            continue
    results.sort(key=lambda x: x["confidence"], reverse=True)
    return results[:10]

def scan_breakouts():
    """Find stocks breaking resistance/support on daily chart."""
    results = []
    for sym in list(set(SCAN_UNIVERSE))[:20]:
        try:
            df = yf.download(sym, period="1mo", progress=False)
            if df.empty or len(df) < 10:
                continue
            close = df["Close"].iloc[:, 0] if len(df["Close"].shape) > 1 else df["Close"]
            high = df["High"].iloc[:, 0] if len(df["High"].shape) > 1 else df["High"]
            low = df["Low"].iloc[:, 0] if len(df["Low"].shape) > 1 else df["Low"]
            resistance = high.iloc[-11:-1].max()
            support = low.iloc[-11:-1].min()
            current, prev = float(close.iloc[-1]), float(close.iloc[-2])

            if current > resistance and prev <= resistance:
                results.append({"symbol": sym, "type": "BREAKOUT_UP", "price": round(current, 2),
                    "level": round(float(resistance), 2), "target": round(current + (float(resistance) - float(support)), 2)})
            elif current < support and prev >= support:
                results.append({"symbol": sym, "type": "BREAKDOWN", "price": round(current, 2),
                    "level": round(float(support), 2), "target": round(current - (float(resistance) - float(support)), 2)})
        except:
            continue
    return results

def scan_oversold_bounces():
    """Find oversold stocks ready to bounce — high win-rate scalps."""
    results = []
    for sym in list(set(SCAN_UNIVERSE))[:20]:
        try:
            df = yf.download(sym, period="1mo", progress=False)
            if df.empty or len(df) < 14:
                continue
            close = df["Close"].iloc[:, 0] if len(df["Close"].shape) > 1 else df["Close"]
            rsi_series = ta.momentum.RSIIndicator(close).rsi()
            rsi, rsi_prev = rsi_series.iloc[-1], rsi_series.iloc[-2]
            bb = ta.volatility.BollingerBands(close)
            lower = bb.bollinger_lband().iloc[-1]
            mid = bb.bollinger_mavg().iloc[-1]

            if rsi < 35 and rsi > rsi_prev and float(close.iloc[-1]) <= lower * 1.02:
                results.append({"symbol": sym, "type": "OVERSOLD_BOUNCE", "rsi": round(rsi, 1),
                    "price": round(float(close.iloc[-1]), 2), "target": round(float(mid), 2),
                    "stop": round(float(close.iloc[-1]) * 0.97, 2)})
        except:
            continue
    return results

def full_market_scan():
    """Run ALL scanners — returns best opportunities NOW."""
    _log_trade("🔍 Running full market scan...")
    momentum = scan_momentum()
    breakouts = scan_breakouts()
    bounces = scan_oversold_bounces()

    top_picks = []
    for m in momentum[:3]:
        top_picks.append(f"🔥 {m['symbol']} {m['signal']} — {m['move_pct']:+.1f}%, {m['vol_spike']}x vol, {m['confidence']}% conf")
    for b in breakouts[:2]:
        top_picks.append(f"💥 {b['symbol']} {b['type']} above ${b['level']} → target ${b['target']}")
    for o in bounces[:2]:
        top_picks.append(f"🎯 {o['symbol']} BOUNCE RSI {o['rsi']}, entry ${o['price']} → ${o['target']}")

    scan_result = {"timestamp": datetime.now().isoformat(), "momentum": momentum[:5],
                   "breakouts": breakouts[:5], "bounces": bounces[:5], "top_picks": top_picks}
    json.dump(scan_result, open("/tmp/jarvis_scan.json", "w"), indent=2)

    for m in momentum:
        if m["confidence"] >= 80:
            _save_alert({"time": datetime.now().isoformat(), "type": "MOMENTUM",
                        "symbol": m["symbol"], "signal": m["signal"],
                        "confidence": m["confidence"], "price": m["price"]})
    _log_trade(f"✅ Scan: {len(momentum)} momentum, {len(breakouts)} breakouts, {len(bounces)} bounces")
    return scan_result

def get_ai_trade_plan(symbol):
    """Gemini-powered aggressive trade plan with entry/target/stop."""
    analysis = get_analysis(symbol)
    if "error" in analysis:
        return f"Can't analyze {symbol}: {analysis['error']}"
    from google import genai
    client = genai.Client(vertexai=True, project='YOUR_GCP_PROJECT_ID', location='global')
    prompt = (f"Calculated trader analysis for {analysis['symbol']} @ ${analysis['price']}. "
              f"RSI: {analysis['rsi']}, MACD: {analysis['macd']}, SMA20: ${analysis['sma20']}, SMA50: ${analysis['sma50']}. "
              f"TradingView recommendation: {analysis.get('sentiment','N/A')} ({analysis.get('buy_signals',0)} buy vs {analysis.get('sell_signals',0)} sell indicators). "
              f"Signals: {', '.join(analysis['signals'])}. "
              f"Give in 3-4 sentences: BUY/SELL/WAIT with reasoning, entry price, target price, stop loss. "
              f"Be calculated — only recommend if risk/reward is at least 2:1. If unclear, say WAIT.")
    try:
        resp = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        return resp.text.strip() if resp.text else "Analysis failed."
    except Exception as e:
        return f"AI error: {e}"


def set_stop_loss(symbol, stop_price, qty=None):
    """Set a stop-loss order. If qty=None, closes full position."""
    client = _get_client()
    if not client:
        return "Alpaca not configured."
    from alpaca.trading.requests import StopOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
    try:
        if qty is None:
            positions = client.get_all_positions()
            pos = next((p for p in positions if p.symbol == symbol.upper()), None)
            if not pos: return f"No open position in {symbol.upper()}"
            qty = int(float(pos.qty))
        sp = _round_price(float(stop_price))
        req = StopOrderRequest(symbol=symbol.upper(), qty=qty, side=OrderSide.SELL,
                               time_in_force=TimeInForce.GTC, stop_price=sp)
        order = client.submit_order(req)
        msg = f"STOP-LOSS {qty}x {symbol.upper()} @ ${sp} — Order {order.id}"
        _log_trade(msg)
        return msg
    except Exception as e:
        return f"Stop-loss failed: {e}"

def set_alert(symbol, target_price, direction="above"):
    """Set a price alert. Saves to ~/jarvis_alerts.json."""
    alerts_file = os.path.expanduser("~/jarvis_alerts.json")
    try:
        alerts = json.load(open(alerts_file))
    except:
        alerts = []
    alert = {"symbol": symbol.upper(), "target": float(target_price),
             "direction": direction, "created": datetime.now().isoformat(), "triggered": False}
    alerts.append(alert)
    json.dump(alerts, open(alerts_file, "w"), indent=2)
    return f"Alert set: {symbol.upper()} {direction} ${target_price}"

def check_alerts():
    """Check all price alerts, return triggered ones."""
    alerts_file = os.path.expanduser("~/jarvis_alerts.json")
    try:
        alerts = json.load(open(alerts_file))
    except:
        return []
    triggered = []
    remaining = []
    for a in alerts:
        if a.get("triggered"): continue
        r = get_price(a["symbol"])
        if "error" in r:
            remaining.append(a)
            continue
        price = r["price"]
        hit = (a["direction"] == "above" and price >= a["target"]) or \
              (a["direction"] == "below" and price <= a["target"])
        if hit:
            a["triggered"] = True
            a["triggered_at"] = price
            a["triggered_time"] = datetime.now().isoformat()
            triggered.append(a)
        else:
            remaining.append(a)
    json.dump(remaining + triggered, open(alerts_file, "w"), indent=2)
    return triggered

def get_scheduled_scan_config():
    """Get scan schedule config — market open and close scans."""
    return {"scans": [
        {"time": "09:30", "tz": "US/Eastern", "type": "open_scan"},
        {"time": "15:45", "tz": "US/Eastern", "type": "close_scan"},
    ], "interval_min": 30, "universe_size": len(SCAN_UNIVERSE)}

def run_scheduled_scan():
    """Execute a scheduled scan — called by scheduler daemon."""
    result = full_market_scan()
    triggered = check_alerts()
    if triggered:
        result["triggered_alerts"] = triggered
    json.dump(result, open("/tmp/jarvis_scan.json", "w"), indent=2)
    return result

def get_hud_stock_data():
    """Compact JSON for HUD display — positions, alerts, last scan."""
    data = {"ts": datetime.now().isoformat()}
    try:
        data["positions"] = get_positions() if ALPACA_KEY else []
    except:
        data["positions"] = []
    try:
        data["scan"] = json.load(open("/tmp/jarvis_scan.json"))
    except:
        data["scan"] = {}
    try:
        data["alerts"] = json.load(open(os.path.expanduser("~/jarvis_alerts.json")))
    except:
        data["alerts"] = []
    acc = get_account()
    data["account"] = acc if "error" not in acc else {}
    return data


if __name__ == "__main__":
    # Quick test
    print("=== Jarvis Stocks Module ===")
    print(get_price("AAPL"))
    print(get_analysis("TSLA"))
    print(get_movers())
