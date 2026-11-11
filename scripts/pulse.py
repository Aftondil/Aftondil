"""Generate the live activity line (pulse-{light,dark}.svg) from real contributions.

Run by .github/workflows/pulse.yml daily; stdlib only.

    GITHUB_TOKEN=... python3 scripts/pulse.py <login> <out_dir>
    python3 scripts/pulse.py --demo <out_dir>          # random data, for previews
"""
import json
import os
import random
import sys
import urllib.request
from pathlib import Path

from palette import THEMES

W, H = 1000, 96
TOP, BOTTOM = 34, 88
QUERY = """query($login:String!){user(login:$login){contributionsCollection{contributionCalendar{
  totalContributions weeks{contributionDays{contributionCount}}}}}}"""


def fetch(login):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": login}}).encode(),
        headers={"Authorization": f"bearer {os.environ['GITHUB_TOKEN']}", "User-Agent": "profile-pulse"},
    )
    cal = json.load(urllib.request.urlopen(req))["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    weeks = [sum(d["contributionCount"] for d in w["contributionDays"]) for w in cal["weeks"]]
    return cal["totalContributions"], weeks


def demo():
    rng = random.Random(3)
    weeks = [max(0, int(rng.gauss(14, 9) + 10 * (i % 13 > 8))) for i in range(53)]
    return sum(weeks), weeks


def smooth(pts):
    d = f"M{pts[0][0]:.1f} {pts[0][1]:.1f}"
    for i in range(len(pts) - 1):
        p0 = pts[max(i - 1, 0)]; p1 = pts[i]; p2 = pts[i + 1]; p3 = pts[min(i + 2, len(pts) - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, min(BOTTOM, p1[1] + (p2[1] - p0[1]) / 6))
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, min(BOTTOM, p2[1] - (p3[1] - p1[1]) / 6))
        d += f"C{c1[0]:.1f} {c1[1]:.1f} {c2[0]:.1f} {c2[1]:.1f} {p2[0]:.1f} {p2[1]:.1f}"
    return d


def build(total, weeks, t):
    peak = max(weeks) or 1
    n = len(weeks)
    pts = [(8 + i * (W - 24) / (n - 1), BOTTOM - w / peak * (BOTTOM - TOP)) for i, w in enumerate(weeks)]
    line = smooth(pts)
    ex, ey = pts[-1]
    stops = (f'<stop offset="0" stop-color="{t["a1"]}"/><stop offset=".5" stop-color="{t["am"]}"/>'
             f'<stop offset="1" stop-color="{t["a2"]}"/>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="{total} contributions in the last year">
<defs>
  <linearGradient id="g" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="{W}" y2="0">{stops}</linearGradient>
  <linearGradient id="a" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{t['a2']}" stop-opacity=".16"/><stop offset="1" stop-color="{t['a2']}" stop-opacity="0"/>
  </linearGradient>
</defs>
<style>
  .lbl {{ font: 400 13px ui-monospace, SFMono-Regular, Menlo, Consolas, "DejaVu Sans Mono", monospace; fill: {t['muted']}; }}
  .num {{ fill: {t['fg']}; }}
  .base {{ stroke: {t['muted']}; stroke-opacity: .2; stroke-dasharray: 2 4; }}
  .line {{ fill: none; stroke: url(#g); stroke-width: 2; stroke-linejoin: round;
          stroke-dasharray: 100; stroke-dashoffset: 100; animation: draw 2.4s cubic-bezier(.4,0,.2,1) .2s forwards; }}
  .area {{ fill: url(#a); opacity: 0; animation: show 1.2s ease 1.6s forwards; }}
  .dot {{ fill: {t['a2']}; opacity: 0; animation: show .3s ease 2.5s forwards; }}
  .ring {{ fill: none; stroke: {t['a2']}; stroke-width: 1.5; opacity: 0; transform-box: fill-box; transform-origin: center;
          animation: ping 2s ease-out 2.6s infinite; }}
  @keyframes draw {{ to {{ stroke-dashoffset: 0; }} }}
  @keyframes show {{ to {{ opacity: 1; }} }}
  @keyframes ping {{ 0% {{ opacity: .9; transform: scale(.6); }} 70%, 100% {{ opacity: 0; transform: scale(2.6); }} }}
  @media (prefers-reduced-motion: reduce) {{ * {{ animation: none !important; opacity: 1 !important; stroke-dashoffset: 0 !important; }} .ring {{ display: none; }} }}
</style>
<text class="lbl" x="8" y="16"><tspan class="num">{total:,}</tspan> contributions · last 12 months</text>
<line class="base" x1="8" y1="{BOTTOM}" x2="{W - 16}" y2="{BOTTOM}"/>
<path class="area" d="{line}L{ex:.1f} {BOTTOM}L8 {BOTTOM}Z"/>
<path class="line" d="{line}" pathLength="100"/>
<circle class="ring" cx="{ex:.1f}" cy="{ey:.1f}" r="5"/>
<circle class="dot" cx="{ex:.1f}" cy="{ey:.1f}" r="3.5"/>
</svg>
'''


if __name__ == "__main__":
    if sys.argv[1] == "--demo":
        total, weeks = demo()
    else:
        total, weeks = fetch(sys.argv[1])
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    for name, theme in THEMES.items():
        (out / f"pulse-{name}.svg").write_text(build(total, weeks, theme))
    print(f"{total} contributions, {len(weeks)} weeks -> {out}")
