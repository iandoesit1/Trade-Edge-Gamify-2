"""Metrics, Process Discipline, achievements, missions, skill tree. All conditions are data-driven and configurable."""
import pandas as pd
from datetime import date, timedelta
from game import unlock, unlocked, season_window, SEASON

def week_start(d): return (d - timedelta(days=d.weekday())).isoformat()

def metrics(df, reviews):
    """df: trades DataFrame (may be empty). reviews: [(kind, day, no_trade)]."""
    d = df.copy() if len(df) else pd.DataFrame(columns=["trade_time","setup","notes","planned_stop","planned_target","followed_plan","mistake","pnl"])
    txt = lambda c: d[c].fillna("").astype(str).str.strip()
    setup, notes, fp, mis = txt("setup"), txt("notes"), txt("followed_plan").str.lower(), txt("mistake")
    jour = (setup != "") & (notes.str.len() >= 20)
    per_setup = d[setup != ""].groupby(setup[setup != ""]).size()
    days = set(pd.to_datetime(d["trade_time"]).dt.date.astype(str)) if len(d) else set()
    post_days = {r[1] for r in reviews if r[0] == "post_session"}
    return {"n_trades": len(d), "journaled": int(jour.sum()),
        "plan_doc": int((d["planned_stop"].notna() & d["planned_target"].notna()).sum()),
        "stops": int(d["planned_stop"].notna().sum()), "targets": int(d["planned_target"].notna().sum()),
        "yes": int((fp == "yes").sum()), "no": int((fp == "no").sum()), "answered": int(fp.isin(["yes", "no"]).sum()),
        "mistakes": int((mis != "").sum()), "distinct_mistakes": int(mis[mis != ""].str.lower().nunique()),
        "max_setup_n": int(per_setup.max()) if len(per_setup) else 0, "setups_ge5": int((per_setup >= 5).sum()),
        "hours": int(pd.to_datetime(d["trade_time"]).dt.hour.nunique()) if len(d) else 0,
        "post": sum(r[0] == "post_session" for r in reviews), "weekly": sum(r[0] == "weekly" for r in reviews),
        "notrade": sum(bool(r[2]) for r in reviews),
        "review_weeks": len({week_start(date.fromisoformat(r[1])) for r in reviews if r[0] == "weekly"}),
        "expect_ok": int(len(d) >= 30 and pd.to_numeric(d["pnl"], errors="coerce").mean() > 0),
        "post_days": len(post_days & days), "trade_days": len(days)}

DISCIPLINE_WEIGHTS = {"Journal completeness": 0.3, "Plan documented": 0.25,
                      "Plan adherence (self-reported)": 0.3, "Post-session review coverage": 0.15}

def discipline(m, weights=DISCIPLINE_WEIGHTS):
    """Process score 0-100 from process data only. Components with no data are excluded, not scored as zero."""
    n = m["n_trades"]
    comp = {"Journal completeness": m["journaled"] / n if n else None,
            "Plan documented": m["plan_doc"] / n if n else None,
            "Plan adherence (self-reported)": m["yes"] / m["answered"] if m["answered"] else None,
            "Post-session review coverage": m["post_days"] / m["trade_days"] if m["trade_days"] else None}
    avail = {k: v for k, v in comp.items() if v is not None}
    total = sum(weights[k] for k in avail)
    score = round(100 * sum(v * weights[k] for k, v in avail.items()) / total, 1) if total else None
    return score, comp

# (id, name, category, rarity, description, metric, target, xp, hidden)
ACHIEVEMENTS = [
 ("rule_keeper", "THE RULE KEEPER", "Discipline", "Rare", "Follow your written plan on 10 trades, wins or losses (self-reported).", "yes", 10, 50, False),
 ("precision", "PRECISION", "Discipline", "Rare", "Document a planned stop and target on 10 trades.", "plan_doc", 10, 50, False),
 ("historian", "THE HISTORIAN", "Journaling", "Common", "Journal 10 trades with a setup and written reasoning.", "journaled", 10, 40, False),
 ("first_debrief", "FIRST DEBRIEF", "Journaling", "Common", "Complete a post-session review.", "post", 1, 20, False),
 ("pattern", "PATTERN RECOGNITION", "Strategy Mastery", "Rare", "Document 5+ trades in each of two setups so they can be compared.", "setups_ge5", 2, 60, False),
 ("edge_architect", "EDGE ARCHITECT", "Strategy Mastery", "Epic", "Document 30 trades of one setup, enough to start judging its expectancy.", "max_setup_n", 30, 100, False),
 ("honest_mirror", "HONEST MIRROR", "Self-Awareness", "Rare", "Log an execution mistake on 5 trades (self-reported).", "mistakes", 5, 60, False),
 ("long_game", "THE LONG GAME", "Consistency", "Epic", "Complete weekly reviews in 3 different weeks.", "review_weeks", 3, 80, False),
 ("rest", "REST IS STRATEGY", "Recovery and Improvement", "Rare", "Hidden. Reveals itself when earned.", "notrade", 1, 40, True),
 ("expectancy", "POSITIVE SAMPLE", "Performance Milestones", "Epic", "Positive average P&L per trade over 30+ trades. Financial, and separate from discipline.", "expect_ok", 1, 50, False)]
ICON = {"Discipline": "🛡️", "Journaling": "📓", "Strategy Mastery": "🧭", "Self-Awareness": "🪞",
        "Consistency": "⏳", "Recovery and Improvement": "🌿", "Performance Milestones": "📈"}

# (branch, name, what unlocks it, metric, threshold); nodes unlock in order within a branch
TREE = [
 ("Setup Recognition", "Label your setups", "Tag 10 trades with a setup", "journaled", 10),
 ("Setup Recognition", "Compare two setups", "5+ documented trades in two setups", "setups_ge5", 2),
 ("Setup Recognition", "Meaningful sample", "30 documented trades in one setup", "max_setup_n", 30),
 ("Entry Precision", "Write the plan", "Plan documented on 5 trades", "plan_doc", 5),
 ("Entry Precision", "Grade your adherence", "Answer 'followed plan?' on 10 trades", "answered", 10),
 ("Entry Precision", "Plan vs no plan", "5+ trades in each group", "no", 5),
 ("Exit Management", "Set targets", "Planned target on 5 trades", "targets", 5),
 ("Exit Management", "Target and stop pairs", "Plan documented on 10 trades", "plan_doc", 10),
 ("Exit Management", "Exit sample", "Plan documented on 30 trades", "plan_doc", 30),
 ("Risk Control", "Define risk", "Planned stop on 5 trades", "stops", 5),
 ("Risk Control", "Consistent stops", "Planned stop on 15 trades", "stops", 15),
 ("Risk Control", "Risk history", "Planned stop on 30 trades", "stops", 30),
 ("Session Selection", "Enough data", "10 imported trades", "n_trades", 10),
 ("Session Selection", "Multiple windows", "30 trades across 3+ hours", "hours", 3),
 ("Session Selection", "Session sample", "100 imported trades", "n_trades", 100),
 ("Trade Psychology", "Name a mistake", "Log a mistake on 3 trades", "mistakes", 3),
 ("Trade Psychology", "Find the pattern", "3+ distinct mistake labels", "distinct_mistakes", 3),
 ("Trade Psychology", "Track it over time", "Log a mistake on 10 trades", "mistakes", 10),
 ("Statistical Validation", "First sample", "30 trades", "n_trades", 30),
 ("Statistical Validation", "Solid sample", "100 trades", "n_trades", 100),
 ("Statistical Validation", "Durable edge test", "200 trades", "n_trades", 200)]

def node_id(i): return f"{TREE[i][0]}|{TREE[i][1]}"

# (id, name, scope, xp_kind, target, xp) — counts come from real, timestamped records
MISSIONS = [("wk_journal", "Journal 5 trades with reasoning", "week", "journal_entry", 5, 40),
            ("wk_debrief", "Complete a post-session review", "week", "review_post_session", 1, 20),
            ("wk_weekly", "Complete your weekly review", "week", "review_weekly", 1, 30),
            ("ss_mistakes", "Log 3 execution mistakes", "season", "mistake_logged", 3, 60),
            ("ss_plans", "Document the plan on 10 trades", "season", "plan_documented", 10, 60)]

def mission_progress(con, today):
    ws, (s0, s1) = week_start(today), season_window()
    out = []
    for mid, name, scope, kind, target, xp in MISSIONS:
        a, b = (ws, "9999") if scope == "week" else (s0, s1)
        n = con.execute("SELECT COUNT(*) FROM xp_events WHERE kind=? AND awarded_at>=? AND awarded_at<?", (kind, a, b)).fetchone()[0]
        out.append({"key": f"{SEASON['id']}:{mid}:{ws if scope == 'week' else 'season'}", "name": name,
                    "scope": "Weekly challenge" if scope == "week" else "Season mastery", "n": min(n, target), "target": target, "xp": xp})
    return out

def process(con, m, today):
    """Idempotent: unlock whatever is newly earned and return display names (toast once, never on rerun)."""
    new = []
    for id_, name, _c, _r, _d, key, target, xp, _h in ACHIEVEMENTS:
        if m[key] >= target and unlock(con, "achievement", id_, f"{key} reached {target}", xp): new.append(f"Achievement: {name}")
    done = unlocked(con, "node")
    for i, (_b, name, _n, key, target) in enumerate(TREE):
        prev_ok = i == 0 or TREE[i - 1][0] != TREE[i][0] or node_id(i - 1) in done
        if prev_ok and m[key] >= target and node_id(i) not in done:
            unlock(con, "node", node_id(i), f"{key} reached {target}", 15); done[node_id(i)] = 1; new.append(f"Skill unlocked: {name}")
    for mp in mission_progress(con, today):
        if mp["n"] >= mp["target"] and unlock(con, "mission", mp["key"], mp["name"], mp["xp"]): new.append(f"Mission complete: {mp['name']}")
    return new
