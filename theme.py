"""Design system v0: tokens + HUD. Transitions only (no looping animation); honors reduced motion."""
CSS = """<style>
:root{--obsidian:#0b0d12;--graphite:#161a22;--edge:#2a3040;--silver:#c9d1e0;--gold:#c8a45a;--teal:#38d6c4;--violet:#8b7cf6}
.stApp{background:radial-gradient(1200px 500px at 15% -10%,#1b2140 0%,var(--obsidian) 60%);color:var(--silver)}
h1,h2,h3{letter-spacing:.02em}
.gaud-hud{display:flex;gap:1.2rem;align-items:center;flex-wrap:wrap;padding:1rem 1.2rem;margin:.5rem 0 1rem;
 background:linear-gradient(145deg,var(--graphite),#10131a);border:1px solid var(--edge);border-radius:14px;
 box-shadow:0 8px 30px rgba(0,0,0,.45),inset 0 0 0 1px rgba(200,164,90,.08)}
.gaud-emblem{width:64px;height:64px;flex:none;display:grid;place-items:center;font-weight:700;font-size:1.5rem;color:var(--gold);
 clip-path:polygon(50% 0,100% 25%,100% 75%,50% 100%,0 75%,0 25%);background:linear-gradient(160deg,#2a3040,#12151c);
 filter:drop-shadow(0 0 6px rgba(200,164,90,.35))}
.gaud-meta{flex:1;min-width:220px}
.gaud-rank{font-size:1.15rem;font-weight:600;color:#fff}
.gaud-sub{font-size:.8rem;opacity:.75}
.gaud-bar{height:10px;margin-top:.5rem;background:#0a0c11;border:1px solid var(--edge);border-radius:99px;overflow:hidden}
.gaud-fill{height:100%;background:linear-gradient(90deg,var(--violet),var(--teal));transition:width .6s ease}
@media (prefers-reduced-motion:reduce){.gaud-fill{transition:none}}
@media (max-width:640px){.gaud-hud{padding:.8rem}.gaud-emblem{width:52px;height:52px}}
</style>"""

def hud_html(info):
    pct = round(info["pct"] * 100, 1)
    return (f'<div class="gaud-hud" role="group" aria-label="Trader profile">'
            f'<div class="gaud-emblem" aria-hidden="true">{info["level"]}</div>'
            f'<div class="gaud-meta"><div class="gaud-rank">{info["rank"]} · Level {info["level"]}</div>'
            f'<div class="gaud-sub">{info["into"]:,} / {info["needed"]:,} XP to next level · {info["total"]:,} lifetime XP (process XP only, never P&amp;L)</div>'
            f'<div class="gaud-bar" role="progressbar" aria-valuenow="{pct}" aria-valuemin="0" aria-valuemax="100">'
            f'<div class="gaud-fill" style="width:{pct}%"></div></div></div></div>')

CSS2 = """<style>
.gaud-card{padding:.8rem 1rem;border:1px solid var(--edge);border-radius:12px;background:linear-gradient(145deg,#161a22,#10131a);margin-bottom:.6rem}
.gaud-card.lit{border-color:var(--gold);box-shadow:0 0 14px rgba(200,164,90,.25)}
.gaud-card.avail{border-color:var(--teal)}
.gaud-card.locked{opacity:.55}
.gaud-tag{font-size:.7rem;letter-spacing:.08em;text-transform:uppercase;color:var(--gold)}
.gaud-name{font-weight:600;color:#fff}
</style>"""

def card(title, body, tag="", state=""):
    return f'<div class="gaud-card {state}"><div class="gaud-tag">{tag}</div><div class="gaud-name">{title}</div><div class="gaud-sub">{body}</div></div>'
