import sqlite3
from datetime import date, datetime
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st
from analytics import (summary_stats, equity_curve, grouped_stats, edge_scorecard,
                       risk_metrics, time_buckets, recommendations)
from importer import import_bundle, save_bundle, risk_status
from game import (init_game_db, trade_events, apply_events, total_xp, level_info, recent_events, levelup_pending,
                  add_review, unlocked, season_xp, season_tier, season_window, SEASON)
from rules import (metrics, discipline, process, mission_progress, ACHIEVEMENTS, ICON, TREE, node_id, week_start)
from theme import CSS, CSS2, hud_html, card

DB = Path("trading_journal.sqlite3")
st.set_page_config(page_title="Gaüd Trade Edge", page_icon="📈", layout="wide")
NEW_COLS = {"planned_stop": "REAL", "planned_target": "REAL", "followed_plan": "TEXT", "mistake": "TEXT"}
EDIT = ["strategy", "setup", "notes"] + list(NEW_COLS)
ACCENTS = {"Teal": "#38d6c4", "Gold": "#c8a45a", "Violet": "#8b7cf6", "Crimson": "#e05a6d"}
ACCENT_TIER = {"Gold": 3, "Violet": 6, "Crimson": 9}

def get_conn(): return sqlite3.connect(DB)
def nn(v): return None if v is None or (isinstance(v, float) and pd.isna(v)) or v == "" else v

def init_db():
    with get_conn() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY AUTOINCREMENT, trade_time TEXT, symbol TEXT,
            direction TEXT, qty REAL, entry_price REAL, exit_price REAL, pnl REAL NOT NULL, point_value REAL, holding_minutes REAL,
            strategy TEXT, setup TEXT, notes TEXT, source TEXT, source_key TEXT UNIQUE)""")
        con.execute("""CREATE TABLE IF NOT EXISTS executions (id INTEGER PRIMARY KEY AUTOINCREMENT, execution_time TEXT, symbol TEXT,
            side TEXT, order_type TEXT, qty REAL, price REAL, status TEXT, order_id TEXT, source TEXT)""")
        con.execute("""CREATE TABLE IF NOT EXISTS open_positions (symbol TEXT, side TEXT, qty REAL, avg_price REAL,
            stop_loss REAL, take_profit REAL, unrealized REAL, captured_at TEXT)""")
        have = {r[1] for r in con.execute("PRAGMA table_info(trades)")}
        for c, t in NEW_COLS.items():  # additive migration: existing rows are preserved
            if c not in have: con.execute(f"ALTER TABLE trades ADD COLUMN {c} {t}")

def load_trades():
    with get_conn() as con: df = pd.read_sql_query("SELECT * FROM trades ORDER BY trade_time", con)
    if not df.empty: df["trade_time"] = pd.to_datetime(df["trade_time"])
    return df

def update_tags(edited):
    """Saves journal fields and keeps an audit trail so history cannot be silently rewritten."""
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as con:
        for _, r in edited.iterrows():
            old = con.execute(f"SELECT {','.join(EDIT)} FROM trades WHERE id=?", (int(r["id"]),)).fetchone()
            new = [nn(r.get(c)) for c in EDIT]
            for c, o, n in zip(EDIT, old, new):
                if (o or None) != n and c != "strategy":
                    con.execute("INSERT INTO journal_audit VALUES (?,?,?,?,?)", (int(r["id"]), c, str(o), str(n), now))
            new = [("" if v is None and c in ("strategy", "setup", "notes", "followed_plan", "mistake") else v) for c, v in zip(EDIT, new)]
            con.execute(f"UPDATE trades SET {','.join(c + '=?' for c in EDIT)} WHERE id=?", (*new, int(r["id"])))

init_db()
today = date.today()
with get_conn() as con:
    init_game_db(con)
    allt = load_trades()
    recs = []
    if not allt.empty:
        recs = allt.astype(object).where(allt.notna(), None).assign(trade_time=allt["trade_time"].astype(str)).to_dict("records")
        apply_events(con, trade_events(recs))
    reviews = con.execute("SELECT kind, day, no_trade FROM reviews").fetchall()
    m = metrics(allt, reviews)
    new_unlocks = process(con, m, today)
    info = level_info(total_xp(con))
    leveled = levelup_pending(con, info["level"])
    sxp = season_xp(con)
    tier = season_tier(sxp)
    accent = (con.execute("SELECT value FROM game_state WHERE key='accent'").fetchone() or ["Teal"])[0]
    if accent in ACCENT_TIER and tier < ACCENT_TIER[accent]: accent = "Teal"
    pos = [dict(zip(("symbol", "side", "qty", "avg_price", "stop_loss", "take_profit", "unrealized"), r)) for r in
           con.execute("SELECT symbol,side,qty,avg_price,stop_loss,take_profit,unrealized FROM open_positions")]
    missions = mission_progress(con, today)
    done_ach, done_nodes = unlocked(con, "achievement"), unlocked(con, "node")
    xp_feed = recent_events(con, 10)
    recent_unl = con.execute("SELECT kind,id,unlocked_at FROM unlocks ORDER BY unlocked_at DESC LIMIT 5").fetchall()
st.markdown(CSS + CSS2 + f"<style>:root{{--teal:{ACCENTS[accent]}}}</style>", unsafe_allow_html=True)
if leveled: st.toast(f"Level {info['level']} reached: {info['rank']}", icon="🏅")
for u in new_unlocks: st.toast(u, icon="✨")
score, comp = discipline(m)

st.title("📈 Gaüd Trade Edge")
st.markdown(hud_html(info), unsafe_allow_html=True)

with st.sidebar:
    st.header("Import")
    up = st.file_uploader("Upload all 5 export CSVs", type=["csv"], accept_multiple_files=True)
    if up and st.button("Import CSV", type="primary"):
        b = import_bundle({f.name: f.getvalue() for f in up})
        with get_conn() as con: res = save_bundle(con, b, source="export")
        st.success(f"Imported {res['trades']} new trades and {res['executions']} executions.")
        st.rerun()
    st.header("Filters")
    df = load_trades()
    if not df.empty:
        s1 = st.selectbox("Instrument", ["All"] + sorted(df["symbol"].dropna().unique().tolist()))
        s2 = st.selectbox("Direction", ["All"] + sorted(df["direction"].dropna().unique().tolist()))
        if s1 != "All": df = df[df.symbol == s1]
        if s2 != "All": df = df[df.direction == s2]

tabs = st.tabs(["🏠 Home", "🎟️ Season", "🏆 Achievements", "🧭 Skill Tree", "📓 Trades", "🔎 Find My Edge", "🛡️ Risk", "🗄️ Data"])

with tabs[0]:
    a, b = st.columns([1, 2])
    with a:
        st.subheader("Process Discipline")
        st.metric("Score (process only, never P&L)", "No data yet" if score is None else f"{score:.0f} / 100")
        for k, v in comp.items(): st.progress(0.0 if v is None else float(v), text=f"{k}: " + ("n/a" if v is None else f"{v:.0%}"))
        for msg in (risk_status(pos) if pos else []): (st.warning if "NO STOP" in msg else st.info)(msg)
    with b:
        st.subheader("Today's mission")
        w1, w2, w3 = st.columns(3)
        w1.markdown(card("Pre-market", "Write today's plan and criteria.", "Step 1"), unsafe_allow_html=True)
        w2.markdown(card("Trading session", "Trade only if your criteria are met. Not trading is a valid outcome.", "Step 2"), unsafe_allow_html=True)
        w3.markdown(card("Post-session", "Review what you did and what you followed.", "Step 3"), unsafe_allow_html=True)
        with st.form("review", clear_on_submit=True):
            kind = st.selectbox("Log a review", ["premarket", "post_session", "weekly"],
                                format_func=lambda k: {"premarket": "Pre-market preparation", "post_session": "Post-session review", "weekly": "Weekly review"}[k])
            no_trade = st.checkbox("No-trade day: my criteria were not met (earns the same XP)")
            text = st.text_area("Notes (20+ characters earns XP; self-reported)")
            if st.form_submit_button("Save review"):
                day = week_start(today) if kind == "weekly" else today.isoformat()
                with get_conn() as con: ok = add_review(con, kind, day, text, no_trade)
                (st.success if ok else st.info)("Saved." if ok else "Already logged for this period.")
                st.rerun()
    st.subheader("Performance core")
    if df.empty:
        st.info("Import your five CSVs in the sidebar to see performance. Sample files are in sample_data/.")
    else:
        stt = summary_stats(df)
        for c, (l, v) in zip(st.columns(6), [("Net P&L", f"${stt['net_pnl']:,.2f}"), ("Trades", stt["trades"]), ("Win rate", f"{stt['win_rate']:.1%}"),
                ("Profit factor", f"{stt['profit_factor']:.2f}"), ("Expectancy", f"${stt['expectancy']:,.2f}"), ("Max drawdown", f"${stt['max_drawdown']:,.2f}")]): c.metric(l, v)
        st.plotly_chart(px.line(equity_curve(df), x="trade_time", y="equity", title="Equity curve"), use_container_width=True)
    n1, n2 = st.columns(2)
    with n1:
        st.subheader("Next objective")
        open_ = [(min(m[x[5]], x[6]) / x[6], x) for x in ACHIEVEMENTS if x[0] not in done_ach and not x[8]]
        if open_:
            fr, x = max(open_, key=lambda t: t[0])
            st.markdown(card(x[1], x[4], f"{x[2]} · {min(m[x[5]], x[6])}/{x[6]}", "avail"), unsafe_allow_html=True); st.progress(fr)
    with n2:
        st.subheader("Recent unlocks & activity")
        for k, i, t in recent_unl: st.write(f"✨ {k}: {i.split('|')[-1]} ({t[:10]})")
        for ts, xp, why in xp_feed: st.caption(f"+{xp} XP · {why} · {ts[:10]}")
        if not xp_feed and not recent_unl: st.caption("Nothing yet. Journal a trade or log a review to earn your first XP.")

with tabs[1]:
    s0, s1_ = season_window()
    st.subheader(SEASON["name"]); st.caption(f"{s0} to {s1_} · {sxp} season XP · tier {tier}/{len(SEASON['rewards'])}. Tiers are free and never expire; there is no paid track.")
    st.progress(min(1.0, (sxp % SEASON["tier_xp"]) / SEASON["tier_xp"]) if tier < len(SEASON["rewards"]) else 1.0, text="Progress to next tier")
    cols = st.columns(5)
    for i, (t, rw) in enumerate(SEASON["rewards"]):
        cols[i % 5].markdown(card(rw, f"Tier {t} · {t * SEASON['tier_xp']} XP", "Unlocked" if tier >= t else "Locked", "lit" if tier >= t else "locked"), unsafe_allow_html=True)
    opts = ["Teal"] + [k for k, v in ACCENT_TIER.items() if tier >= v]
    pick = st.selectbox("Accent color (earned cosmetics)", opts, index=opts.index(accent) if accent in opts else 0)
    if pick != accent:
        with get_conn() as con: con.execute("INSERT OR REPLACE INTO game_state VALUES ('accent',?)", (pick,))
        st.rerun()
    st.subheader("Missions")
    st.caption("Counts come from real timestamped records. Missing a week or a day costs nothing.")
    for mp in missions:
        done = mp["n"] >= mp["target"]
        st.markdown(card(("✅ " if done else "") + mp["name"], f"{mp['n']}/{mp['target']} · +{mp['xp']} XP", mp["scope"], "lit" if done else ""), unsafe_allow_html=True)
        st.progress(mp["n"] / mp["target"])

with tabs[2]:
    st.subheader("Achievements")
    st.caption(f"{len(done_ach)}/{len(ACHIEVEMENTS)} unlocked. Some are hidden until earned. Self-reported items are labeled.")
    cols = st.columns(3)
    for i, (id_, name, cat, rar, desc, key, target, xp, hid) in enumerate(ACHIEVEMENTS):
        got, val = id_ in done_ach, min(m[key], target)
        if hid and not got: name, desc, cat, rar = "???", "Hidden achievement.", "Hidden", "?"
        cols[i % 3].markdown(card(f"{ICON.get(cat, '❔')} {name}", desc + (f"<br>Unlocked {done_ach[id_][:10]} · +{xp} XP" if got else f"<br>{val}/{target}"),
                                  f"{cat} · {rar}", "lit" if got else "avail" if val else "locked"), unsafe_allow_html=True)
        if not (hid and not got): cols[i % 3].progress(val / target)

with tabs[3]:
    st.subheader("Strategy Mastery")
    st.warning(f"Sample size: {m['n_trades']} trades. Under 30 trades, results are hypotheses, and an unlocked node means you did the work, not that an edge exists.") if m["n_trades"] < 30 else None
    branches = list(dict.fromkeys(t[0] for t in TREE))
    for c, br in zip(st.columns(len(branches)), branches):
        c.markdown(f"**{br}**")
        for i, (b_, name, need, key, tg) in enumerate(TREE):
            if b_ != br: continue
            state = "lit" if node_id(i) in done_nodes else "avail" if (i == 0 or TREE[i - 1][0] != br or node_id(i - 1) in done_nodes) else "locked"
            c.markdown(card(name, f"{need}<br>{min(m[key], tg)}/{tg}", {"lit": "Unlocked", "avail": "Available", "locked": "Locked"}[state], state), unsafe_allow_html=True)
    sel = st.selectbox("Inspect a node", range(len(TREE)), format_func=lambda i: f"{TREE[i][0]} · {TREE[i][1]}")
    b_, name, need, key, tg = TREE[sel]
    st.write(f"**Requirement:** {need}. **Your data:** {m[key]} (needs {tg}).")
    st.write("**Suggested next task:** " + ("Complete. Review the evidence in Find My Edge." if node_id(sel) in done_nodes else "Log more journal fields in the Trades tab until the requirement is met."))

with tabs[4]:
    st.subheader("Trade journal")
    st.caption("XP comes from documentation quality, never from winning. Follow-plan and mistake fields are self-reported; edits are kept in an audit log and earned XP is never removed.")
    if df.empty: st.info("No trades yet.")
    else:
        cols_ = ["id", "trade_time", "symbol", "direction", "qty", "entry_price", "exit_price", "pnl", "holding_minutes"] + EDIT
        ed = st.data_editor(df[cols_].copy(), use_container_width=True, hide_index=True, column_config={
            "id": st.column_config.NumberColumn(disabled=True), "pnl": st.column_config.NumberColumn(format="$%.2f", disabled=True),
            "followed_plan": st.column_config.SelectboxColumn("followed plan?", options=["", "yes", "no"])})
        if st.button("Save journal"): update_tags(ed); st.success("Saved."); st.rerun()
        st.download_button("Export trades", ed.to_csv(index=False).encode(), "gaud_trade_journal.csv", "text/csv")

with tabs[5]:
    if df.empty: st.info("No trades yet.")
    else:
        st.dataframe(edge_scorecard(df), use_container_width=True, hide_index=True)
        st.plotly_chart(px.bar(time_buckets(df), x="bucket", y="pnl", hover_data=["trades", "win_rate", "expectancy"], title="P&L by 30-minute window"), use_container_width=True)
        for r in recommendations(df): st.info(r)
with tabs[6]:
    if df.empty: st.info("No trades yet.")
    else:
        rm = risk_metrics(df)
        for c, (k, v) in zip(st.columns(5), [("Avg winner", rm["avg_win"]), ("Avg loser", rm["avg_loss"]), ("Largest winner", rm["largest_win"]), ("Largest loser", rm["largest_loss"]), ("Max drawdown", rm["max_drawdown"])]): c.metric(k, f"${v:,.2f}")
        for x in rm["observations"]: st.warning(x)
with tabs[7]:
    st.dataframe(df, use_container_width=True, hide_index=True)
