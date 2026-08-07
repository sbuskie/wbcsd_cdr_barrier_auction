# WBCSD CDR Barrier Auction — Streamlit MVP

A live virtual workshop application for the CDR Barrier Auction.

## Features

### Participant
- Company, function, sector, CDR maturity and breakout code.
- Exactly **100 internal investment units**.
- Exactly **100 external enabling-environment units**.
- One concise qualitative response.
- Unique submission ID.

### Breakout lead
- Sees participant averages for the selected breakout.
- Captures one coordinated **100-unit internal** and **100-unit external** group decision.
- Records the group's rationale.
- Records one recommended WBCSD intervention.

### Facilitator
- Live internal and external rankings.
- Average, median, standard deviation and agreement indicator.
- Whole-workshop or breakout-specific views.
- Individual-average vs breakout-consensus comparison.
- Qualitative response table.
- Excel export.
- One-page breakout HTML report.

## Run locally

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

The app automatically creates `cdr_barrier_auction.db`.

The default facilitator PIN for local testing is:

```text
wbcsd-demo
```

Change it before sharing the app.

## Persistent database for a real workshop

The app falls back to SQLite locally. For deployment, set `DATABASE_URL` to a persistent Postgres database. A hosted Supabase Postgres database is a good fit.

Create `.streamlit/secrets.toml`:

```toml
FACILITATOR_PIN = "your-secure-pin"
DATABASE_URL = "postgresql+psycopg2://USER:PASSWORD@HOST:5432/postgres?sslmode=require"
```

The database tables are created automatically on first run.

## Breakout-specific participant links

Use a query parameter to pre-populate the breakout code:

```text
https://your-app.example/?group=BLUE3
```

Create one link or QR code per breakout.

## Recommended workshop flow

1. Individual allocation — 4–5 minutes.
2. Facilitator reveals individual results.
3. Breakout discusses rankings and areas of disagreement.
4. Breakout lead records one coordinated allocation.
5. Plenary compares independent views, group decisions and proposed WBCSD interventions.

## Branding

The app uses the supplied WBCSD horizontal charcoal logo, WBCSD 2024 primary palette and Arial as the Office-compatible fallback typeface.
