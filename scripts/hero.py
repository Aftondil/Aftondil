"""Generate the static profile assets:

  assets/hero-{light,dark}.svg   animated header (network writes the tagline, mountain ridge)
  assets/link-<name>-{light,dark}.svg   minimal link pills

Pure SVG + CSS/SMIL, no JS, so GitHub renders it.  Stdlib only:

    python3 scripts/hero.py
"""
import random
from pathlib import Path

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

W, H = 1000, 300
LAYERS = [4, 6, 6, 2]
X0, DX = 600, 115          # first layer x, spacing between layers
CY, DY = 125, 34           # vertical centre, spacing between nodes
STEP = 0.7                 # seconds per layer hop
CYCLE = 3.6                # one forward pass (s)
FIRE_P = 0.55              # share of edges that carry a signal

TX, NAME_Y, ROLE_Y = 8, 118, 162
ADV = 12.04                # monospace advance at 20px
TYPE_DT, ERASE_DT = 0.045, 0.018

# Ridge of the peak behind me in the profile photo (photo px, 1600 wide).
RIDGE = [(0, 455), (60, 440), (120, 425), (170, 405), (230, 396), (300, 386), (340, 376),
         (380, 371), (410, 360), (440, 376), (465, 361), (490, 355), (525, 362), (560, 356),
         (610, 366), (650, 365), (690, 371), (720, 386), (760, 395), (790, 386), (840, 381),
         (880, 396), (920, 401), (960, 416), (1000, 430), (1040, 436), (1080, 456), (1120, 476),
         (1160, 471), (1200, 511), (1240, 541), (1290, 566), (1340, 571), (1380, 581),
         (1420, 601), (1480, 606), (1540, 626), (1600, 641)]
RIDGE_TOP, RIDGE_BOTTOM = 192, 288


def smooth(pts):
    """Catmull-Rom through pts, as a cubic Bezier path."""
    d = f"M{pts[0][0]:.1f} {pts[0][1]:.1f}"
    for i in range(len(pts) - 1):
        p0 = pts[max(i - 1, 0)]; p1 = pts[i]; p2 = pts[i + 1]; p3 = pts[min(i + 2, len(pts) - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d += f"C{c1[0]:.1f} {c1[1]:.1f} {c2[0]:.1f} {c2[1]:.1f} {p2[0]:.1f} {p2[1]:.1f}"
    return d


def ridge_path():
    ys = [y for _, y in RIDGE]
    lo, hi = min(ys), max(ys)
    pts = [(x / 1600 * W, RIDGE_TOP + (y - lo) / (hi - lo) * (RIDGE_BOTTOM - RIDGE_TOP)) for x, y in RIDGE]
    return smooth(pts)


def nodes():
    out = []
    for li, n in enumerate(LAYERS):
        x = X0 + li * DX
        out.append([(x, CY + (i - (n - 1) / 2) * DY) for i in range(n)])
    return out


def curve(p, q):
    (x1, y1), (x2, y2) = p, q
    xm = (x1 + x2) / 2
    return f"M{x1:.1f} {y1:.1f}C{xm:.1f} {y1:.1f} {xm:.1f} {y2:.1f} {x2:.1f} {y2:.1f}"


def discrete(attr, values, times, total):
    """SMIL discrete animation; times in seconds, first must be 0."""
    kt = ";".join(f"{t / total:.4f}" for t in times)
    vs = ";".join(str(v) for v in values)
    return (f'<animate attributeName="{attr}" dur="{total}s" repeatCount="indefinite" '
            f'calcMode="discrete" keyTimes="{kt}" values="{vs}"/>')


def tagline(prefix_len):
    """Per-character typing of PHRASES, synced to the output layer firing."""
    total = CYCLE * len(PHRASES)
    out_t = (len(LAYERS) - 1) * STEP + 0.05          # output layer fires
    base = TX + prefix_len * ADV
    chars, cursor_events = [], []
    for k, phrase in enumerate(PHRASES):
        n = len(phrase)
        start = k * CYCLE + out_t
        erase_start = (k + 1) * CYCLE + out_t - 0.12 - n * ERASE_DT
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
    cursor = discrete("x", [f"{x:.1f}" for x in xs], ts, total)
    end_x = base + max(len(p) for p in PHRASES) * ADV
    return "".join(chars), cursor, end_x


def build(t):
    rng = random.Random(7)
    layers = nodes()
    hop = STEP / CYCLE * 100  # % of the cycle a signal spends travelling

    edges, pulses = [], []
    for li in range(len(layers) - 1):
        for p in layers[li]:
            for q in layers[li + 1]:
                d = curve(p, q)
                edges.append(f'<path d="{d}"/>')
                if rng.random() < FIRE_P:
                    delay = li * STEP + rng.uniform(0, 0.12)
                    pulses.append(f'<path d="{d}" pathLength="100" style="animation-delay:{delay:.2f}s"/>')

    dots = []
    for li, layer in enumerate(layers):
        for (x, y) in layer:
            delay = li * STEP
            dots.append(
                f'<circle class="halo" cx="{x:.1f}" cy="{y:.1f}" r="7" style="animation-delay:{delay:.2f}s"/>'
                f'<circle class="core" cx="{x:.1f}" cy="{y:.1f}" r="4.5" style="animation-delay:{delay:.2f}s"/>'
            )

    prefix = f"> {ROLE} · "
    xs = " ".join(f"{TX + i * ADV:.1f}" for i in range(len(prefix)))
    toks, cursor_anim, tag_end = tagline(len(prefix))
    ridge = ridge_path()
    stops = (f'<stop offset="0" stop-color="{t["a1"]}"/><stop offset=".5" stop-color="{t["am"]}"/>'
             f'<stop offset="1" stop-color="{t["a2"]}"/>')

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="{NAME} — {ROLE}">
<title>{NAME} — {ROLE}</title>
<defs>
  <linearGradient id="g" gradientUnits="userSpaceOnUse" x1="{X0}" y1="0" x2="{X0 + DX * (len(LAYERS) - 1)}" y2="0">{stops}</linearGradient>
  <linearGradient id="tg" gradientUnits="userSpaceOnUse" x1="{TX}" y1="0" x2="{tag_end:.0f}" y2="0">{stops}</linearGradient>
  <linearGradient id="rg" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="{W}" y2="0">{stops}</linearGradient>
  <linearGradient id="rf" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{t['muted']}" stop-opacity=".08"/><stop offset="1" stop-color="{t['muted']}" stop-opacity="0"/>
  </linearGradient>
  <linearGradient id="fade" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".12" stop-color="#fff"/>
    <stop offset=".88" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/>
  </linearGradient>
  <mask id="m"><rect width="{W}" height="{H}" fill="url(#fade)"/></mask>
  <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
    <feGaussianBlur stdDeviation="2.2" result="b"/>
    <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
</defs>
<style>
  .name {{ font: 600 56px -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Helvetica, Arial, sans-serif;
          fill: {t['fg']}; letter-spacing: -1.5px; opacity: 0; animation: rise .9s cubic-bezier(.2,.7,.2,1) .1s forwards; }}
  .role, .tok {{ font: 400 20px ui-monospace, SFMono-Regular, Menlo, Consolas, "DejaVu Sans Mono", monospace; }}
  .role {{ fill: {t['muted']}; opacity: 0; animation: rise .9s cubic-bezier(.2,.7,.2,1) .35s forwards; }}
  .role .p, .tok, .cursor {{ fill: url(#tg); }}
  .cursor {{ animation: blink 1.1s steps(1) infinite; }}
  .edges path {{ fill: none; stroke: {t['muted']}; stroke-opacity: .16; stroke-width: 1; }}
  .pulses path {{ fill: none; stroke: url(#g); stroke-width: 1.8; stroke-linecap: round;
                 stroke-dasharray: 14 200; stroke-dashoffset: 14; animation: flow {CYCLE}s linear infinite; }}
  .core {{ fill: {t['node']}; animation: fire {CYCLE}s ease-out infinite; }}
  .halo {{ fill: none; stroke: url(#g); stroke-width: 1.5; opacity: 0; transform-box: fill-box; transform-origin: center;
          animation: ring {CYCLE}s ease-out infinite; }}
  .ridge {{ fill: none; stroke: {t['muted']}; stroke-opacity: .5; stroke-width: 1.2;
           stroke-dasharray: 100; stroke-dashoffset: 100; animation: draw 2.8s cubic-bezier(.4,0,.2,1) .2s forwards; }}
  .ridge-fill {{ fill: url(#rf); opacity: 0; animation: show 1.6s ease 1.6s forwards; }}
  .ridge-glow {{ fill: none; stroke: url(#rg); stroke-width: 2; stroke-linecap: round;
                stroke-dasharray: 16 300; stroke-dashoffset: 16; animation: sweep 9s cubic-bezier(.5,0,.5,1) 3s infinite; }}
  @keyframes rise  {{ from {{ opacity: 0; transform: translateY(8px); }} to {{ opacity: 1; transform: none; }} }}
  @keyframes show  {{ to {{ opacity: 1; }} }}
  @keyframes draw  {{ to {{ stroke-dashoffset: 0; }} }}
  @keyframes sweep {{ 0% {{ stroke-dashoffset: 16; }} 60%, 100% {{ stroke-dashoffset: -100; }} }}
  @keyframes blink {{ 0%, 50% {{ opacity: 1; }} 50.01%, 100% {{ opacity: 0; }} }}
  @keyframes flow  {{ 0% {{ stroke-dashoffset: 14; }} {hop:.1f}% {{ stroke-dashoffset: -100; }} 100% {{ stroke-dashoffset: -100; }} }}
  @keyframes fire  {{ 0% {{ fill: {t['a2']}; }} 18% {{ fill: {t['node']}; }} 100% {{ fill: {t['node']}; }} }}
  @keyframes ring  {{ 0% {{ opacity: .9; transform: scale(.7); }} 20% {{ opacity: 0; transform: scale(2.4); }} 100% {{ opacity: 0; }} }}
  @media (prefers-reduced-motion: reduce) {{
    * {{ animation: none !important; opacity: 1 !important; stroke-dashoffset: 0 !important; }}
    .pulses, .ridge-glow, .halo {{ display: none; }}
  }}
</style>
<g mask="url(#m)">
  <path class="ridge-fill" d="{ridge}L{W} {H}L0 {H}Z"/>
  <path class="ridge" d="{ridge}" pathLength="100"/>
  <path class="ridge-glow" d="{ridge}" pathLength="100" filter="url(#glow)"/>
</g>
<text class="name" x="{TX - 2}" y="{NAME_Y}">{NAME}</text>
<text class="role" x="{xs}" y="{ROLE_Y}"><tspan class="p">&gt;</tspan> {ROLE} ·</text>
<g>{toks}</g>
<rect class="cursor" x="0" y="{ROLE_Y - 16}" width="10" height="20" rx="1">{cursor_anim}</rect>
<g class="edges">{"".join(edges)}</g>
<g class="pulses" filter="url(#glow)">{"".join(pulses)}</g>
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
    out = Path(__file__).resolve().parent.parent / "assets"
    out.mkdir(exist_ok=True)
    for name, theme in THEMES.items():
        (out / f"hero-{name}.svg").write_text(build(theme))
        for label, _ in LINKS:
            (out / f"link-{label}-{name}.svg").write_text(pill(label, theme))
    print("wrote", sorted(p.name for p in out.glob("*.svg")))
