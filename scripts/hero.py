"""Generate the static profile assets:

  assets/hero-{light,dark}.svg          animated header
  assets/link-<name>-{light,dark}.svg   minimal link pills

Header story, one loop per tagline phrase:
  forward pass -> signal beams from the output layer into the text -> phrase is typed
  -> backward pass (training) -> weights drift.
Behind it: the ridge from my profile photo as a point cloud, swept by a scan line,
with fainter ranges drifting behind. Dark theme gets stars, light theme gets haze.

Pure SVG + CSS/SMIL, no JS, so GitHub renders it.  Stdlib only:

    python3 scripts/hero.py
"""
import math
import random
from pathlib import Path

from network import NETWORKS, path
from palette import THEMES

NAME = "Aftondil"
ROLE = "AI Engineer"
# The network "generates" one of these per forward pass.
PHRASES = [
    "building agents",
    "shipping LLM systems",
    "fine-tuning models",
    "automating the boring stuff",
]
# (label, url) — rendered as "~/label ↗" pills under the header.
LINKS = [
    ("linkedin", "https://www.linkedin.com/in/YOUR_HANDLE"),
    ("telegram", "https://t.me/YOUR_HANDLE"),
    ("website", "https://YOUR_SITE"),
]

NETWORK = "hourglass"       # shape of the network, see scripts/network.py

W, H = 1000, 300
X0, X1 = 595, 960          # network area (accent gradient spans it)
BEAM = 0.4                 # output layer -> text (s)
CYCLE = 4.2                # one full loop (s)
FIRE_P = 0.55              # share of edges that carry a forward signal
BACK_P = 0.4               # share of edges that carry a gradient

TX, NAME_Y, ROLE_Y = 8, 118, 162
ADV = 12.04                # monospace advance at 20px
TYPE_DT, ERASE_DT = 0.045, 0.018

T_OUT = 2.1                                # output layer fires
T_TYPE = T_OUT + BEAM + 0.05               # beam lands, typing starts
T_BACK = T_OUT + BEAM                      # backward pass starts
T_BACK_LEN = 1.05                          # backward pass duration

# Ridge of the peak behind me in the profile photo (photo px, 1600 wide).
RIDGE = [(0, 455), (60, 440), (120, 425), (170, 405), (230, 396), (300, 386), (340, 376),
         (380, 371), (410, 360), (440, 376), (465, 361), (490, 355), (525, 362), (560, 356),
         (610, 366), (650, 365), (690, 371), (720, 386), (760, 395), (790, 386), (840, 381),
         (880, 396), (920, 401), (960, 416), (1000, 430), (1040, 436), (1080, 456), (1120, 476),
         (1160, 471), (1200, 511), (1240, 541), (1290, 566), (1340, 571), (1380, 581),
         (1420, 601), (1480, 606), (1540, 626), (1600, 641)]
RIDGE_TOP, RIDGE_BOTTOM = 196, 288
SCAN = 8.0                 # scan line period (s)


# ---------------------------------------------------------------- geometry

def smooth(pts):
    """Catmull-Rom through pts, as a cubic Bezier path."""
    d = f"M{pts[0][0]:.1f} {pts[0][1]:.1f}"
    for i in range(len(pts) - 1):
        p0 = pts[max(i - 1, 0)]; p1 = pts[i]; p2 = pts[i + 1]; p3 = pts[min(i + 2, len(pts) - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d += f"C{c1[0]:.1f} {c1[1]:.1f} {c2[0]:.1f} {c2[1]:.1f} {p2[0]:.1f} {p2[1]:.1f}"
    return d


def ridge_pts():
    ys = [y for _, y in RIDGE]
    lo, hi = min(ys), max(ys)
    return [(x / 1600 * W, RIDGE_TOP + (y - lo) / (hi - lo) * (RIDGE_BOTTOM - RIDGE_TOP)) for x, y in RIDGE]


def ridge_y(x, pts):
    x = min(max(x, 0), W)
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        if x1 <= x <= x2:
            return y1 + (y2 - y1) * (x - x1) / (x2 - x1)
    return pts[-1][1]


def far_range(pts, src, lift, amp, phase):
    """A fainter range derived from the main ridge; spans past the edges so it can drift."""
    out = []
    for x in range(-60, W + 61, 20):
        y0 = ridge_y(src(x), pts)
        y = RIDGE_TOP - lift + amp * (y0 - RIDGE_TOP) + 4 * math.sin(x / 47 + phase)
        out.append((x, y))
    return smooth(out)


def point_cloud(pts, rng):
    dots = []
    for x in range(2, W, 6):
        top = ridge_y(x, pts)
        dots.append(f'<circle cx="{x + rng.uniform(-1, 1):.1f}" cy="{top + rng.uniform(-.6, .6):.1f}" r="1.3"/>')
        d = 5.0
        while top + d < H:
            if rng.random() < math.exp(-d / 38):
                op = max(.25, 1 - d / 90)
                dots.append(f'<circle cx="{x + rng.uniform(-2.5, 2.5):.1f}" cy="{top + d + rng.uniform(-2, 2):.1f}" '
                            f'r=".9" opacity="{op:.2f}"/>')
            d += 4.5 + d * .12
    return "".join(dots)


# ---------------------------------------------------------------- timing

def discrete(attr, values, times, total):
    """SMIL discrete animation; times in seconds, first must be 0."""
    kt = ";".join(f"{t / total:.4f}" for t in times)
    vs = ";".join(str(v) for v in values)
    return (f'<animate attributeName="{attr}" dur="{total}s" repeatCount="indefinite" '
            f'calcMode="discrete" keyTimes="{kt}" values="{vs}"/>')


def tagline(base):
    """Per-character typing of PHRASES, synced to the beam landing."""
    total = CYCLE * len(PHRASES)
    chars, cursor_events = [], []
    for k, phrase in enumerate(PHRASES):
        n = len(phrase)
        start = k * CYCLE + T_TYPE
        erase_start = (k + 1) * CYCLE + T_OUT - 0.1 - n * ERASE_DT
        for i, ch in enumerate(phrase):
            on = (start + i * TYPE_DT) % total
            off = (erase_start + (n - 1 - i) * ERASE_DT) % total
            cursor_events += [(on, base + (i + 1) * ADV), (off, base + i * ADV)]
            if ch == " ":
                continue
            if on < off:
                anim = discrete("opacity", [0, 1, 0], [0, on, off], total)
            else:
                anim = discrete("opacity", [1, 0, 1], [0, off, on], total)
            esc = {"<": "&lt;", "&": "&amp;", ">": "&gt;"}.get(ch, ch)
            chars.append(f'<text class="tok" x="{base + i * ADV:.1f}" y="{ROLE_Y}" opacity="0">{esc}{anim}</text>')
    cursor_events.sort()
    # state at t=0 is the end of the loop: last phrase fully typed
    xs = [base + len(PHRASES[-1]) * ADV] + [x for _, x in cursor_events]
    ts = [0] + [t for t, _ in cursor_events]
    return "".join(chars), discrete("x", [f"{x:.1f}" for x in xs], ts, total)


# ---------------------------------------------------------------- scenery

def stars(rng, n=18):
    out = []
    avoid = [(0, 60, 270, 128), (0, 140, 560, 172), (580, 25, 975, 230)]
    while len(out) < n:
        x, y = rng.uniform(10, W - 10), rng.uniform(8, 185)
        if any(a <= x <= c and b <= y <= d for a, b, c, d in avoid):
            continue
        out.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{rng.uniform(.6, 1.3):.1f}" '
                   f'style="animation-duration:{rng.uniform(2.5, 6):.1f}s;animation-delay:-{rng.uniform(0, 6):.1f}s"/>')
    return f'<g class="stars">{"".join(out)}</g>'


def haze(rng):
    out = []
    for i in range(4):
        out.append(f'<ellipse cx="{rng.uniform(360, 900):.0f}" cy="{rng.uniform(10, 40):.0f}" '
                   f'rx="{rng.uniform(120, 240):.0f}" ry="{rng.uniform(3, 6):.0f}" '
                   f'style="animation-delay:-{rng.uniform(0, 30):.0f}s"/>')
    return f'<g class="haze" filter="url(#soft)">{"".join(out)}</g>'


# ---------------------------------------------------------------- build

def build(theme_name, t, variant=NETWORK):
    rng = random.Random(7)
    net = NETWORKS[variant](random.Random(11))
    hop, bhop = T_OUT / net.maxd, T_BACK_LEN / net.maxd
    pct = lambda s: s / CYCLE * 100

    edges, fwd, bwd = [], [], []
    wdur = CYCLE * 4
    for a, b, w in net.edges:
        na, nb = net.nodes[a], net.nodes[b]
        pa, pb = (na["x"], na["y"]), (nb["x"], nb["y"])
        d = path(pa, pb, net.orient)
        edges.append(f'<path d="{d}" style="stroke-width:{w:.2f};animation-delay:-{rng.uniform(0, wdur):.1f}s"/>')
        if na["d"] >= nb["d"]:
            continue
        if rng.random() < FIRE_P:
            delay = na["d"] * hop + rng.uniform(0, 0.12)
            fwd.append(f'<path d="{d}" pathLength="100" style="stroke-width:{w + .6:.2f};animation-delay:{delay:.2f}s"/>')
        if rng.random() < BACK_P:
            delay = T_BACK + (net.maxd - nb["d"]) * bhop + rng.uniform(0, 0.08)
            bwd.append(f'<path d="{path(pb, pa, net.orient)}" pathLength="100" style="animation-delay:{delay:.2f}s"/>')

    dots = []
    for n in net.nodes:
        x, y, r = n["x"], n["y"], n["r"]
        st = f'style="animation-delay:{n["d"] * hop:.2f}s"'
        cls = "core hollow" if n.get("hollow") else "core big" if n.get("big") else "core"
        dots.append(f'<circle class="halo" cx="{x:.1f}" cy="{y:.1f}" r="{r * 1.5:.1f}" {st}/>')
        if n["shape"] == "s":
            dots.append(f'<rect class="{cls}" x="{x - r:.1f}" y="{y - r:.1f}" width="{2 * r:.1f}" height="{2 * r:.1f}" rx="2" {st}/>')
        else:
            dots.append(f'<circle class="{cls}" cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" {st}/>')

    prefix = f"> {ROLE} · "
    base = TX + len(prefix) * ADV
    xs = " ".join(f"{TX + i * ADV:.1f}" for i in range(len(prefix)))
    toks, cursor_anim = tagline(base)
    tag_end = base + max(len(p) for p in PHRASES) * ADV

    # beam: from the output layer, over the network, down into the cursor
    ox, oy = net.out
    bx, by = base + 5, ROLE_Y - 24
    beam = f"M{ox:.1f} {oy:.1f}C{ox + 55:.1f} {min(oy, 60) - 90:.1f} {bx + 120:.1f} -10 {bx:.1f} {by}"

    rp = ridge_pts()
    ridge = smooth(rp)
    cloud = point_cloud(rp, rng)
    far1 = far_range(rp, lambda x: x + 110, 14, .8, 0)
    far2 = far_range(rp, lambda x: x - 190, 27, .65, 2)
    scenery = stars(rng) if theme_name == "dark" else haze(rng)

    stops = (f'<stop offset="0" stop-color="{t["a1"]}"/><stop offset=".5" stop-color="{t["am"]}"/>'
             f'<stop offset="1" stop-color="{t["a2"]}"/>')
    rev = (f'<stop offset="0" stop-color="{t["a1"]}"/><stop offset="1" stop-color="{t["a2"]}"/>')

    return f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="{NAME} — {ROLE}">
<title>{NAME} — {ROLE}</title>
<defs>
  <linearGradient id="g" gradientUnits="userSpaceOnUse" x1="{X0}" y1="0" x2="{X1}" y2="0">{stops}</linearGradient>
  <linearGradient id="tg" gradientUnits="userSpaceOnUse" x1="{TX}" y1="0" x2="{tag_end:.0f}" y2="0">{stops}</linearGradient>
  <linearGradient id="bg" gradientUnits="userSpaceOnUse" x1="{bx:.0f}" y1="0" x2="{ox:.0f}" y2="0">{rev}</linearGradient>
  <linearGradient id="rg" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="{W}" y2="0">{stops}</linearGradient>
  <linearGradient id="fade" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".1" stop-color="#fff"/>
    <stop offset=".9" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/>
  </linearGradient>
  <linearGradient id="band" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".85" stop-color="#fff" stop-opacity=".55"/>
    <stop offset="1" stop-color="#fff"/>
  </linearGradient>
  <linearGradient id="sl" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{t['a2']}" stop-opacity="0"/><stop offset=".35" stop-color="{t['a2']}"/>
    <stop offset="1" stop-color="{t['a2']}" stop-opacity="0"/>
  </linearGradient>
  <mask id="m"><rect width="{W}" height="{H}" fill="url(#fade)"/></mask>
  <mask id="scan" maskUnits="userSpaceOnUse" x="-200" y="0" width="{W + 400}" height="{H}">
    <rect class="sweep" x="-160" y="0" width="160" height="{H}" fill="url(#band)"/>
  </mask>
  <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
    <feGaussianBlur stdDeviation="2.2" result="b"/>
    <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
  <filter id="soft" x="-20%" y="-200%" width="140%" height="500%"><feGaussianBlur stdDeviation="7"/></filter>
  <g id="cloud">{cloud}</g>
</defs>
<style>
  .name {{ font: 600 56px -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Helvetica, Arial, sans-serif;
          fill: {t['fg']}; letter-spacing: -1.5px; opacity: 0; animation: rise .9s cubic-bezier(.2,.7,.2,1) .1s forwards; }}
  .role, .tok {{ font: 400 20px ui-monospace, SFMono-Regular, Menlo, Consolas, "DejaVu Sans Mono", monospace; }}
  .role {{ fill: {t['muted']}; opacity: 0; animation: rise .9s cubic-bezier(.2,.7,.2,1) .35s forwards; }}
  .role .p, .tok, .cursor {{ fill: url(#tg); }}
  .cursor {{ animation: blink 1.1s steps(1) infinite; }}
  .gen {{ opacity: 0; animation: show .01s linear {T_OUT:.2f}s forwards; }}  /* hide the wrapped-around last phrase on load */

  .edges path {{ fill: none; stroke: {t['muted']}; stroke-opacity: .16; animation: wt {wdur}s ease-in-out infinite; }}
  .fwd path {{ fill: none; stroke: url(#g); stroke-linecap: round;
              stroke-dasharray: 14 200; stroke-dashoffset: 14; animation: flow {CYCLE}s linear infinite; }}
  .bwd path {{ fill: none; stroke: url(#g); stroke-opacity: .55; stroke-width: 1; stroke-linecap: round;
              stroke-dasharray: 8 200; stroke-dashoffset: 8; animation: back {CYCLE}s linear infinite; }}
  .beam {{ fill: none; stroke: url(#bg); stroke-width: 2; stroke-linecap: round;
          stroke-dasharray: 22 200; stroke-dashoffset: 22; animation: beam {CYCLE}s cubic-bezier(.5,0,.6,1) {T_OUT:.2f}s infinite; }}
  .core {{ fill: {t['node']}; animation: fire {CYCLE}s ease-out infinite; }}
  .hollow {{ fill: none; stroke: {t['muted']}; stroke-width: 1.3; animation-name: fireh; }}
  .big {{ fill: {t['muted']}; }}
  .halo {{ fill: none; stroke: url(#g); stroke-width: 1.5; opacity: 0; transform-box: fill-box; transform-origin: center;
          animation: ring {CYCLE}s ease-out infinite; }}
  .land {{ fill: none; stroke: {t['a1']}; stroke-width: 1.5; opacity: 0; transform-box: fill-box; transform-origin: center;
          animation: ring {CYCLE}s ease-out {T_TYPE - .05:.2f}s infinite; }}

  .far {{ fill: none; stroke: {t['muted']}; stroke-width: 1; }}
  .far1 {{ stroke-opacity: .22; animation: drift 22s ease-in-out infinite alternate; }}
  .far2 {{ stroke-opacity: .12; animation: drift 31s ease-in-out -9s infinite alternate-reverse; }}
  .ridge {{ fill: none; stroke: {t['muted']}; stroke-opacity: .3; stroke-width: 1;
           stroke-dasharray: 100; stroke-dashoffset: 100; animation: draw 2.4s cubic-bezier(.4,0,.2,1) .2s forwards; }}
  .pc {{ fill: {t['muted']}; opacity: 0; animation: show 1.6s ease .8s forwards; }}
  .pc-lit {{ fill: url(#rg); }}
  .sweep, .scanline {{ animation: scan {SCAN}s cubic-bezier(.45,0,.55,1) 1.2s infinite; transform: translateX(-200px); }}
  .scanline {{ stroke: url(#sl); stroke-width: 1.2; }}
  .stars circle {{ fill: {t['fg']}; animation: twinkle 4s ease-in-out infinite alternate; }}
  .haze ellipse {{ fill: {t['muted']}; opacity: .06; animation: drift 30s ease-in-out infinite alternate; }}

  @keyframes rise   {{ from {{ opacity: 0; transform: translateY(8px); }} to {{ opacity: 1; transform: none; }} }}
  @keyframes show   {{ to {{ opacity: 1; }} }}
  @keyframes draw   {{ to {{ stroke-dashoffset: 0; }} }}
  @keyframes blink  {{ 0%, 50% {{ opacity: 1; }} 50.01%, 100% {{ opacity: 0; }} }}
  @keyframes wt     {{ 0%, 100% {{ stroke-opacity: .08; }} 30% {{ stroke-opacity: .26; }} 55% {{ stroke-opacity: .11; }} 80% {{ stroke-opacity: .2; }} }}
  @keyframes flow   {{ 0% {{ stroke-dashoffset: 14; }} {pct(hop):.1f}%, 100% {{ stroke-dashoffset: -100; }} }}
  @keyframes back   {{ 0% {{ stroke-dashoffset: 8; }} {pct(bhop):.1f}%, 100% {{ stroke-dashoffset: -100; }} }}
  @keyframes beam   {{ 0% {{ stroke-dashoffset: 22; }} {pct(BEAM):.1f}%, 100% {{ stroke-dashoffset: -100; }} }}
  @keyframes fire   {{ 0% {{ fill: {t['a2']}; }} 18%, 100% {{ fill: {t['node']}; }} }}
  @keyframes fireh  {{ 0% {{ stroke: {t['a2']}; }} 18%, 100% {{ stroke: {t['muted']}; }} }}
  @keyframes ring   {{ 0% {{ opacity: .9; transform: scale(.7); }} 20%, 100% {{ opacity: 0; transform: scale(2.4); }} }}
  @keyframes scan   {{ 0% {{ transform: translateX(-200px); }} 70%, 100% {{ transform: translateX({W + 200}px); }} }}
  @keyframes drift  {{ from {{ transform: translateX(-18px); }} to {{ transform: translateX(18px); }} }}
  @keyframes twinkle {{ from {{ opacity: .12; }} to {{ opacity: .75; }} }}
  @media (prefers-reduced-motion: reduce) {{
    * {{ animation: none !important; }}
    .name, .role, .pc, .gen {{ opacity: 1; }} .ridge {{ stroke-dashoffset: 0; }}
    .fwd, .bwd, .beam, .halo, .land, .scanline, .pc-lit {{ display: none; }}
  }}
</style>
{scenery}
<g mask="url(#m)">
  <path class="far far2" d="{far2}"/>
  <path class="far far1" d="{far1}"/>
  <path class="ridge" d="{ridge}" pathLength="100"/>
  <use class="pc" href="#cloud" xlink:href="#cloud"/>
  <g mask="url(#scan)"><use class="pc-lit" href="#cloud" xlink:href="#cloud" filter="url(#glow)"/></g>
  <line class="scanline" x1="0" y1="{RIDGE_TOP - 30}" x2="0" y2="{H}"/>
</g>
<text class="name" x="{TX - 2}" y="{NAME_Y}">{NAME}</text>
<text class="role" x="{xs}" y="{ROLE_Y}"><tspan class="p">&gt;</tspan> {ROLE} ·</text>
<g class="gen"><g>{toks}</g>
<rect class="cursor" x="0" y="{ROLE_Y - 16}" width="10" height="20" rx="1">{cursor_anim}</rect></g>
<circle class="land" cx="{bx:.1f}" cy="{ROLE_Y - 6}" r="6"/>
<g class="edges">{"".join(edges)}</g>
<g class="bwd">{"".join(bwd)}</g>
<g class="fwd" filter="url(#glow)">{"".join(fwd)}</g>
<path class="beam" d="{beam}" pathLength="100" filter="url(#glow)"/>
<g filter="url(#glow)">{"".join(dots)}</g>
</svg>
'''


def pill(label, t):
    text = f"~/{label}"
    w = round(28 + (len(text) + 2) * 8.43)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} 32" width="{w}" height="32" role="img" aria-label="{label}">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="0">
  <stop offset="0" stop-color="{t['a1']}"/><stop offset=".5" stop-color="{t['am']}"/><stop offset="1" stop-color="{t['a2']}"/>
</linearGradient></defs>
<rect x=".75" y=".75" width="{w - 1.5}" height="30.5" rx="15.25" fill="none" stroke="{t['muted']}" stroke-opacity=".35" stroke-width="1.5"/>
<text x="14" y="21" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, 'DejaVu Sans Mono', monospace" font-size="14">
<tspan fill="{t['muted']}">~/</tspan><tspan fill="{t['fg']}">{label}</tspan><tspan fill="url(#g)"> ↗</tspan></text>
</svg>
'''


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3:  # preview a shape: hero.py <variant> <out_dir>
        out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
        for name, theme in THEMES.items():
            (out / f"hero-{sys.argv[1]}-{name}.svg").write_text(build(name, theme, sys.argv[1]))
        sys.exit()
    out = Path(__file__).resolve().parent.parent / "assets"
    out.mkdir(exist_ok=True)
    for name, theme in THEMES.items():
        (out / f"hero-{name}.svg").write_text(build(name, theme))
        for label, _ in LINKS:
            (out / f"link-{label}-{name}.svg").write_text(pill(label, theme))
    for p in sorted(out.glob("hero-*.svg")):
        print(p.name, f"{p.stat().st_size / 1024:.0f} KB")
