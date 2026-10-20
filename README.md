# Backtest Review

Read-only web UI for the `backtests`, `backtest_days` and `backtest_agent_responses` tables,
plus the PostgreSQL service it reads from.

## Run

```bash
cp .env.example .env        # optional, defaults work
docker compose up --build
```

- UI: http://localhost:8000
- Postgres: `postgresql://backtest:backtest@localhost:5432/backtest`

Point your backtest process at that URL. It creates the tables (`Base.metadata.create_all`);
this project never creates or alters tables. Until they exist the UI shows a
"Waiting for the backtest tables" page and retries every 5 seconds.

`app/models.py` is a copy of your models file. Keep it identical to the one your backtest uses.

**Existing database?** `create_all` only creates missing tables; it never adds columns to tables that
already exist. If your tables were created before the review fields were added, run the migration once
(it is idempotent):

```bash
psql postgresql://backtest:backtest@localhost:5432/backtest -f migrations/001_add_review_columns.sql
```

Until then the UI shows a "database schema is out of date" page instead of failing.

## Architecture

```
backtest process ──writes──▶ PostgreSQL ◀──reads── UI (FastAPI + Jinja2, one container)
                                                    ├─ queries.py     all SQL, no HTML
                                                    ├─ formatting.py  number / date / metric helpers
                                                    ├─ charts.py      server-side SVG equity chart
                                                    └─ templates/     one small template per page
```

No JavaScript build step and no API layer to maintain: every page is rendered on the server
from a few focused queries. Large columns (`graph_png`, `equity_chart_png`, agent `output` and
`inputs`) are deferred, so lists stay fast; images stream from their own URLs
(`/backtests/{id}/graph.png`, `/backtests/{id}/equity.png`).

## Pages

Each page has one job, and detail sits one click deeper instead of all on one screen.

| URL | Shows |
|---|---|
| `/` | All runs: status filter, search, headline metrics |
| `/backtests/{id}` | Headline metrics, live equity curve vs buy and hold, rendered report chart, run details (incl. recheck totals), all metrics |
| `/backtests/{id}/days` | Trading days table with review verdict and recheck rounds, filter by signal, rechecked or errors, paginated |
| `/backtests/{id}/graph` | Agent graph image, YAML, Mermaid source |
| `/backtests/{id}/settings` | Run settings |
| `/backtests/{id}/days/{date}` | Tabs: Decision (proposed, risk level, review, final, fill), Market and portfolio, Agents (with review round) |
| `/backtests/{id}/days/{date}/agents/{n}` | One agent: output, or the evidence it was given, plus its review round |

Every column of the three tables is reachable somewhere in these pages.

## Notes

- Returns and drawdown are formatted as percentages and assume fractions (0.0123 is +1.23%).
  Change `pct` in `app/formatting.py` if you store percent values.
- Decision pipeline: proposed, risk level, review, final. `risk_level` (low / medium / high / unknown)
  is the risk assessment. `risk_verdict` is deprecated and only shown, as "Legacy verdict", on older runs
  that have it. The Review card appears only when a day has review data, so older runs look unchanged.
  `recheck_rounds` counts rechecks, and a NULL `approved_action` is shown as "None approved".
- In the Agents tab, a rule is drawn between rows whenever `review_round` changes. A NULL round shows as a dash.
- Badge colors are set per value in `style.css` (`.b-approved`, `.b-recheck`, `.b-low`, ...). Unknown
  values fall back to a neutral grey; add a class there if your reviewer uses other verdict words.
- Metrics are free-form JSON, so the "headline" tiles pick keys by name (return, sharpe,
  drawdown, buy_hold) and fall back to the first scalar metrics. Everything is under "All metrics".
- If a run has no stored graph image, the graph page draws the Mermaid source in the browser
  (loads mermaid from a CDN; the source is always shown too).
