# WBCSD CDR Decision Lab - Version 1.0

A WBCSD-branded Streamlit workshop application for moving from individual CDR barrier allocations to a coordinated breakout decision.

## V1.0 additions

- More polished WBCSD-branded interface.
- Automatic proportional rebalancing: each allocation always totals exactly 100.
- Functional +/-5 quick controls plus exact number entry.
- Low / average / high range plots instead of average-only bars.
- Facilitator-controlled live reveal. Participant pages poll for the reveal every 3 seconds.
- Submission locking / reopening controls.
- Priority and agreement heat maps by breakout.
- Breakout comparison view, including low / average / high for a selected barrier.
- Word cloud of qualitative responses.
- Local machine-learning theme clustering (TF-IDF + k-means); no participant text is sent to an external AI service.
- WBCSD-branded PDF workshop report generation.
- Excel export.
- Facilitator/admin pages hidden from ordinary participant URLs.

## Access model

Participants need no PIN.

Breakout leads use:

```toml
BREAKOUT_LEAD_PIN = "..."
```

Facilitators/admins use a different secret:

```toml
FACILITATOR_PIN = "..."
```

Facilitator pages are deliberately hidden from the ordinary interface. Open the deployed app with:

```text
https://your-app.streamlit.app/?staff=1
```

The facilitator PIN is still required after opening that URL.

Breakout leads can use a link such as:

```text
https://your-app.streamlit.app/?lead=1&workshop=WS-XXXXXXXX&group=B1
```

## Streamlit Cloud secrets

In Streamlit Community Cloud -> App settings -> Secrets, set:

```toml
FACILITATOR_PIN = "choose-a-strong-private-pin"
BREAKOUT_LEAD_PIN = "choose-a-different-breakout-pin"
DATABASE_URL = "postgresql+psycopg2://USER:PASSWORD@HOST:5432/postgres?sslmode=require"
```

Do not commit a real `.streamlit/secrets.toml` to GitHub.

## Database warning

SQLite is retained for local testing. For a real virtual workshop use persistent Postgres/Supabase via `DATABASE_URL`; Streamlit Community Cloud local storage should not be treated as a durable multi-user database.

## Run locally

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

pip install -r requirements.txt
python -m streamlit run app.py
```

Fallback local test PINs, used only if secrets are absent:

- Facilitator: `wbcsd-demo`
- Breakout lead: `breakout-demo`

## Recommended test flow

1. Open `http://localhost:8501/?staff=1`.
2. Create a workshop in **Workshop configuration**.
3. Open ordinary participant links in several browser/incognito sessions and submit responses.
4. In **Facilitator**, verify the live counts and then **Lock submissions**.
5. Click **Reveal results**. Submitted participant pages should reveal within roughly 3 seconds.
6. Use a breakout-lead link and save one coordinated allocation.
7. Return to the facilitator dashboard to inspect breakout heat maps, qualitative themes and generate the PDF report.
