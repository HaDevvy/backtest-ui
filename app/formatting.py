"""Display helpers shared by the templates."""
import datetime as dt
from typing import Any

# (label, key fragments to look for in the flattened metrics)
_HEADLINE = [
    ("return", ("total_return", "cumulative_return", "return")),
    ("sharpe", ("sharpe",)),
    ("drawdown", ("max_drawdown", "drawdown")),
    ("benchmark", ("buy_hold", "benchmark")),
]


def fmt(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, float):
        if v != v:
            return "—"
        if abs(v) >= 1000:
            return f"{v:,.2f}"
        s = f"{v:.4f}".rstrip("0").rstrip(".")
        return "0" if s in ("", "-0") else s
    if isinstance(v, dt.datetime):
        return v.astimezone(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if isinstance(v, dt.date):
        return v.isoformat()
    return str(v)


def pct(v: Any) -> str:
    """Fraction -> signed percent (0.0123 -> +1.23%)."""
    if v is None:
        return "—"
    return f"{v * 100:+.2f}%"


def tone(v: Any) -> str:
    if v is None or v == 0:
        return ""
    return "pos" if v > 0 else "neg"


def pretty_key(key: str) -> str:
    text = str(key).replace("_", " ").replace(".", " › ")
    return text[:1].upper() + text[1:]


def duration(start: dt.datetime | None, end: dt.datetime | None) -> str:
    if not start or not end:
        return "—"
    secs = int((end - start).total_seconds())
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m"
    return f"{m}m {s:02d}s" if m else f"{s}s"


def flatten(data: Any, prefix: str = "") -> list[tuple[str, Any]]:
    if not isinstance(data, dict):
        return []
    out: list[tuple[str, Any]] = []
    for k, v in data.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out += flatten(v, key + ".")
        else:
            out.append((key, v))
    return out


def headline(metrics: Any, limit: int = 4) -> list[tuple[str, Any]]:
    """A few representative metrics. Metric names are whatever the backtest
    wrote, so match by key fragment and fall back to the first scalars."""
    flat = [(k, v) for k, v in flatten(metrics) if not isinstance(v, (list, dict))]
    picks: list[tuple[str, Any]] = []
    used: set[str] = set()
    for _, needles in _HEADLINE:
        for needle in needles:
            hit = next((kv for kv in flat if needle in kv[0].lower() and kv[0] not in used), None)
            if hit:
                used.add(hit[0])
                picks.append(hit)
                break
    for kv in flat:
        if len(picks) >= limit:
            break
        if kv[0] not in used:
            used.add(kv[0])
            picks.append(kv)
    return picks[:limit]
