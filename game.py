"""Pure progression logic (no Streamlit). XP never reads P&L; the ledger is append-only."""
import hashlib
from datetime import datetime, timezone

CONFIG = {
    "base_xp": 100, "growth": 1.25,  # XP to go from level L to L+1 = base * growth**(L-1)
    "ranks": [(1, "Initiate"), (5, "Apprentice"), (10, "Technician"),
              (15, "Specialist"), (25, "Elite"), (40, "Master")],
    "journal_xp": 10, "journal_min_note_chars": 20,
}

def xp_to_next(level, cfg=CONFIG):
    return round(cfg["base_xp"] * cfg["growth"] ** (level - 1))

def level_info(total_xp, cfg=CONFIG):
    level, remaining = 1, max(0, int(total_xp))
    while remaining >= (need := xp_to_next(level, cfg)):
        remaining -= need
        level += 1
    rank = [n for lv, n in cfg["ranks"] if level >= lv][-1]
    return {"level": level, "rank": rank, "into": remaining, "needed": need,
            "pct": remaining / need, "total": max(0, int(total_xp))}

def trade_key(t):
    """Content-based id, so re-importing the same trade from another file cannot re-award XP."""
    raw = f"{t['trade_time']}|{t['symbol']}|{t['direction']}|{t['qty']}|{t['exit_price']}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]

def journal_events(trades, cfg=CONFIG):
    """XP for a journal entry with a setup label and written reasoning. Ignores P&L entirely."""
    out = []
    for t in trades:
        setup = (t.get("setup") or "").strip()
        notes = (t.get("notes") or "").strip()
        if setup and len(notes) >= cfg["journal_min_note_chars"]:
            k = trade_key(t)
            out.append({"event_key": f"journal:{k}", "kind": "journal_entry",
                        "xp": cfg["journal_xp"], "ref": k,
                        "reason": "Journal entry with setup and written reasoning"})
    return out

def init_game_db(con):
    con.execute("""CREATE TABLE IF NOT EXISTS xp_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, event_key TEXT UNIQUE NOT NULL,
        awarded_at TEXT NOT NULL, kind TEXT, xp INTEGER NOT NULL CHECK (xp >= 0),
        reason TEXT, ref TEXT)""")
    con.execute("CREATE TABLE IF NOT EXISTS game_state (key TEXT PRIMARY KEY, value TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS unlocks (kind TEXT, id TEXT, unlocked_at TEXT, reason TEXT, PRIMARY KEY(kind,id))")
    con.execute("CREATE TABLE IF NOT EXISTS reviews (kind TEXT, day TEXT, text TEXT, no_trade INTEGER, created_at TEXT, PRIMARY KEY(kind,day))")
    con.execute("CREATE TABLE IF NOT EXISTS journal_audit (trade_id INTEGER, field TEXT, old TEXT, new TEXT, changed_at TEXT)")
    con.commit()

def apply_events(con, events):
    now, added = datetime.now(timezone.utc).isoformat(timespec="seconds"), 0
    for e in events:
        cur = con.execute(
            "INSERT OR IGNORE INTO xp_events (event_key,awarded_at,kind,xp,reason,ref) VALUES (?,?,?,?,?,?)",
            (e["event_key"], now, e["kind"], e["xp"], e["reason"], e.get("ref")))
        added += cur.rowcount
    con.commit()
    return added

def total_xp(con):
    return con.execute("SELECT COALESCE(SUM(xp),0) FROM xp_events").fetchone()[0]

def recent_events(con, n=8):
    return con.execute("SELECT awarded_at,xp,reason FROM xp_events ORDER BY id DESC LIMIT ?", (n,)).fetchall()

def levelup_pending(con, level):
    """True exactly once per new level, so the celebration cannot replay on Streamlit reruns."""
    row = con.execute("SELECT value FROM game_state WHERE key='last_seen_level'").fetchone()
    last = int(row[0]) if row else 1
    if level > last:
        con.execute("INSERT OR REPLACE INTO game_state VALUES ('last_seen_level', ?)", (str(level),))
        con.commit()
        return True
    return False

def _ev(key, kind, xp, ref, reason):
    return {"event_key": key, "kind": kind, "xp": xp, "ref": ref, "reason": reason}

def trade_events(trades, cfg=CONFIG):
    """Journal + plan documentation + self-reported adherence. Never reads P&L."""
    out = journal_events(trades, cfg)
    for t in trades:
        k, fp = trade_key(t), (t.get("followed_plan") or "").lower()
        if t.get("planned_stop") is not None and t.get("planned_target") is not None:
            out.append(_ev(f"plan:{k}", "plan_documented", 5, k, "Documented planned stop and target"))
        if fp == "yes":
            out.append(_ev(f"adherence:{k}", "plan_followed", 10, k, "Followed the written plan (self-reported)"))
        if fp == "no" and (t.get("mistake") or "").strip():
            out.append(_ev(f"mistake:{k}", "mistake_logged", 5, k, "Logged an execution mistake honestly (self-reported)"))
    return out

REVIEW_XP = {"premarket": 15, "post_session": 15, "weekly": 30}

def add_review(con, kind, day, text, no_trade=False):
    """A no-trade review earns the same XP as any other review: not trading is never punished."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cur = con.execute("INSERT OR IGNORE INTO reviews VALUES (?,?,?,?,?)", (kind, day, text, int(no_trade), now))
    if cur.rowcount and len(text.strip()) >= 20:
        apply_events(con, [_ev(f"review:{kind}:{day}", f"review_{kind}", REVIEW_XP[kind], day, f"Completed {kind.replace('_',' ')} review")])
    con.commit()
    return bool(cur.rowcount)

def unlock(con, kind, id_, reason, xp=0):
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cur = con.execute("INSERT OR IGNORE INTO unlocks VALUES (?,?,?,?)", (kind, id_, now, reason))
    if cur.rowcount and xp:
        apply_events(con, [_ev(f"{kind}:{id_}", f"{kind}_unlock", xp, id_, reason)])
    con.commit()
    return bool(cur.rowcount)

def unlocked(con, kind):
    return {r[0]: r[1] for r in con.execute("SELECT id, unlocked_at FROM unlocks WHERE kind=?", (kind,))}

SEASON = {"id": "S1", "name": "Season 1 · Foundations", "start": "2026-09-28", "weeks": 4, "tier_xp": 100,
    "rewards": [(1, "Title: Initiate of Process"), (2, "Emblem: Graphite Hex"), (3, "Accent: Gold"),
                (4, "Title: Rule Keeper"), (5, "Frame: Silver Edge"), (6, "Accent: Violet"),
                (7, "Title: Clear-Eyed"), (8, "Emblem: Teal Sigil"), (9, "Accent: Crimson"),
                (10, "Title: Season 1 Finisher")]}

def season_window(S=SEASON):
    from datetime import date, timedelta
    a = date.fromisoformat(S["start"]); return a.isoformat(), (a + timedelta(weeks=S["weeks"])).isoformat()

def season_xp(con, S=SEASON):
    a, b = season_window(S)
    return con.execute("SELECT COALESCE(SUM(xp),0) FROM xp_events WHERE awarded_at>=? AND awarded_at<?", (a, b)).fetchone()[0]

def season_tier(xp, S=SEASON):
    return min(len(S["rewards"]), xp // S["tier_xp"])
