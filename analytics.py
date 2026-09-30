import numpy as np
import pandas as pd
def _clean(df):
    x = df.copy()
    x["pnl"] = pd.to_numeric(x["pnl"], errors="coerce").fillna(0)
    x["trade_time"] = pd.to_datetime(x["trade_time"])
    x["weekday"] = x["trade_time"].dt.day_name()
    x["hour"] = x["trade_time"].dt.hour
    x["minute"] = x["trade_time"].dt.minute
    x["minute_of_day"] = x["hour"]*60 + x["minute"]
    x["direction"] = x["direction"].str.title()
    return x
def max_drawdown(pnl):
    eq = pd.Series(pnl).cumsum()
    dd = eq - eq.cummax()
    return float(dd.min()) if len(dd) else 0.0
def summary_stats(df):
    x = _clean(df)
    wins, losses = x.loc[x.pnl > 0, "pnl"], x.loc[x.pnl < 0, "pnl"]
    gross_profit, gross_loss = wins.sum(), abs(losses.sum())
    return {
        "net_pnl": float(x.pnl.sum()),
        "trades": len(x),
        "win_rate": float((x.pnl > 0).mean()) if len(x) else 0,
        "profit_factor": float(gross_profit/gross_loss) if gross_loss else float("inf"),
        "expectancy": float(x.pnl.mean()) if len(x) else 0,
        "max_drawdown": max_drawdown(x.pnl),
    }
def equity_curve(df):
    x = _clean(df).sort_values("trade_time").copy()
    x["equity"] = x.pnl.cumsum()
    return x[["trade_time","equity"]]
def grouped_stats(df, col):
    x = _clean(df)
    g = x.groupby(col, dropna=False).agg(
        trades=("pnl","size"),
        pnl=("pnl","sum"),
        win_rate=("pnl", lambda s: (s>0).mean()),
        expectancy=("pnl","mean"),
    ).reset_index()
    g["profit_factor"] = g.apply(
        lambda r: np.nan if r["pnl"] == 0 else (
            x.loc[x[col].eq(r[col]) & x.pnl.gt(0),"pnl"].sum() /
            abs(x.loc[x[col].eq(r[col]) & x.pnl.lt(0),"pnl"].sum())
            if abs(x.loc[x[col].eq(r[col]) & x.pnl.lt(0),"pnl"].sum()) > 0 else np.inf
        ), axis=1
    )
    return g.sort_values("pnl", ascending=False)
def time_buckets(df):
    x = _clean(df)
    x["bucket_start"] = (x["minute_of_day"] // 30) * 30
    x["bucket"] = x["bucket_start"].apply(lambda m: f"{m//60:02d}:{m%60:02d}")
    g = x.groupby(["bucket_start","bucket"]).agg(
        trades=("pnl","size"), pnl=("pnl","sum"), win_rate=("pnl", lambda s:(s>0).mean()),
        expectancy=("pnl","mean")
    ).reset_index().sort_values("bucket_start")
    return g
def risk_metrics(df):
    x = _clean(df)
    wins, losses = x.loc[x.pnl > 0, "pnl"], x.loc[x.pnl < 0, "pnl"]
    obs = []
    if len(losses) and abs(losses.min()) > (wins.mean() if len(wins) else 0)*2:
        obs.append("Your largest loss is much larger than your average winner. This can overwhelm a high win rate; investigate stop placement and position sizing.")
    if len(x) >= 10:
        daily = x.groupby(x.trade_time.dt.date).pnl.sum()
        if daily.min() < 0:
            obs.append(f"Historical worst day: ${daily.min():,.2f}. Use this as an input when choosing a daily loss ceiling.")
    if len(x) < 30:
        obs.append("Sample size is still small. Treat apparent edges as hypotheses until they survive more trades.")
    return {
        "avg_win": float(wins.mean()) if len(wins) else 0,
        "avg_loss": float(losses.mean()) if len(losses) else 0,
        "largest_win": float(wins.max()) if len(wins) else 0,
        "largest_loss": float(losses.min()) if len(losses) else 0,
        "max_drawdown": max_drawdown(x.pnl),
        "observations": obs
    }
def edge_scorecard(df):
    x = _clean(df)
    dimensions = [("Instrument", "symbol"), ("Direction", "direction"), ("Day", "weekday"), ("Hour", "hour")]
    outputs=[]
    for label, col in dimensions:
        g = x.groupby(col).agg(
            trades=("pnl","size"), pnl=("pnl","sum"),
            win_rate=("pnl", lambda s:(s>0).mean()),
            expectancy=("pnl","mean")
        ).reset_index()
        g["dimension"] = label
        g["value"] = g[col].astype(str)
        g["confidence"] = np.minimum(1, g["trades"]/30)
        g["edge_score"] = g["expectancy"] * g["confidence"]
        outputs.append(g[["dimension","value","trades","pnl","win_rate","expectancy","confidence","edge_score"]])
    out = pd.concat(outputs, ignore_index=True)
    return out.sort_values(["edge_score","trades"], ascending=[False,False]).round({
        "pnl":2,"win_rate":3,"expectancy":2,"confidence":2,"edge_score":2
    })
def recommendations(df):
    x = _clean(df)
    rec=[]
    if len(x) < 10:
        return ["Import more closed trades before making strategy changes. The app will get more useful as the sample grows."]
    s = summary_stats(x)
    best_symbol = grouped_stats(x,"symbol").iloc[0]
    worst_symbol = grouped_stats(x,"symbol").iloc[-1]
    rec.append(f"Best instrument by total P&L: {best_symbol['symbol']} (${best_symbol['pnl']:,.2f} across {int(best_symbol['trades'])} trades).")
    rec.append(f"Worst instrument by total P&L: {worst_symbol['symbol']} (${worst_symbol['pnl']:,.2f} across {int(worst_symbol['trades'])} trades).")
    tb = time_buckets(x)
    viable = tb[tb.trades >= 3].sort_values("expectancy", ascending=False)
    if not viable.empty:
        b=viable.iloc[0]
        rec.append(f"Strongest 30-minute window so far: {b['bucket']} — {int(b['trades'])} trades, {b['win_rate']:.0%} win rate, ${b['expectancy']:,.2f} expectancy.")
    if s["win_rate"] > .65 and s["net_pnl"] < 0:
        rec.append("Important risk signal: the win rate is high but total P&L is negative. That usually points to losses being too large relative to winners, so risk management deserves priority over increasing trade frequency.")
    return rec
