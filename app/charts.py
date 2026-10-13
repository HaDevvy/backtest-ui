"""Server-rendered SVG equity chart (no JS needed)."""
from markupsafe import Markup, escape


def _short(v: float) -> str:
    a = abs(v)
    if a >= 1e6:
        return f"{v / 1e6:.2f}M"
    if a >= 1e3:
        return f"{v / 1e3:.1f}k"
    return f"{v:.2f}"


def equity_svg(points: list[dict]) -> Markup | None:
    pts = [p for p in points if p["equity"] is not None]
    if len(pts) < 2:
        return None
    W, H, L, R, T, B = 900, 300, 64, 16, 14, 30
    eq = [p["equity"] for p in pts]
    bh = [p["buy_hold"] for p in pts]
    has_bh = all(v is not None for v in bh)
    vals = eq + (bh if has_bh else [])
    lo, hi = min(vals), max(vals)
    if hi == lo:
        hi = lo + 1
    pad = (hi - lo) * 0.06
    lo, hi = lo - pad, hi + pad
    n = len(pts)

    def x(i: int) -> float:
        return L + (W - L - R) * i / (n - 1)

    def y(v: float) -> float:
        return T + (H - T - B) * (1 - (v - lo) / (hi - lo))

    def path(vs: list[float]) -> str:
        return "M" + " L".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vs))

    out = [f'<svg viewBox="0 0 {W} {H}" class="ec" role="img" aria-label="Equity curve compared with buy and hold">']
    for k in range(5):
        v = lo + (hi - lo) * k / 4
        yy = y(v)
        out.append(f'<line class="ec-grid" x1="{L}" x2="{W - R}" y1="{yy:.1f}" y2="{yy:.1f}"/>')
        out.append(f'<text class="ec-tick" x="{L - 8}" y="{yy + 4:.1f}" text-anchor="end">{_short(v)}</text>')
    for i, anchor in ((0, "start"), (n // 2, "middle"), (n - 1, "end")):
        out.append(f'<text class="ec-tick" x="{x(i):.1f}" y="{H - 8}" text-anchor="{anchor}">{pts[i]["date"].isoformat()}</text>')
    if has_bh:
        out.append(f'<path class="ec-bh" d="{path(bh)}"/>')
    out.append(f'<path class="ec-eq" d="{path(eq)}"/>')
    fills = [(i, p) for i, p in enumerate(pts) if (p["action"] or "").lower() in ("buy", "sell")]
    if len(fills) <= 250:
        for i, p in fills:
            side = str(p["action"]).lower()
            out.append(
                f'<circle class="ec-{side}" cx="{x(i):.1f}" cy="{y(eq[i]):.1f}" r="3.5">'
                f'<title>{escape(side)} on {p["date"].isoformat()}</title></circle>'
            )
    out.append("</svg>")
    return Markup("".join(out))
