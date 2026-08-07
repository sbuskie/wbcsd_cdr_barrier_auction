# V1.1.2 active-workshop and public-results release

## Participant workshop control
- Participants can only submit to the workshop currently marked Active by the facilitator.
- The active workshop name is displayed in a disabled/greyed-out field rather than a selectable dropdown.
- Submission performs a fresh active-workshop check before writing, so an old browser session cannot write to a workshop that has since been deactivated.

## Public Results view
- Added a password-free **Results** view for all participants.
- Removed the show/hide/reveal-results workflow.
- Results mirrors only the facilitator's **Breakout comparison** content:
  - every breakout: participant low-average-high range vs coordinated decision
  - final coordinated allocation comparison
  - priority heat maps
  - agreement/disagreement heat maps
  - compare one barrier across breakouts
- It excludes Live overview, Qualitative intelligence, and Report & export.

## Publishing refreshed results
- Facilitator **Refresh results** still fetches a fresh facilitator snapshot.
- The same click now updates a lightweight database timestamp.
- Public Results views poll only that timestamp every five seconds; full result tables are reloaded only when the facilitator has published a new refresh.
- Participant allocation pages remain local and do not poll results while people are entering data.

## Submission controls
- Lock/Reopen submissions remains available.
- Show/Hide/Reveal results controls have been removed because Results is now a permanent public view.

# V1.1.1 performance release

## Participant performance
The participant data-entry area now runs inside a Streamlit fragment. Editing profile fields, typing values, or pressing -5/+5 reruns only that local fragment and does not reload workshop data from Supabase.

Participant database traffic is now:
1. Initial page/configuration load.
2. On **Submit my allocation**: one lock-state check and one INSERT.
3. After submission only: the existing reveal fragment polls the small workshop-state record until the facilitator reveals results.

## Connection pooling and startup
- The SQLAlchemy engine is cached as a Streamlit resource so reruns reuse the same connection pool.
- Database schema initialization/migrations run once per worker process rather than on every widget interaction.
- PostgreSQL/Supabase uses a small reusable SQLAlchemy connection pool.

## Cached configuration
Workshop and breakout configuration are cached for five minutes. Admin writes explicitly clear this cache.

## Facilitator refresh
The facilitator dashboard no longer fetches all participant/results data on every Streamlit interaction.
- Results are loaded once when the facilitator opens a workshop.
- **Refresh results** explicitly fetches the latest participant submissions and breakout consensus from Supabase.
- Filters, tabs, chart selections and other dashboard interactions operate against the local snapshot.
- The dashboard shows the timestamp of the current results snapshot.

Live controls (lock/reopen and reveal/hide) still write immediately to the database when clicked.

# V1.1.0 Supabase and workshop operations

## Supabase/PostgreSQL fix
PostgreSQL migrations now use `ADD COLUMN IF NOT EXISTS` instead of catching a failing `ALTER TABLE` inside a transaction. This fixes the `InFailedSqlTransaction` startup error encountered after connecting Streamlit to Supabase.

## Submission status
Facilitator and Workshop configuration views now show breakout-level status:
- expected participants (even split of the workshop target, for guidance only)
- submitted individual responses
- whether breakout consensus is complete
- a simple ready/not-ready indicator

## Workshop reset
Workshop configuration now includes a facilitator-only danger zone. Typing `RESET` enables a workshop-specific reset that:
- deletes participant submissions
- deletes breakout consensus allocations
- deletes associated qualitative responses
- resets locked/revealed state
- retains the workshop and breakout configuration

## Database status
Facilitator/admin views display the active backend and connection health, e.g. `Supabase PostgreSQL · connected`.

# V1.0.5 participant-shareable PDF report

The facilitator PDF now includes the same core information as the participant Reveal:

1. **Every breakout - participant range vs coordinated decision**
   - Internal barriers
   - External enabling environment
   - Low-to-high individual range
   - Participant average
   - Final coordinated breakout decision

2. **How the breakouts made their final allocations**
   - Stacked 100-unit internal budget comparison across all breakouts
   - Stacked 100-unit external enabling-priority comparison across all breakouts

The PDF then continues with the workshop-wide rankings, qualitative themes and breakout report-backs, including the group's rationale and recommended WBCSD intervention where submitted.

# V1.0.4 reveal and chart-legibility update

- Moved the low / average / high + breakout-decision chart legend to the bottom of every chart so it no longer overlaps the chart title.
- Simplified the participant Reveal view to mirror the facilitator's breakout-comparison experience.
- Reveal now contains only:
  1. Every breakout · participant range vs coordinated decision, using expandable breakout sections.
  2. How the breakouts made their final allocations, using stacked 100-unit comparisons for internal and external priorities.
- Removed the previous standalone reveal charts, heat maps and barrier-comparison content from the participant Reveal experience.
- Facilitator analytical views remain unchanged, apart from the improved bottom legend placement.

# V1.0.3 breakout decision and reveal update

- Breakout lead allocation is now sequential, matching the participant flow: Internal first, External second, then qualitative questions.
- New breakout allocations are pre-loaded with the rounded participant averages for that breakout. Rounding may leave a total slightly above or below 100, so the group must still make a deliberate final adjustment.
- Breakout rationale and intervention fields now use workshop-and-breakout-specific state keys. Switching from B1 to B2 therefore shows B2's own blank/input state rather than carrying B1 text across.
- Revealed participant results overlay the final breakout consensus as a charcoal diamond on the same low-average-high chart.
- Facilitator breakout views do the same.
- Facilitator comparison now contains a low-average-high + consensus view for every breakout.
- Added two whole-workshop stacked comparisons: final internal 100-unit allocation by breakout and final external 100-unit allocation by breakout.

# V1.0.2 participant UX update

- Participant allocations are sequential again: Internal investment first, then External enabling environment directly below it. There is no tab to miss.
- Removed proportional rebalancing completely.
- Editing a barrier changes only that barrier.
- −5 / +5 controls remain for quick adjustment, alongside exact numeric entry.
- Allocations start at zero.
- Participants cannot submit until both the internal and external allocations total exactly 100.
- Breakout consensus uses the same non-rebalancing allocation behaviour and cannot be saved until both consensus allocations total exactly 100.

# V1.0.1 deployment fix

This patch fixes workshop creation on deployments that retained an older SQLite schema and removes the `?staff=1` navigation gate.

## What changed
- Facilitator and Workshop configuration are now always visible in the sidebar.
- Both remain protected by `FACILITATOR_PIN`.
- Breakout lead remains separately protected by `BREAKOUT_LEAD_PIN`.
- Added an automatic SQLite migration so breakout codes such as `B1` can be reused across different workshops using the correct composite key `(workshop_id, breakout_code)`.
- Added a clearer error message if workshop creation still fails.

After pushing this version to GitHub, allow Streamlit to restart once before creating a new workshop.

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
