"""All database reads live here, so pages stay thin."""
import datetime as dt
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, defer

from .models import Backtest, BacktestAgentResponse as AR, BacktestDay as Day

STATUSES = ("running", "completed", "failed", "interrupted")
RUNS_PER_PAGE = 20
DAYS_PER_PAGE = 40


def paginate(total: int, page: int, size: int) -> dict:
    pages = max(1, -(-total // size))
    page = min(max(page, 1), pages)
    return {"page": page, "pages": pages, "total": total, "offset": (page - 1) * size, "size": size}


# ---- backtests ------------------------------------------------------------
def list_backtests(s: Session, status: str, text: str, page: int):
    conds = []
    if status in STATUSES:
        conds.append(Backtest.status == status)
    if text:
        like = f"%{text}%"
        conds.append(or_(Backtest.symbol.ilike(like), Backtest.name.ilike(like)))
    total = s.scalar(select(func.count()).select_from(Backtest).where(*conds)) or 0
    pg = paginate(total, page, RUNS_PER_PAGE)
    rows = s.scalars(
        select(Backtest).where(*conds).order_by(Backtest.created_at.desc())
        .offset(pg["offset"]).limit(RUNS_PER_PAGE)
    ).all()
    ids = [r.id for r in rows]
    counts = {}
    if ids:
        counts = dict(s.execute(
            select(Day.backtest_id, func.count()).where(Day.backtest_id.in_(ids)).group_by(Day.backtest_id)
        ).all())
    return rows, counts, pg


def status_counts(s: Session) -> dict:
    return dict(s.execute(select(Backtest.status, func.count()).group_by(Backtest.status)).all())


def get_backtest(s: Session, bid: uuid.UUID):
    return s.get(Backtest, bid)


def image_flags(s: Session, bid: uuid.UUID) -> dict:
    row = s.execute(
        select(Backtest.graph_png.isnot(None), Backtest.equity_chart_png.isnot(None)).where(Backtest.id == bid)
    ).one()
    return {"graph": bool(row[0]), "equity": bool(row[1])}


def image_bytes(s: Session, bid: uuid.UUID, kind: str):
    col = Backtest.graph_png if kind == "graph" else Backtest.equity_chart_png
    return s.scalar(select(col).where(Backtest.id == bid))


# ---- days -----------------------------------------------------------------
def day_summary(s: Session, bid: uuid.UUID) -> dict:
    row = s.execute(
        select(
            func.count(),
            func.count().filter(Day.status == "error"),
            func.count(Day.executed_action),
            func.count().filter(Day.recheck_rounds > 0),
            func.coalesce(func.sum(Day.recheck_rounds), 0),
        ).where(Day.backtest_id == bid)
    ).one()
    return {
        "days": row[0], "errors": row[1], "fills": row[2],
        "rechecked_days": row[3], "recheck_rounds": int(row[4]),
    }


def equity_points(s: Session, bid: uuid.UUID) -> list[dict]:
    rows = s.execute(
        select(Day.trade_date, Day.equity, Day.buy_hold_equity, Day.executed_action)
        .where(Day.backtest_id == bid, Day.equity.isnot(None)).order_by(Day.trade_date)
    ).all()
    return [{"date": r[0], "equity": r[1], "buy_hold": r[2], "action": r[3]} for r in rows]


def list_days(s: Session, bid: uuid.UUID, action: str, page: int):
    conds = [Day.backtest_id == bid]
    if action == "error":
        conds.append(Day.status == "error")
    elif action == "rechecked":
        conds.append(Day.recheck_rounds > 0)
    elif action in ("buy", "sell", "hold"):
        conds.append(func.lower(Day.final_action) == action)
    total = s.scalar(select(func.count()).select_from(Day).where(*conds)) or 0
    pg = paginate(total, page, DAYS_PER_PAGE)
    rows = s.scalars(
        select(Day).where(*conds).order_by(Day.trade_date).offset(pg["offset"]).limit(DAYS_PER_PAGE)
    ).all()
    return rows, pg


def get_day(s: Session, bid: uuid.UUID, trade_date: dt.date):
    return s.scalar(select(Day).where(Day.backtest_id == bid, Day.trade_date == trade_date))


def adjacent_days(s: Session, bid: uuid.UUID, trade_date: dt.date):
    prev_d = s.scalar(select(Day.trade_date).where(Day.backtest_id == bid, Day.trade_date < trade_date)
                      .order_by(Day.trade_date.desc()).limit(1))
    next_d = s.scalar(select(Day.trade_date).where(Day.backtest_id == bid, Day.trade_date > trade_date)
                      .order_by(Day.trade_date).limit(1))
    return prev_d, next_d


# ---- agent responses --------------------------------------------------------
def list_agent_responses(s: Session, day_id: int, attempt: int | None):
    attempts = list(s.scalars(select(AR.attempt).where(AR.day_id == day_id).distinct().order_by(AR.attempt)))
    if not attempts:
        return [], [], None
    attempt = attempt if attempt in attempts else attempts[-1]
    rows = s.scalars(
        select(AR).options(defer(AR.output), defer(AR.inputs))
        .where(AR.day_id == day_id, AR.attempt == attempt).order_by(AR.id)
    ).all()
    return rows, attempts, attempt


def get_agent_response(s: Session, day_id: int, agent_id: int):
    return s.scalar(select(AR).where(AR.id == agent_id, AR.day_id == day_id))


def adjacent_agents(s: Session, r: AR):
    rows = s.execute(
        select(AR.id, AR.agent).where(AR.day_id == r.day_id, AR.attempt == r.attempt).order_by(AR.id)
    ).all()
    ids = [x[0] for x in rows]
    i = ids.index(r.id)
    return (rows[i - 1] if i > 0 else None), (rows[i + 1] if i < len(rows) - 1 else None)
