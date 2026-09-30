"""Five-file export importer. Additive: parser.py is untouched. Dedupes by trade/order content, not filename."""
import csv, io, re
from datetime import datetime

CLOSE_RE = re.compile(r"Close (long|short) position for symbol ([^ ]+) at price ([\d.]+) "
                      r"for ([\d.]+) units\. Position AVG Price was ([\d.]+).*?point value: ([\d.]+)")

def _rows(raw):
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig", errors="replace"))))

def _num(s):
    s = (s or "").replace(",", "").replace("\u2212", "-").replace("USD", "").replace("%", "").strip()
    try: return float(s)
    except ValueError: return None

def classify(raw):
    lines = raw.decode("utf-8-sig", errors="replace").splitlines()
    if not lines: return None
    cols = set(next(csv.reader([lines[0]])))
    if {"Balance before", "Balance after"} <= cols: return "balance"
    if {"Closing time", "Commission"} <= cols: return "order_history"
    if "Unrealized PnL (value)" in cols: return "positions"
    if {"Instruction", "Placing time"} <= cols: return "working_orders"
    if cols == {"Time", "Text"}: return "activity"
    return None

def parse_balance(raw):
    out = []
    for r in _rows(raw):
        m = CLOSE_RE.search(r.get("Action", ""))
        if not m: continue
        d, sym, exit_p, qty, avg, pv = m.groups()
        pnl = float(r["Realized PnL (value)"])
        out.append({"trade_time": r["Time"], "symbol": sym, "direction": d, "qty": float(qty),
                    "entry_price": float(avg), "exit_price": float(exit_p), "pnl": pnl,
                    "point_value": float(pv), "holding_minutes": None,
                    "source_key": f"close:{r['Time']}:{sym}:{qty}:{exit_p}:{pnl}"})
    return out

def parse_order_history(raw):
    return [{"execution_time": r["Closing time"], "symbol": r["Symbol"], "side": r["Side"],
             "order_type": r["Type"], "qty": _num(r["Quantity"]), "price": _num(r["Fill price"]),
             "status": r["Status"], "order_id": r["Order ID"]} for r in _rows(raw)]

def parse_positions(raw):
    return [{"symbol": r["Symbol"], "side": r["Side"], "qty": _num(r["Quantity"]),
             "avg_price": _num(r["Avg fill price"]), "stop_loss": _num(r["Stop loss"]),
             "take_profit": _num(r["Take profit"]), "unrealized": _num(r["Unrealized PnL (value)"])}
            for r in _rows(raw)]

def risk_status(positions):
    if not positions: return ["Flat: no open positions."]
    return [f"{p['side']} {p['qty']:g} {p['symbol']}: unrealized ${p['unrealized']:,.2f}"
            + ("; NO STOP LOSS set." if p["stop_loss"] is None else f"; stop at {p['stop_loss']}.")
            for p in positions]

def infer_holding(trades, execs):
    """Inferred (not exact): minutes since the nearest earlier same-side entry fill."""
    f = lambda s: datetime.fromisoformat(s)
    for t in trades:
        want = "buy" if t["direction"] == "long" else "sell"
        gaps = [(f(t["trade_time"]) - f(e["execution_time"])).total_seconds() / 60
                for e in execs if e["symbol"] == t["symbol"] and e["status"].lower() == "filled"
                and e["side"].lower() == want and f(e["execution_time"]) < f(t["trade_time"])]
        if gaps: t["holding_minutes"] = round(min(gaps), 2)
    return trades

def import_bundle(files):
    """files: {filename: bytes}. Returns parsed pieces plus any files we could not classify."""
    b = {"trades": [], "executions": [], "positions": [], "unrecognized": []}
    for name, raw in files.items():
        kind = classify(raw)
        if kind == "balance": b["trades"] = parse_balance(raw)
        elif kind == "order_history": b["executions"] = parse_order_history(raw)
        elif kind == "positions": b["positions"] = parse_positions(raw)
        elif kind not in ("working_orders", "activity"): b["unrecognized"].append(name)
    infer_holding(b["trades"], b["executions"])
    return b

def save_bundle(con, b, source="bundle"):
    con.execute("""CREATE TABLE IF NOT EXISTS open_positions (symbol TEXT, side TEXT, qty REAL,
        avg_price REAL, stop_loss REAL, take_profit REAL, unrealized REAL, captured_at TEXT)""")
    nt = ne = 0
    for t in b["trades"]:
        if con.execute("SELECT 1 FROM trades WHERE trade_time=? AND symbol=? AND qty=? AND exit_price=? AND pnl=?",
                       (t["trade_time"], t["symbol"], t["qty"], t["exit_price"], t["pnl"])).fetchone(): continue
        con.execute("""INSERT OR IGNORE INTO trades (trade_time,symbol,direction,qty,entry_price,exit_price,pnl,
            point_value,holding_minutes,strategy,setup,notes,source,source_key) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (t["trade_time"], t["symbol"], t["direction"], t["qty"], t["entry_price"], t["exit_price"], t["pnl"],
             t["point_value"], t["holding_minutes"], "", "", "", source, t["source_key"]))
        nt += 1
    for e in b["executions"]:
        if con.execute("SELECT 1 FROM executions WHERE order_id=?", (e["order_id"],)).fetchone(): continue
        con.execute("""INSERT INTO executions (execution_time,symbol,side,order_type,qty,price,status,order_id,source)
            VALUES (?,?,?,?,?,?,?,?,?)""", (e["execution_time"], e["symbol"], e["side"], e["order_type"],
            e["qty"], e["price"], e["status"], e["order_id"], source)); ne += 1
    if b["positions"] or any(True for _ in [0] if b["trades"]):
        con.execute("DELETE FROM open_positions")  # snapshot semantics: latest file wins
        for p in b["positions"]:
            con.execute("INSERT INTO open_positions VALUES (?,?,?,?,?,?,?,datetime('now'))",
                        (p["symbol"], p["side"], p["qty"], p["avg_price"], p["stop_loss"], p["take_profit"], p["unrealized"]))
    con.commit()
    return {"trades": nt, "executions": ne}
