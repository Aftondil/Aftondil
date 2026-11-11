"""Network shapes for the header. Each returns a Net; hero.py animates any of them.

A node's depth `d` is when it fires in the forward pass (0 = first).
Edges go from lower to higher depth; equal-depth edges are drawn but carry no signal.
"""
import math
from dataclasses import dataclass

CY = 125
X_MIN, X_MAX = 595, 960


@dataclass
class Net:
    nodes: list      # dict(x, y, d, r, shape='c'|'s', hollow=False, big=False)
    edges: list      # (a, b, weight)
    orient: str      # 'h' horizontal curves, 'v' vertical curves, 's' straight
    out: tuple       # (x, y) the beam to the text starts here

    @property
    def maxd(self):
        return max(n["d"] for n in self.nodes)


def path(p, q, orient):
    (x1, y1), (x2, y2) = p, q
    if orient == "h":
        xm = (x1 + x2) / 2
        return f"M{x1:.1f} {y1:.1f}C{xm:.1f} {y1:.1f} {xm:.1f} {y2:.1f} {x2:.1f} {y2:.1f}"
    if orient == "v":
        ym = (y1 + y2) / 2
        return f"M{x1:.1f} {y1:.1f}C{x1:.1f} {ym:.1f} {x2:.1f} {ym:.1f} {x2:.1f} {y2:.1f}"
    return f"M{x1:.1f} {y1:.1f}L{x2:.1f} {y2:.1f}"


def _lin(a, b, n):
    return [a + (b - a) * i / (n - 1) for i in range(n)] if n > 1 else [(a + b) / 2]


def layered(rng, sizes, density=1.0, r=4.5, hollow=False, dy=34, big=None, xa=600, xb=945):
    nodes, layers = [], []
    for d, (x, n) in enumerate(zip(_lin(xa, xb, len(sizes)), sizes)):
        ids = []
        for i in range(n):
            is_big = big is not None and d == big
            nodes.append(dict(x=x, y=CY + (i - (n - 1) / 2) * dy, d=d, r=r * (1.6 if is_big else 1),
                              shape="c", hollow=hollow and not is_big, big=is_big))
            ids.append(len(nodes) - 1)
        layers.append(ids)
    edges = []
    for la, lb in zip(layers, layers[1:]):
        for i, a in enumerate(la):
            near = round(i * (len(lb) - 1) / max(len(la) - 1, 1))
            for j, b in enumerate(lb):
                if density >= 1 or j == near or rng.random() < density:
                    edges.append((a, b, rng.uniform(.6, 1.6)))
    return Net(nodes, edges, "h", (xb, CY))


def current(rng):
    return layered(rng, [4, 6, 6, 2])


def finer(rng):
    return layered(rng, [3, 5, 6, 6, 5, 2], density=.45, r=3, hollow=True, dy=32, xa=X_MIN, xb=X_MAX)


def hourglass(rng):
    return layered(rng, [6, 4, 2, 1, 2, 4, 6], r=3.6, dy=32, big=3, xa=X_MIN, xb=X_MAX)


def transformer(rng, tokens=6, rows=4):
    xs, ys = _lin(612, 945, tokens), _lin(212, 40, rows)
    nodes = [dict(x=x, y=y, d=d, r=4.5, shape="s") for d, y in enumerate(ys) for x in xs]
    edges = []
    for d in range(rows - 1):
        for i in range(tokens):            # destination token in row d+1
            for j in range(i + 1):         # causal: attends to itself and earlier tokens
                if j == i:
                    edges.append((d * tokens + j, (d + 1) * tokens + i, 1.6))
                elif rng.random() < .45:
                    edges.append((d * tokens + j, (d + 1) * tokens + i, rng.uniform(.5, 1.3)))
    return Net(nodes, edges, "v", (xs[-1], ys[-1]))


def constellation(rng, n=22, min_dist=40):
    pts, tries = [], 0
    while len(pts) < n and tries < 20000:
        tries += 1
        p = (rng.uniform(X_MIN + 5, X_MAX), rng.uniform(35, 220))
        if all(math.dist(p, q) >= min_dist for q in pts):
            pts.append(p)
    pairs = set()
    for i, p in enumerate(pts):
        near = sorted(range(len(pts)), key=lambda j: math.dist(p, pts[j]))[1:4]
        pairs |= {tuple(sorted((i, j))) for j in near}
    adj = {i: set() for i in range(len(pts))}
    for a, b in pairs:
        adj[a].add(b); adj[b].add(a)
    # signals enter from the left edge and spread outward
    depth = {i: 0 for i, p in enumerate(pts) if p[0] < X_MIN + 45} or {min(range(len(pts)), key=lambda i: pts[i][0]): 0}
    frontier = list(depth)
    while frontier:
        nxt = []
        for a in frontier:
            for b in adj[a]:
                if b not in depth:
                    depth[b] = depth[a] + 1
                    nxt.append(b)
        frontier = nxt
    maxd = max(depth.values())
    nodes = [dict(x=x, y=y, d=depth.get(i, maxd), r=rng.uniform(2.2, 4), shape="c") for i, (x, y) in enumerate(pts)]
    edges = []
    for a, b in pairs:
        if nodes[a]["d"] > nodes[b]["d"]:
            a, b = b, a
        edges.append((a, b, rng.uniform(.6, 1.5)))
    out = max(range(len(nodes)), key=lambda i: (nodes[i]["d"], nodes[i]["x"]))
    return Net(nodes, edges, "s", (nodes[out]["x"], nodes[out]["y"]))


NETWORKS = dict(current=current, finer=finer, hourglass=hourglass, transformer=transformer, constellation=constellation)
