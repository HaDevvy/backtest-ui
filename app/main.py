"""Backtest Review: read-only, server-rendered pages over the backtest tables.

  /                                   all runs
  /backtests/{id}                     overview (metrics, equity chart)
  /backtests/{id}/days                trading days
  /backtests/{id}/graph               agent graph (image, mermaid, yaml)
  /backtests/{id}/settings            run settings
  /backtests/{id}/days/{date}         one day (decision, market, agents)
  /backtests/{id}/days/{date}/agents/{n}   one agent response
"""
import datetime as dt
import uuid
from pathlib import Path
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import formatting as f
from . import queries as qry
from .charts import equity_svg
from .db import get_session

BASE = Path(__file__).parent
app = FastAPI(title="Backtest Review", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")


def url_with(request: Request, **changes) -> str:
    """Current URL with some query params changed (None/'' removes one)."""
    params = dict(request.query_params)
    for k, v in changes.items():
        if v in (None, ""):
            params.pop(k, None)
        else:
            params[k] = v
    qs = urlencode(params)
    return request.url.path + (f"?{qs}" if qs else "")


templates.env.filters.update(
    fmt=f.fmt, pct=f.pct, tone=f.tone, pretty_key=f.pretty_key,
    headline=f.headline, flatten=f.flatten, duration=f.duration,
)
templates.env.globals.update(url_with=url_with, statuses=qry.STATUSES)


def render(request: Request, name: str, status_code: int = 200, **ctx):
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def found(obj, what: str):
    if obj is None:
        raise HTTPException(404, f"{what} not found")
    return obj


# ---- error pages -------------------------------------------------------------
@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    return render(request, "error.html", status_code=exc.status_code,
                  title="Not found" if exc.status_code == 404 else "Something went wrong",
                  message=str(exc.detail))


@app.exception_handler(ProgrammingError)
@app.exception_handler(OperationalError)
async def db_not_ready(request: Request, exc):
    kind = type(getattr(exc, "orig", exc)).__name__
    return render(request, "waiting.html", status_code=503,
                  missing_tables=(kind == "UndefinedTable"),
                  # create_all never adds columns to existing tables, so a database
                  # created before the review fields existed needs the migration.
                  outdated_schema=(kind == "UndefinedColumn"),
                  detail=str(getattr(exc, "orig", exc)).splitlines()[0])


@app.get("/healthz")
def healthz():
    return {"ok": True}


# ---- pages -------------------------------------------------------------------
@app.get("/")
def index(request: Request, status: str = "", q: str = "", page: int = Query(1, ge=1),
          s: Session = Depends(get_session)):
    rows, day_counts, pg = qry.list_backtests(s, status, q.strip(), page)
    return render(request, "backtests.html", rows=rows, day_counts=day_counts, pg=pg,
                  status=status, q=q, totals=qry.status_counts(s))


def run_context(s: Session, bid: uuid.UUID, tab: str) -> dict:
    bt = found(qry.get_backtest(s, bid), "Backtest")
    return dict(bt=bt, tab=tab, summary=qry.day_summary(s, bid), images=qry.image_flags(s, bid))


@app.get("/backtests/{bid}")
def overview(request: Request, bid: uuid.UUID, s: Session = Depends(get_session)):
    ctx = run_context(s, bid, "overview")
    metrics = ctx["bt"].metrics
    return render(request, "backtest_overview.html", chart=equity_svg(qry.equity_points(s, bid)),
                  heads=f.headline(metrics), metrics=f.flatten(metrics), **ctx)


@app.get("/backtests/{bid}/days")
def days(request: Request, bid: uuid.UUID, action: str = "", page: int = Query(1, ge=1),
         s: Session = Depends(get_session)):
    ctx = run_context(s, bid, "days")
    rows, pg = qry.list_days(s, bid, action, page)
    return render(request, "backtest_days.html", rows=rows, pg=pg, action=action, **ctx)


@app.get("/backtests/{bid}/graph")
def graph(request: Request, bid: uuid.UUID, s: Session = Depends(get_session)):
    return render(request, "backtest_graph.html", **run_context(s, bid, "graph"))


@app.get("/backtests/{bid}/settings")
def settings(request: Request, bid: uuid.UUID, s: Session = Depends(get_session)):
    return render(request, "backtest_settings.html", **run_context(s, bid, "settings"))


def _png(s: Session, bid: uuid.UUID, kind: str) -> Response:
    data = found(qry.image_bytes(s, bid, kind), "Image")
    return Response(bytes(data), media_type="image/png", headers={"Cache-Control": "private, max-age=300"})


@app.get("/backtests/{bid}/graph.png")
def graph_png(bid: uuid.UUID, s: Session = Depends(get_session)):
    return _png(s, bid, "graph")


@app.get("/backtests/{bid}/equity.png")
def equity_png(bid: uuid.UUID, s: Session = Depends(get_session)):
    return _png(s, bid, "equity")


@app.get("/backtests/{bid}/days/{trade_date}")
def day(request: Request, bid: uuid.UUID, trade_date: dt.date, tab: str = "decision",
        attempt: int | None = None, s: Session = Depends(get_session)):
    bt = found(qry.get_backtest(s, bid), "Backtest")
    d = found(qry.get_day(s, bid, trade_date), "Day")
    tab = tab if tab in ("decision", "market", "agents") else "decision"
    prev_d, next_d = qry.adjacent_days(s, bid, trade_date)
    ctx = dict(bt=bt, d=d, tab=tab, prev_d=prev_d, next_d=next_d)
    if tab == "agents":
        ctx["responses"], ctx["attempts"], ctx["attempt"] = qry.list_agent_responses(s, d.id, attempt)
    return render(request, "day.html", **ctx)


@app.get("/backtests/{bid}/days/{trade_date}/agents/{agent_id}")
def agent(request: Request, bid: uuid.UUID, trade_date: dt.date, agent_id: int,
          view: str = "output", s: Session = Depends(get_session)):
    bt = found(qry.get_backtest(s, bid), "Backtest")
    d = found(qry.get_day(s, bid, trade_date), "Day")
    r = found(qry.get_agent_response(s, d.id, agent_id), "Agent response")
    prev_r, next_r = qry.adjacent_agents(s, r)
    view = view if view in ("output", "inputs") else "output"
    return render(request, "agent.html", bt=bt, d=d, r=r, prev_r=prev_r, next_r=next_r, view=view)
