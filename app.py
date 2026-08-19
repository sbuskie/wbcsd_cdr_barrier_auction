import io
import math
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from reportlab.lib import colors as rl_colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.graphics.shapes import Circle, Drawing, Line, Polygon, Rect, String
from reportlab.platypus import (
    Image as RLImage,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sqlalchemy import create_engine, text
from wordcloud import STOPWORDS, WordCloud

st.set_page_config(
    page_title="WBCSD CDR Decision Lab",
    page_icon="🧱",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------------------------------------------------------
# WBCSD visual system
# -----------------------------------------------------------------------------
COLORS = {
    "charcoal": "#2a2825",
    "pearl": "#f0ede6",
    "orange": "#f8781e",
    "olive": "#61704b",
    "spruce": "#465c66",
    "sky": "#b9c8d4",
    "sand": "#cab6a5",
    "sage": "#c3cbb6",
    "salmon": "#eb696d",
    "gold": "#ffcd69",
    "white": "#ffffff",
}

st.markdown(
    f"""
    <style>
    #MainMenu, footer {{visibility:hidden;}}
    header[data-testid="stHeader"] {{background: rgba(255,255,255,0);}}
    html, body, [class*="css"] {{font-family: Arial, sans-serif; color:{COLORS['charcoal']};}}
    .block-container {{padding-top: 1.0rem; padding-bottom: 3rem; max-width: 1500px;}}
    section[data-testid="stSidebar"] {{background:{COLORS['pearl']}; border-right:1px solid {COLORS['sand']};}}
    /* Sidebar view hierarchy */
    section[data-testid="stSidebar"] div[role="radiogroup"] > label:nth-child(1) p,
    section[data-testid="stSidebar"] div[role="radiogroup"] > label:nth-child(2) p {{
        color:{COLORS['charcoal']} !important;
        font-weight:600;
    }}
    section[data-testid="stSidebar"] div[role="radiogroup"] > label:nth-child(3) p {{
        color:{COLORS['orange']} !important;
        font-weight:700;
    }}
    section[data-testid="stSidebar"] div[role="radiogroup"] > label:nth-child(4) p,
    section[data-testid="stSidebar"] div[role="radiogroup"] > label:nth-child(5) p {{
        color:{COLORS['spruce']} !important;
        font-weight:700;
    }}
    .hero {{border-top:9px solid {COLORS['orange']}; background:{COLORS['charcoal']}; color:white;
            padding:1.35rem 1.5rem 1.2rem; border-radius:0 0 16px 16px; margin-bottom:1.4rem;}}
    .hero h1 {{font-size:2.0rem; margin:0 0 .35rem 0; font-weight:500; letter-spacing:-.03em;}}
    .hero p {{margin:0; color:{COLORS['pearl']}; max-width:900px;}}
    .eyebrow {{text-transform:uppercase; letter-spacing:.09em; font-size:.72rem; font-weight:700; color:{COLORS['orange']};}}
    .section-label {{font-size:.78rem; text-transform:uppercase; letter-spacing:.08em; color:{COLORS['spruce']}; font-weight:700;}}
    .callout {{background:{COLORS['pearl']}; border-left:5px solid {COLORS['orange']}; padding:.85rem 1rem; border-radius:8px;}}
    .success-box {{background:{COLORS['sage']}; padding:.75rem .9rem; border-radius:10px;}}
    .waiting-box {{background:{COLORS['sky']}; padding:.9rem 1rem; border-radius:10px;}}
    .locked-box {{background:{COLORS['sand']}; padding:.9rem 1rem; border-radius:10px;}}
    .allocation-row {{padding:.35rem 0 .05rem;}}
    .allocation-label {{font-weight:600; margin-bottom:.1rem;}}
    .required-field-label {{font-size:.875rem; font-weight:400; line-height:1.25rem; margin:0 0 .35rem 0;}}
    .required-asterisk {{color:#D71920; font-weight:700;}}
    .alloc-track {{height:8px;background:{COLORS['pearl']};border-radius:999px;overflow:hidden;margin-top:.2rem;}}
    .alloc-fill {{height:100%;background:{COLORS['orange']};border-radius:999px;}}
    .total-pill {{display:inline-block;padding:.28rem .75rem;border-radius:999px;background:{COLORS['sage']};font-weight:700;}}
    .reveal {{animation: revealFade .7s ease both;}}
    @keyframes revealFade {{from {{opacity:0;transform:translateY(8px)}} to {{opacity:1;transform:none}}}}
    div.stButton > button {{border-radius:999px; border:1px solid {COLORS['spruce']}; min-height:2.25rem;}}
    div.stButton > button[kind="primary"] {{background:{COLORS['orange']}; color:white; border-color:{COLORS['orange']};}}
    [data-testid="stMetric"] {{background:{COLORS['pearl']}; border:1px solid {COLORS['sand']}; padding:.8rem 1rem; border-radius:12px;}}
    [data-testid="stDataFrame"] {{border:1px solid {COLORS['sand']}; border-radius:12px; overflow:hidden;}}
    </style>
    """,
    unsafe_allow_html=True,
)

INTERNAL = [
    "Leadership buy-in",
    "Governance & decision-making",
    "Budget allocation",
    "Internal capability",
    "Procurement complexity",
]
EXTERNAL = [
    "Cost",
    "Standards & accounting",
    "Technology maturity",
    "Credit quality & integrity",
    "Customer demand",
    "Reputation / greenwashing risk",
    "Other",
]
MATURITY = ["Exploring", "Preparing internally", "Pilot", "Active buyer", "Scaling"]
FUNCTIONS = [
    "Sustainability", "Procurement", "Finance", "Strategy", "Operations",
    "Legal / Risk", "Executive leadership", "Other",
]
INTERNAL_DB = {
    "Leadership buy-in": "internal_leadership",
    "Governance & decision-making": "internal_governance",
    "Budget allocation": "internal_budget",
    "Internal capability": "internal_capability",
    "Procurement complexity": "internal_procurement",
}
EXTERNAL_DB = {
    "Cost": "external_cost",
    "Standards & accounting": "external_standards",
    "Technology maturity": "external_technology",
    "Credit quality & integrity": "external_quality",
    "Customer demand": "external_demand",
    "Reputation / greenwashing risk": "external_reputation",
    "Other": "external_other",
}

# -----------------------------------------------------------------------------
# Database
# -----------------------------------------------------------------------------
def get_secret(name, fallback=None):
    try:
        value = st.secrets.get(name)
    except Exception:
        value = None
    return value or os.getenv(name) or fallback

DATABASE_URL = get_secret("DATABASE_URL", "sqlite:///cdr_barrier_auction.db")


@st.cache_resource(show_spinner=False)
def get_engine(database_url):
    """Create one SQLAlchemy engine/pool per Streamlit worker process."""
    if database_url.startswith("sqlite"):
        return create_engine(
            database_url,
            pool_pre_ping=True,
            connect_args={"check_same_thread": False, "timeout": 30},
        )
    return create_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_recycle=300,
    )


engine = get_engine(DATABASE_URL)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


@st.cache_resource(show_spinner=False)
def init_db():
    """Initialise/migrate the schema once per Streamlit worker process."""
    with engine.begin() as conn:
        if DATABASE_URL.startswith("sqlite"):
            conn.execute(text("PRAGMA journal_mode=WAL;"))

        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS workshops (
            workshop_id TEXT PRIMARY KEY,
            workshop_name TEXT NOT NULL,
            event_name TEXT,
            event_date TEXT,
            participant_target INTEGER,
            duration_minutes INTEGER,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )"""))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS workshop_breakouts (
            workshop_id TEXT NOT NULL,
            breakout_code TEXT NOT NULL,
            breakout_name TEXT,
            PRIMARY KEY (workshop_id, breakout_code)
        )"""))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS workshop_state (
            workshop_id TEXT PRIMARY KEY,
            submissions_locked INTEGER NOT NULL DEFAULT 0,
            results_revealed INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        )"""))

        # V1.0.1 migration for older SQLite deployments.
        # CREATE TABLE IF NOT EXISTS does not alter an existing table, so if an
        # earlier deployment used breakout_code as the only primary key, B1/B2
        # can collide when a new workshop is created. Rebuild with the intended
        # composite primary key: (workshop_id, breakout_code).
        if DATABASE_URL.startswith("sqlite"):
            pk_rows = conn.execute(text("PRAGMA table_info(workshop_breakouts)")).fetchall()
            pk_cols = [row[1] for row in sorted(
                [r for r in pk_rows if int(r[5] or 0) > 0],
                key=lambda r: int(r[5])
            )]
            if pk_cols != ["workshop_id", "breakout_code"]:
                conn.execute(text("""
                    CREATE TABLE workshop_breakouts_v101 (
                        workshop_id TEXT NOT NULL,
                        breakout_code TEXT NOT NULL,
                        breakout_name TEXT,
                        PRIMARY KEY (workshop_id, breakout_code)
                    )
                """))
                existing_cols = {r[1] for r in pk_rows}
                if {"workshop_id", "breakout_code"}.issubset(existing_cols):
                    conn.execute(text("""
                        INSERT OR IGNORE INTO workshop_breakouts_v101
                            (workshop_id, breakout_code, breakout_name)
                        SELECT workshop_id, breakout_code, breakout_name
                        FROM workshop_breakouts
                        WHERE workshop_id IS NOT NULL AND breakout_code IS NOT NULL
                    """))
                conn.execute(text("DROP TABLE workshop_breakouts"))
                conn.execute(text("ALTER TABLE workshop_breakouts_v101 RENAME TO workshop_breakouts"))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS participant_submissions (
            submission_id TEXT PRIMARY KEY,
            submitted_at TEXT NOT NULL,
            workshop_id TEXT,
            participant_name TEXT,
            company TEXT,
            function_name TEXT,
            sector TEXT,
            cdr_maturity TEXT,
            breakout_code TEXT NOT NULL,
            internal_leadership INTEGER NOT NULL,
            internal_governance INTEGER NOT NULL,
            internal_budget INTEGER NOT NULL,
            internal_capability INTEGER NOT NULL,
            internal_procurement INTEGER NOT NULL,
            external_cost INTEGER NOT NULL,
            external_standards INTEGER NOT NULL,
            external_technology INTEGER NOT NULL,
            external_quality INTEGER NOT NULL,
            external_demand INTEGER NOT NULL,
            external_reputation INTEGER NOT NULL,
            external_other INTEGER NOT NULL,
            biggest_reason TEXT
        )"""))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS breakout_consensus (
            workshop_id TEXT,
            breakout_code TEXT NOT NULL,
            submitted_at TEXT NOT NULL,
            internal_leadership INTEGER NOT NULL,
            internal_governance INTEGER NOT NULL,
            internal_budget INTEGER NOT NULL,
            internal_capability INTEGER NOT NULL,
            internal_procurement INTEGER NOT NULL,
            external_cost INTEGER NOT NULL,
            external_standards INTEGER NOT NULL,
            external_technology INTEGER NOT NULL,
            external_quality INTEGER NOT NULL,
            external_demand INTEGER NOT NULL,
            external_reputation INTEGER NOT NULL,
            external_other INTEGER NOT NULL,
            rationale TEXT,
            wbcsd_intervention TEXT,
            PRIMARY KEY (workshop_id, breakout_code)
        )"""))

        # Database-aware migration for pre-V1.0 databases.
        # PostgreSQL aborts the entire transaction after a failed statement,
        # so never rely on try/except around ALTER TABLE there.
        if DATABASE_URL.startswith("sqlite"):
            for table_name, column_name, column_type in [
                ("participant_submissions", "workshop_id", "TEXT"),
                ("breakout_consensus", "workshop_id", "TEXT"),
            ]:
                existing = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
                existing_cols = {row[1] for row in existing}
                if column_name not in existing_cols:
                    conn.execute(text(
                        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
                    ))
        else:
            conn.execute(text(
                "ALTER TABLE participant_submissions "
                "ADD COLUMN IF NOT EXISTS workshop_id TEXT"
            ))
            conn.execute(text(
                "ALTER TABLE breakout_consensus "
                "ADD COLUMN IF NOT EXISTS workshop_id TEXT"
            ))

        # Ensure older configured workshops have state rows.
        workshop_ids = conn.execute(text("SELECT workshop_id FROM workshops")).fetchall()
        for (wid,) in workshop_ids:
            exists = conn.execute(text("SELECT workshop_id FROM workshop_state WHERE workshop_id=:wid"), {"wid": wid}).fetchone()
            if not exists:
                conn.execute(text("""
                    INSERT INTO workshop_state (workshop_id, submissions_locked, results_revealed, updated_at)
                    VALUES (:wid, 0, 0, :updated)
                """), {"wid": wid, "updated": now_iso()})


init_db()


def load_workshops():
    return pd.read_sql("SELECT * FROM workshops ORDER BY created_at DESC", engine)


def load_breakouts(workshop_id=None):
    if workshop_id:
        return pd.read_sql(
            text("SELECT * FROM workshop_breakouts WHERE workshop_id=:wid ORDER BY breakout_code"),
            engine, params={"wid": workshop_id},
        )
    return pd.read_sql("SELECT * FROM workshop_breakouts ORDER BY workshop_id, breakout_code", engine)



@st.cache_data(ttl=300, show_spinner=False)
def load_workshops_cached():
    return load_workshops()


@st.cache_data(ttl=300, show_spinner=False)
def load_breakouts_cached(workshop_id):
    return load_breakouts(workshop_id)


def clear_configuration_cache():
    load_workshops_cached.clear()
    load_breakouts_cached.clear()


def load_participants(workshop_id=None):
    if workshop_id:
        return pd.read_sql(
            text("SELECT * FROM participant_submissions WHERE workshop_id=:wid ORDER BY submitted_at"),
            engine, params={"wid": workshop_id},
        )
    return pd.read_sql("SELECT * FROM participant_submissions ORDER BY submitted_at", engine)


def load_consensus(workshop_id=None):
    if workshop_id:
        return pd.read_sql(
            text("SELECT * FROM breakout_consensus WHERE workshop_id=:wid ORDER BY breakout_code"),
            engine, params={"wid": workshop_id},
        )
    return pd.read_sql("SELECT * FROM breakout_consensus ORDER BY workshop_id, breakout_code", engine)



def database_backend_label():
    if DATABASE_URL.startswith("sqlite"):
        return "SQLite"
    if "supabase" in DATABASE_URL or "pooler.supabase.com" in DATABASE_URL:
        return "Supabase PostgreSQL"
    return "PostgreSQL"


@st.cache_data(ttl=60, show_spinner=False)
def database_health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def workshop_submission_status(workshop_id):
    breakouts = load_breakouts(workshop_id)
    participants = load_participants(workshop_id)
    consensus = load_consensus(workshop_id)
    workshops = load_workshops()
    ws = workshops[workshops["workshop_id"] == workshop_id]

    target = int(ws.iloc[0]["participant_target"] or 0) if not ws.empty else 0
    breakout_count = max(len(breakouts), 1)
    expected_per_breakout = int(round(target / breakout_count)) if target else None

    rows = []
    for _, br in breakouts.iterrows():
        code = br["breakout_code"]
        submitted = int((participants["breakout_code"] == code).sum()) if not participants.empty else 0
        consensus_done = bool((consensus["breakout_code"] == code).any()) if not consensus.empty else False
        rows.append({
            "Breakout": code,
            "Name": br.get("breakout_name") or "",
            "Expected": expected_per_breakout if expected_per_breakout is not None else "",
            "Submitted": submitted,
            "Consensus": "Complete" if consensus_done else "Pending",
            "Ready": (
                "Yes"
                if consensus_done and (expected_per_breakout is None or submitted >= expected_per_breakout)
                else "No"
            ),
        })
    return pd.DataFrame(rows)


def reset_workshop_responses(workshop_id):
    """Clear all response/result data while retaining workshop configuration."""
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM participant_submissions WHERE workshop_id=:wid"),
            {"wid": workshop_id},
        )
        conn.execute(
            text("DELETE FROM breakout_consensus WHERE workshop_id=:wid"),
            {"wid": workshop_id},
        )
        conn.execute(
            text("""
                UPDATE workshop_state
                SET submissions_locked=0,
                    results_revealed=0,
                    updated_at=:updated
                WHERE workshop_id=:wid
            """),
            {"wid": workshop_id, "updated": now_iso()},
        )


def load_workshop_state(workshop_id):
    with engine.begin() as conn:
        row = conn.execute(text("SELECT * FROM workshop_state WHERE workshop_id=:wid"), {"wid": workshop_id}).mappings().fetchone()
        if not row:
            conn.execute(text("""
                INSERT INTO workshop_state (workshop_id, submissions_locked, results_revealed, updated_at)
                VALUES (:wid, 0, 0, :updated)
            """), {"wid": workshop_id, "updated": now_iso()})
            return {"workshop_id": workshop_id, "submissions_locked": 0, "results_revealed": 0, "updated_at": now_iso()}
        return dict(row)


def update_workshop_state(workshop_id, locked=None, revealed=None):
    current = load_workshop_state(workshop_id)
    locked_value = int(current["submissions_locked"] if locked is None else locked)
    revealed_value = int(current["results_revealed"] if revealed is None else revealed)
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE workshop_state
            SET submissions_locked=:locked, results_revealed=:revealed, updated_at=:updated
            WHERE workshop_id=:wid
        """), {"locked": locked_value, "revealed": revealed_value, "updated": now_iso(), "wid": workshop_id})


def active_workshop():
    df = load_workshops()
    active = df[df["is_active"] == 1]
    return None if active.empty else active.iloc[0].to_dict()


def active_workshop_cached():
    df = load_workshops_cached()
    active = df[df["is_active"] == 1]
    return None if active.empty else active.iloc[0].to_dict()


def active_workshop_direct():
    """Fresh DB check used only at submission time."""
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT workshop_id, workshop_name, event_name, event_date,
                   participant_target, duration_minutes, is_active, created_at
            FROM workshops
            WHERE is_active=1
            ORDER BY created_at DESC
            LIMIT 1
        """)).mappings().first()
    return dict(row) if row else None


def touch_results_snapshot(workshop_id):
    """Signal public Results views that the facilitator published a new snapshot."""
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE workshop_state
                SET updated_at=:updated
                WHERE workshop_id=:wid
            """),
            {"wid": workshop_id, "updated": now_iso()},
        )


def set_active_workshop(workshop_id):
    """Make exactly one workshop active, or pass None to leave no active workshop."""
    with engine.begin() as conn:
        conn.execute(text("UPDATE workshops SET is_active=0"))
        if workshop_id:
            conn.execute(
                text("UPDATE workshops SET is_active=1 WHERE workshop_id=:wid"),
                {"wid": workshop_id},
            )
    clear_configuration_cache()


def delete_workshop(workshop_id):
    """Permanently remove a workshop and all of its associated data/configuration."""
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM participant_submissions WHERE workshop_id=:wid"),
            {"wid": workshop_id},
        )
        conn.execute(
            text("DELETE FROM breakout_consensus WHERE workshop_id=:wid"),
            {"wid": workshop_id},
        )
        conn.execute(
            text("DELETE FROM workshop_breakouts WHERE workshop_id=:wid"),
            {"wid": workshop_id},
        )
        conn.execute(
            text("DELETE FROM workshop_state WHERE workshop_id=:wid"),
            {"wid": workshop_id},
        )
        conn.execute(
            text("DELETE FROM workshops WHERE workshop_id=:wid"),
            {"wid": workshop_id},
        )
    clear_configuration_cache()
    st.session_state.pop(f"fac_snapshot_{workshop_id}", None)
    st.session_state.pop(f"fac_state_{workshop_id}", None)
    st.session_state.pop(f"public_results_snapshot_{workshop_id}", None)
    st.session_state.pop(f"public_results_token_{workshop_id}", None)

# -----------------------------------------------------------------------------
# Shared analysis
# -----------------------------------------------------------------------------
def agreement_label(std):
    if pd.isna(std):
        return "n/a"
    if std <= 8:
        return "High"
    if std <= 15:
        return "Medium"
    return "Low"


def summary_table(df, mapping):
    rows = []
    for label, col in mapping.items():
        s = pd.to_numeric(df[col], errors="coerce").dropna()
        rows.append({
            "Barrier": label,
            "Low": round(float(s.min()), 1) if len(s) else np.nan,
            "Average": round(float(s.mean()), 1) if len(s) else np.nan,
            "High": round(float(s.max()), 1) if len(s) else np.nan,
            "Median": round(float(s.median()), 1) if len(s) else np.nan,
            "Std dev": round(float(s.std(ddof=0)), 1) if len(s) else np.nan,
        })
    out = pd.DataFrame(rows).sort_values("Average", ascending=False).reset_index(drop=True)
    out.insert(0, "Rank", range(1, len(out) + 1))
    out["Agreement"] = out["Std dev"].apply(agreement_label)
    return out


def range_plot(df, mapping, title, marker_color):
    summary = summary_table(df, mapping).sort_values("Average", ascending=True)
    fig = go.Figure()
    for _, r in summary.iterrows():
        fig.add_trace(go.Scatter(
            x=[r["Low"], r["High"]], y=[r["Barrier"], r["Barrier"]], mode="lines",
            line=dict(color=COLORS["sand"], width=8), hoverinfo="skip", showlegend=False,
        ))
    fig.add_trace(go.Scatter(
        x=summary["Average"], y=summary["Barrier"], mode="markers",
        marker=dict(size=12, color=marker_color, line=dict(color=COLORS["charcoal"], width=1)),
        customdata=np.stack([summary["Low"], summary["High"], summary["Std dev"]], axis=-1),
        hovertemplate="<b>%{y}</b><br>Average %{x:.1f}<br>Low %{customdata[0]:.1f}<br>High %{customdata[1]:.1f}<br>Std dev %{customdata[2]:.1f}<extra></extra>",
        name="Average",
    ))
    fig.update_layout(
        title=title, height=max(330, 58 * len(summary)), xaxis_title="Allocation units",
        yaxis_title=None, xaxis=dict(range=[0, 100]), margin=dict(l=10, r=15, t=55, b=40),
        plot_bgcolor="white", paper_bgcolor="white", showlegend=False,
    )
    return fig


def breakout_heatmap(df, mapping, statistic="mean", title=""):
    if df.empty:
        return None
    grouped = df.groupby("breakout_code")
    rows = []
    for breakout, g in grouped:
        row = {"Breakout": breakout}
        for label, col in mapping.items():
            if statistic == "std":
                row[label] = float(g[col].std(ddof=0))
            else:
                row[label] = float(g[col].mean())
        rows.append(row)
    matrix = pd.DataFrame(rows).set_index("Breakout")
    fig = px.imshow(
        matrix, text_auto=".1f", aspect="auto",
        color_continuous_scale=[[0, COLORS["pearl"]], [0.5, COLORS["sky"]], [1, COLORS["orange"]]],
        labels=dict(color="Units" if statistic == "mean" else "Std dev"),
        title=title,
    )
    fig.update_layout(height=max(300, 62 * len(matrix)), margin=dict(l=10, r=10, t=55, b=10))
    return fig


def cluster_qualitative(texts):
    clean = [str(t).strip() for t in texts if str(t).strip()]
    if len(clean) < 4:
        return None, None
    k = min(5, max(2, round(math.sqrt(len(clean) / 2))))
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1, max_features=500)
    X = vectorizer.fit_transform(clean)
    if X.shape[1] < 2:
        return None, None
    k = min(k, len(clean), X.shape[0])
    model = KMeans(n_clusters=k, random_state=42, n_init=20)
    labels = model.fit_predict(X)
    terms = np.array(vectorizer.get_feature_names_out())
    theme_names = {}
    for cluster_id in range(k):
        center = model.cluster_centers_[cluster_id]
        top = terms[center.argsort()[::-1][:3]]
        theme_names[cluster_id] = " · ".join(top)
    rows = pd.DataFrame({"Response": clean, "Cluster": labels})
    rows["Theme"] = rows["Cluster"].map(theme_names)
    summary = rows.groupby(["Cluster", "Theme"]).size().reset_index(name="Responses").sort_values("Responses", ascending=False)
    return rows, summary


def make_wordcloud(texts):
    clean = " ".join(str(t).strip() for t in texts if str(t).strip())
    if not clean:
        return None
    custom_stopwords = set(STOPWORDS) | {
        "organisation", "organization", "company", "companies", "cdr", "carbon", "removal", "removals",
        "today", "moving", "faster", "biggest", "reason",
    }
    brand_words = [COLORS["spruce"], COLORS["olive"], COLORS["orange"], COLORS["charcoal"]]
    def brand_color(word, font_size, position, orientation, random_state=None, **kwargs):
        return brand_words[sum(ord(c) for c in word) % len(brand_words)]
    wc = WordCloud(
        width=1400, height=600, background_color="white", stopwords=custom_stopwords,
        max_words=70, prefer_horizontal=0.9, color_func=brand_color, random_state=42,
    ).generate(clean)
    return wc.to_array()

# -----------------------------------------------------------------------------
# Allocation UI - deliberate manual allocation, exact total required
# -----------------------------------------------------------------------------
def alloc_key(prefix, idx):
    return f"{prefix}__{idx}"


def init_allocation(prefix, labels, defaults=None):
    """Initialise once, then preserve every choice the user makes."""
    defaults = defaults or {}
    for i, label in enumerate(labels):
        key = alloc_key(prefix, i)
        if key not in st.session_state:
            st.session_state[key] = int(defaults.get(label, 0))


def nudge_allocation(prefix, labels, idx, delta):
    """Adjust only the selected barrier. Never rebalance other choices."""
    key = alloc_key(prefix, idx)
    current = int(st.session_state.get(key, 0))
    st.session_state[key] = int(max(0, min(100, current + delta)))


def allocation_editor(prefix, labels, help_text=None, defaults=None):
    init_allocation(prefix, labels, defaults=defaults)

    if help_text:
        st.caption(help_text)

    st.caption(
        "Allocate the 100 units deliberately. Changing one barrier will not alter any of your other choices. "
        "Use −5 / +5 for quick adjustments or type an exact value."
    )

    for i, label in enumerate(labels):
        c_label, c_minus, c_value, c_plus = st.columns(
            [5.2, 0.8, 1.25, 0.8],
            vertical_alignment="center",
        )
        value = int(st.session_state[alloc_key(prefix, i)])

        with c_label:
            st.markdown(
                f'<div class="allocation-row"><div class="allocation-label">{label}</div>'
                f'<div class="alloc-track"><div class="alloc-fill" style="width:{value}%"></div></div></div>',
                unsafe_allow_html=True,
            )

        with c_minus:
            st.button(
                "−5",
                key=f"{prefix}_minus_{i}",
                on_click=nudge_allocation,
                args=(prefix, labels, i, -5),
                use_container_width=True,
            )

        with c_value:
            st.number_input(
                label,
                min_value=0,
                max_value=100,
                step=1,
                key=alloc_key(prefix, i),
                label_visibility="collapsed",
            )

        with c_plus:
            st.button(
                "+5",
                key=f"{prefix}_plus_{i}",
                on_click=nudge_allocation,
                args=(prefix, labels, i, 5),
                use_container_width=True,
            )

    values = {
        label: int(st.session_state[alloc_key(prefix, i)])
        for i, label in enumerate(labels)
    }
    total = sum(values.values())
    remaining = 100 - total

    if total == 100:
        st.markdown(
            '<div class="ok"><b>100 / 100 allocated</b> · complete</div>',
            unsafe_allow_html=True,
        )
    elif total < 100:
        st.markdown(
            f'<div class="warn"><b>{total} / 100 allocated</b> · {remaining} units remaining</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="bad"><b>{total} / 100 allocated</b> · {-remaining} units over the limit</div>',
            unsafe_allow_html=True,
        )

    return values, total


def range_plot_with_consensus(df, mapping, title, color, consensus_row=None):
    """Low-average-high participant range with optional breakout consensus marker."""
    base = summary_table(df, mapping).sort_values("Average", ascending=True)

    fig = go.Figure()
    for _, r in base.iterrows():
        fig.add_trace(go.Scatter(
            x=[r["Low"], r["High"]],
            y=[r["Barrier"], r["Barrier"]],
            mode="lines",
            line=dict(color=COLORS["sand"], width=9),
            showlegend=False,
            hoverinfo="skip",
        ))

    fig.add_trace(go.Scatter(
        x=base["Average"],
        y=base["Barrier"],
        mode="markers",
        marker=dict(size=13, color=color),
        name="Participant average",
        customdata=np.stack([base["Low"], base["High"]], axis=-1),
        hovertemplate="%{y}<br>Average %{x:.1f}<br>Low %{customdata[0]:.1f}<br>High %{customdata[1]:.1f}<extra></extra>",
    ))

    if consensus_row is not None:
        consensus_values = []
        consensus_barriers = []
        for barrier in base["Barrier"]:
            db_col = mapping[barrier]
            value = consensus_row.get(db_col)
            if value is not None and not pd.isna(value):
                consensus_barriers.append(barrier)
                consensus_values.append(float(value))
        if consensus_values:
            fig.add_trace(go.Scatter(
                x=consensus_values,
                y=consensus_barriers,
                mode="markers",
                marker=dict(size=14, color=COLORS["charcoal"], symbol="diamond"),
                name="Breakout consensus",
                hovertemplate="%{y}<br>Consensus %{x:.0f}<extra></extra>",
            ))

    fig.update_layout(
        title=title,
        xaxis=dict(range=[0, 100], title="Allocation units"),
        yaxis_title=None,
        height=max(330, 58 * len(base) + 100),
        plot_bgcolor="white",
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.18,
            xanchor="left",
            x=0,
        ),
        margin=dict(l=10, r=20, t=55, b=85),
    )
    return fig


def consensus_comparison_chart(consensus_df, mapping, title):
    """100-unit stacked comparison of final coordinated allocations by breakout."""
    if consensus_df.empty:
        return None

    rows = []
    for _, r in consensus_df.sort_values("breakout_code").iterrows():
        for barrier, col in mapping.items():
            rows.append({
                "Breakout": r["breakout_code"],
                "Barrier": barrier,
                "Allocation": float(r[col]),
            })

    long_df = pd.DataFrame(rows)
    fig = px.bar(
        long_df,
        x="Breakout",
        y="Allocation",
        color="Barrier",
        barmode="stack",
        title=title,
    )
    fig.update_layout(
        yaxis=dict(range=[0, 100], title="Allocation units"),
        xaxis_title=None,
        height=430,
        legend_title_text="Barrier",
        margin=dict(l=10, r=20, t=60, b=20),
    )
    return fig


# -----------------------------------------------------------------------------
# PDF generation
# -----------------------------------------------------------------------------
def pdf_hex(hex_color):
    return rl_colors.HexColor(hex_color)


def build_pdf_report(workshop_row, participants, consensus, breakouts, theme_summary=None):
    """
    Generate a participant-shareable WBCSD report.

    The first section mirrors the live Reveal:
      1. Every breakout - participant low/average/high range vs coordinated decision.
      2. How the breakouts made their final allocations - stacked 100-unit comparison.
    It then adds workshop-wide rankings, qualitative themes and breakout report-backs.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=15*mm,
        leftMargin=15*mm,
        topMargin=17*mm,
        bottomMargin=17*mm,
        title=f"{workshop_row['workshop_name']} - CDR Decision Lab",
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="WTitle",
        parent=styles["Title"],
        fontName="Helvetica",
        fontSize=22,
        leading=25,
        textColor=pdf_hex(COLORS["charcoal"]),
        alignment=TA_LEFT,
        spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="WH2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        textColor=pdf_hex(COLORS["spruce"]),
        spaceBefore=9,
        spaceAfter=5,
    ))
    styles.add(ParagraphStyle(
        name="WH3",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=10.2,
        textColor=pdf_hex(COLORS["charcoal"]),
        spaceBefore=6,
        spaceAfter=3,
    ))
    styles.add(ParagraphStyle(
        name="WBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9.2,
        leading=12,
        textColor=pdf_hex(COLORS["charcoal"]),
    ))
    styles.add(ParagraphStyle(
        name="WSmall",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=9,
        textColor=pdf_hex(COLORS["spruce"]),
    ))

    story = []
    logo_path = Path("assets/wbcsd_logo.jpg")
    if logo_path.exists():
        story.append(RLImage(str(logo_path), width=58*mm, height=19*mm))
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph(workshop_row["workshop_name"], styles["WTitle"]))
    story.append(Paragraph(
        f"{workshop_row.get('event_name') or ''} | {workshop_row.get('event_date') or ''} | "
        f"{len(participants)} participant submissions | "
        f"{participants['breakout_code'].nunique() if not participants.empty else 0} breakouts",
        styles["WBody"],
    ))
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph(
        "This report captures the results revealed to participants: the range of individual views within each "
        "breakout, the participant average, the coordinated breakout decision, and the final 100-unit allocations "
        "made across all breakout groups.",
        styles["WBody"],
    ))

    def consensus_row_for(code):
        cdf = consensus[consensus["breakout_code"] == code]
        return cdf.iloc[0].to_dict() if not cdf.empty else None

    def pdf_range_chart(group_df, mapping, consensus_row, title):
        """
        Compact vector chart: barrier label, low-high line, average dot and
        coordinated-decision diamond on a 0-100 scale.
        """
        rows = []
        for barrier, col in mapping.items():
            rows.append({
                "Barrier": barrier,
                "Low": float(group_df[col].min()),
                "Average": float(group_df[col].mean()),
                "High": float(group_df[col].max()),
                "Consensus": (
                    float(consensus_row[col])
                    if consensus_row is not None
                    and col in consensus_row
                    and consensus_row[col] is not None
                    and not pd.isna(consensus_row[col])
                    else None
                ),
            })

        chart_width = 172*mm
        label_width = 61*mm
        plot_left = label_width + 7*mm
        plot_width = chart_width - plot_left - 6*mm
        row_height = 7.2*mm
        top_pad = 9*mm
        bottom_pad = 13*mm
        chart_height = top_pad + len(rows)*row_height + bottom_pad

        d = Drawing(chart_width, chart_height)

        # Title
        d.add(String(
            0,
            chart_height - 4.5*mm,
            title,
            fontName="Helvetica-Bold",
            fontSize=9.5,
            fillColor=pdf_hex(COLORS["charcoal"]),
        ))

        # Axis/grid
        grid_top = chart_height - top_pad - 1*mm
        grid_bottom = bottom_pad
        for tick in [0, 25, 50, 75, 100]:
            x = plot_left + (tick / 100.0) * plot_width
            d.add(Line(
                x, grid_bottom, x, grid_top,
                strokeColor=pdf_hex(COLORS["pearl"]),
                strokeWidth=0.8,
            ))
            d.add(String(
                x - 3*mm, 4.7*mm, str(tick),
                fontName="Helvetica",
                fontSize=6.4,
                fillColor=pdf_hex(COLORS["spruce"]),
            ))

        for idx, r in enumerate(rows):
            y = grid_top - idx*row_height - 3.5*mm
            label = r["Barrier"]
            if len(label) > 31:
                label = label[:29] + "..."
            d.add(String(
                0, y - 1.8,
                label,
                fontName="Helvetica",
                fontSize=7.2,
                fillColor=pdf_hex(COLORS["charcoal"]),
            ))

            x_low = plot_left + (r["Low"]/100.0)*plot_width
            x_avg = plot_left + (r["Average"]/100.0)*plot_width
            x_high = plot_left + (r["High"]/100.0)*plot_width

            d.add(Line(
                x_low, y, x_high, y,
                strokeColor=pdf_hex(COLORS["sand"]),
                strokeWidth=5.5,
                strokeLineCap=1,
            ))
            d.add(Circle(
                x_avg, y, 2.1*mm,
                fillColor=pdf_hex(COLORS["orange"]),
                strokeColor=pdf_hex(COLORS["orange"]),
            ))

            if r["Consensus"] is not None:
                x_c = plot_left + (r["Consensus"]/100.0)*plot_width
                s = 2.4*mm
                d.add(Polygon(
                    [x_c, y+s, x_c+s, y, x_c, y-s, x_c-s, y],
                    fillColor=pdf_hex(COLORS["charcoal"]),
                    strokeColor=pdf_hex(COLORS["charcoal"]),
                ))

            d.add(String(
                chart_width - 5*mm, y - 1.8,
                f"{r['Average']:.1f}",
                textAnchor="end",
                fontName="Helvetica-Bold",
                fontSize=6.8,
                fillColor=pdf_hex(COLORS["orange"]),
            ))

        # Legend at bottom - deliberately away from the title.
        legend_y = 1.4*mm
        lx = plot_left
        d.add(Line(
            lx, legend_y + 1.8*mm, lx + 8*mm, legend_y + 1.8*mm,
            strokeColor=pdf_hex(COLORS["sand"]),
            strokeWidth=4.5,
        ))
        d.add(String(
            lx + 10*mm, legend_y,
            "Low-high",
            fontName="Helvetica",
            fontSize=6.5,
            fillColor=pdf_hex(COLORS["spruce"]),
        ))
        lx += 31*mm
        d.add(Circle(
            lx, legend_y + 1.8*mm, 1.7*mm,
            fillColor=pdf_hex(COLORS["orange"]),
            strokeColor=pdf_hex(COLORS["orange"]),
        ))
        d.add(String(
            lx + 4*mm, legend_y,
            "Participant average",
            fontName="Helvetica",
            fontSize=6.5,
            fillColor=pdf_hex(COLORS["spruce"]),
        ))
        lx += 43*mm
        s = 1.9*mm
        d.add(Polygon(
            [lx, legend_y+1.8*mm+s, lx+s, legend_y+1.8*mm, lx, legend_y+1.8*mm-s, lx-s, legend_y+1.8*mm],
            fillColor=pdf_hex(COLORS["charcoal"]),
            strokeColor=pdf_hex(COLORS["charcoal"]),
        ))
        d.add(String(
            lx + 4*mm, legend_y,
            "Breakout decision",
            fontName="Helvetica",
            fontSize=6.5,
            fillColor=pdf_hex(COLORS["spruce"]),
        ))
        return d

    def pdf_consensus_stacked_chart(consensus_df, mapping, title):
        """Stacked 100-unit horizontal bars comparing final breakout decisions."""
        chart_width = 172*mm
        label_width = 27*mm
        plot_left = label_width
        plot_width = chart_width - plot_left - 4*mm
        row_height = 10*mm
        top_pad = 10*mm
        legend_rows = math.ceil(len(mapping) / 3)
        bottom_pad = (legend_rows * 8 + 7)*mm
        chart_height = top_pad + max(1, len(consensus_df))*row_height + bottom_pad

        d = Drawing(chart_width, chart_height)
        d.add(String(
            0,
            chart_height - 4.5*mm,
            title,
            fontName="Helvetica-Bold",
            fontSize=10,
            fillColor=pdf_hex(COLORS["charcoal"]),
        ))

        palette = [
            COLORS["orange"], COLORS["spruce"], COLORS["olive"],
            COLORS["sky"], COLORS["sand"], COLORS["sage"], COLORS["salmon"],
        ]
        categories = list(mapping.items())
        y_top = chart_height - top_pad - 2*mm

        for ridx, (_, r) in enumerate(consensus_df.sort_values("breakout_code").iterrows()):
            y = y_top - ridx*row_height - 4*mm
            d.add(String(
                0, y - 1.8,
                str(r["breakout_code"]),
                fontName="Helvetica-Bold",
                fontSize=7.5,
                fillColor=pdf_hex(COLORS["charcoal"]),
            ))
            x = plot_left
            for cidx, (barrier, col) in enumerate(categories):
                val = max(0.0, float(r[col] or 0))
                seg_w = (val / 100.0) * plot_width
                if seg_w > 0:
                    d.add(Rect(
                        x, y - 2.7*mm, seg_w, 5.4*mm,
                        fillColor=pdf_hex(palette[cidx % len(palette)]),
                        strokeColor=rl_colors.white,
                        strokeWidth=0.35,
                    ))
                    if seg_w >= 11*mm:
                        d.add(String(
                            x + seg_w/2, y - 1.4,
                            f"{int(round(val))}",
                            textAnchor="middle",
                            fontName="Helvetica-Bold",
                            fontSize=6.2,
                            fillColor=pdf_hex(COLORS["charcoal"]),
                        ))
                x += seg_w

        # Legend below bars
        legend_y_top = bottom_pad - 8*mm
        col_w = chart_width / 3
        for idx, (barrier, _) in enumerate(categories):
            row = idx // 3
            col = idx % 3
            x = col * col_w
            y = legend_y_top - row*8*mm
            d.add(Rect(
                x, y, 4*mm, 4*mm,
                fillColor=pdf_hex(palette[idx % len(palette)]),
                strokeColor=None,
            ))
            label = barrier if len(barrier) <= 28 else barrier[:26] + "..."
            d.add(String(
                x + 6*mm, y + 0.4*mm,
                label,
                fontName="Helvetica",
                fontSize=6.4,
                fillColor=pdf_hex(COLORS["spruce"]),
            ))
        return d

    # ------------------------------------------------------------------
    # REVEALED RESULTS SUMMARY
    # ------------------------------------------------------------------
    story.append(PageBreak())
    story.append(Paragraph("Revealed results summary", styles["WTitle"]))
    story.append(Paragraph(
        "The following pages reproduce the core results shown to participants during the live reveal.",
        styles["WBody"],
    ))
    story.append(Spacer(1, 3*mm))

    story.append(Paragraph(
        "Every breakout - participant range vs coordinated decision",
        styles["WH2"],
    ))
    story.append(Paragraph(
        "The line is the lowest-to-highest individual response within the breakout. "
        "The orange dot is the participant average. The charcoal diamond is the final coordinated allocation "
        "submitted by the breakout lead.",
        styles["WBody"],
    ))

    if participants.empty:
        story.append(Paragraph("No participant responses were recorded.", styles["WBody"]))
    else:
        for _, br in breakouts.iterrows():
            code = br["breakout_code"]
            group = participants[participants["breakout_code"] == code]
            if group.empty:
                continue
            c_row = consensus_row_for(code)

            story.append(Spacer(1, 4*mm))
            title = f"{code}"
            if br.get("breakout_name"):
                title += f" - {br.get('breakout_name')}"
            title += f" | {len(group)} participant responses"
            story.append(Paragraph(title, styles["WH3"]))
            story.append(pdf_range_chart(
                group,
                INTERNAL_DB,
                c_row,
                "Internal barriers",
            ))
            story.append(Spacer(1, 2*mm))
            story.append(pdf_range_chart(
                group,
                EXTERNAL_DB,
                c_row,
                "External enabling environment",
            ))
            if c_row is None:
                story.append(Paragraph(
                    "No coordinated breakout allocation had been submitted at the time this report was generated.",
                    styles["WSmall"],
                ))
            story.append(PageBreak())

    story.append(Paragraph("How the breakouts made their final allocations", styles["WTitle"]))
    story.append(Paragraph(
        "Each bar totals 100 and shows the final coordinated allocation submitted by that breakout. "
        "These charts make it easy to compare where the groups converged and where they made different trade-offs.",
        styles["WBody"],
    ))
    story.append(Spacer(1, 4*mm))

    if consensus.empty:
        story.append(Paragraph("No breakout coordinated allocations were submitted.", styles["WBody"]))
    else:
        story.append(pdf_consensus_stacked_chart(
            consensus,
            INTERNAL_DB,
            "Internal budget - breakout comparison",
        ))
        story.append(Spacer(1, 6*mm))
        story.append(pdf_consensus_stacked_chart(
            consensus,
            EXTERNAL_DB,
            "External enabling priorities - breakout comparison",
        ))

    # ------------------------------------------------------------------
    # WORKSHOP-WIDE SUMMARY
    # ------------------------------------------------------------------
    story.append(PageBreak())
    story.append(Paragraph("Workshop-wide summary", styles["WTitle"]))

    def add_summary_section(title, mapping):
        story.append(Paragraph(title, styles["WH2"]))
        sm = summary_table(participants, mapping)
        data = [["Rank", "Barrier", "Low", "Average", "High", "Agreement"]] + [
            [int(r["Rank"]), r["Barrier"], r["Low"], r["Average"], r["High"], r["Agreement"]]
            for _, r in sm.iterrows()
        ]
        table = Table(
            data,
            colWidths=[11*mm, 66*mm, 18*mm, 21*mm, 18*mm, 24*mm],
            repeatRows=1,
        )
        table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), pdf_hex(COLORS["charcoal"])),
            ("TEXTCOLOR", (0,0), (-1,0), rl_colors.white),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTNAME", (0,1), (-1,-1), "Helvetica"),
            ("FONTSIZE", (0,0), (-1,-1), 8),
            ("GRID", (0,0), (-1,-1), .35, pdf_hex(COLORS["sand"])),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [rl_colors.white, pdf_hex(COLORS["pearl"])]),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("LEFTPADDING", (0,0), (-1,-1), 4),
            ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ]))
        story.append(table)

    if not participants.empty:
        add_summary_section("Internal investment priorities", INTERNAL_DB)
        add_summary_section("External enabling environment", EXTERNAL_DB)

    if theme_summary is not None and not theme_summary.empty:
        story.append(Paragraph("Qualitative themes", styles["WH2"]))
        data = [["Theme", "Responses"]] + [
            [r["Theme"], int(r["Responses"])]
            for _, r in theme_summary.iterrows()
        ]
        table = Table(data, colWidths=[130*mm, 28*mm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), pdf_hex(COLORS["spruce"])),
            ("TEXTCOLOR", (0,0), (-1,0), rl_colors.white),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTNAME", (0,1), (-1,-1), "Helvetica"),
            ("FONTSIZE", (0,0), (-1,-1), 8.5),
            ("GRID", (0,0), (-1,-1), .35, pdf_hex(COLORS["sand"])),
        ]))
        story.append(table)

    # ------------------------------------------------------------------
    # BREAKOUT REPORT-BACKS
    # ------------------------------------------------------------------
    story.append(PageBreak())
    story.append(Paragraph("Breakout report-backs", styles["WTitle"]))

    for _, br in breakouts.iterrows():
        code = br["breakout_code"]
        group = participants[participants["breakout_code"] == code]
        c_row_df = consensus[consensus["breakout_code"] == code]

        story.append(Paragraph(
            f"{code} - {br.get('breakout_name') or ''}",
            styles["WH2"],
        ))

        if group.empty:
            story.append(Paragraph("No participant responses recorded.", styles["WBody"]))
            continue

        int_top = summary_table(group, INTERNAL_DB).iloc[0]
        ext_top = summary_table(group, EXTERNAL_DB).iloc[0]

        summary_data = [
            ["Submissions", len(group)],
            ["Highest internal priority", f"{int_top['Barrier']} ({int_top['Average']:.1f})"],
            ["Highest external priority", f"{ext_top['Barrier']} ({ext_top['Average']:.1f})"],
        ]

        if not c_row_df.empty:
            crow = c_row_df.iloc[0]
            summary_data.append([
                "Recommended WBCSD intervention",
                crow["wbcsd_intervention"] or "Not recorded",
            ])

        t = Table(summary_data, colWidths=[48*mm, 110*mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (0,-1), pdf_hex(COLORS["pearl"])),
            ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
            ("FONTNAME", (1,0), (1,-1), "Helvetica"),
            ("FONTSIZE", (0,0), (-1,-1), 8.2),
            ("GRID", (0,0), (-1,-1), .35, pdf_hex(COLORS["sand"])),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
        ]))
        story.append(t)

        if not c_row_df.empty:
            crow = c_row_df.iloc[0]
            story.append(Spacer(1, 3*mm))
            story.append(Paragraph(
                "<b>Why the group made this allocation</b>",
                styles["WBody"],
            ))
            story.append(Paragraph(
                crow["rationale"] or "Not recorded",
                styles["WBody"],
            ))
        story.append(Spacer(1, 4*mm))

    def footer(canvas, doc_obj):
        canvas.saveState()
        canvas.setFillColor(pdf_hex(COLORS["orange"]))
        canvas.rect(0, 0, A4[0], 4*mm, fill=1, stroke=0)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(pdf_hex(COLORS["charcoal"]))
        canvas.drawRightString(
            A4[0]-15*mm,
            8*mm,
            f"WBCSD CDR Decision Lab | Page {doc_obj.page}",
        )
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    buf.seek(0)
    return buf.getvalue()

# -----------------------------------------------------------------------------
# App chrome / access
# -----------------------------------------------------------------------------
def header():
    c1, c2 = st.columns([1.1, 5.9], vertical_alignment="center")
    with c1:
        st.image("assets/wbcsd_logo.jpg", use_container_width=True)
    with c2:
        st.markdown(
            """
            <div class="hero">
              <div class="eyebrow">CDR Decision Lab</div>
              <h1>From individual barriers to collective action</h1>
              <p>Allocate 100 units independently, explore where perspectives diverge, then make one coordinated breakout decision.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )


def check_breakout_pin():
    expected = get_secret("BREAKOUT_LEAD_PIN", "breakout-demo")
    supplied = st.text_input("Breakout lead PIN", type="password", key="breakout_pin")
    if supplied != expected:
        st.info("Enter the breakout lead PIN to continue.")
        return False
    return True


def check_facilitator_pin(key="facilitator_pin"):
    expected = get_secret("FACILITATOR_PIN", "wbcsd-demo")
    supplied = st.text_input("Facilitator PIN", type="password", key=key)
    if supplied != expected:
        st.info("Enter the facilitator PIN to continue.")
        return False
    return True


def select_workshop(label="Workshop", key="workshop_select"):
    workshops = load_workshops()
    if workshops.empty:
        return None
    options = workshops["workshop_id"].tolist()
    labels = {r["workshop_id"]: f'{r["workshop_name"]} · {r["event_name"] or "Workshop"}' for _, r in workshops.iterrows()}
    active = active_workshop()
    default_index = options.index(active["workshop_id"]) if active and active["workshop_id"] in options else 0
    return st.selectbox(label, options, index=default_index, format_func=lambda x: labels[x], key=key)

# -----------------------------------------------------------------------------
# Participant result reveal fragment
# -----------------------------------------------------------------------------
@st.fragment(run_every="3s")
def participant_reveal_fragment(workshop_id, breakout_code):
    """
    This is the only participant-side polling.
    It runs only after a response has been submitted, so allocation inputs never
    trigger Supabase reads while the participant is deciding.
    """
    state = load_workshop_state(workshop_id)
    if not bool(state["results_revealed"]):
        st.markdown(
            '<div class="waiting-box"><b>Response received.</b> Results are hidden until the facilitator triggers the live reveal.</div>',
            unsafe_allow_html=True,
        )
        return

    participants = load_participants(workshop_id)
    consensus = load_consensus(workshop_id)
    breakouts = load_breakouts_cached(workshop_id)

    st.markdown(
        '<div class="reveal"><div class="callout"><b>Results revealed</b> - compare how each breakout thought about the barriers and the coordinated decisions they ultimately made.</div></div>',
        unsafe_allow_html=True,
    )

    st.markdown("### Every breakout · participant range vs coordinated decision")
    st.caption(
        "Open each breakout to see the lowest-to-highest individual response, the participant average, "
        "and the final coordinated allocation submitted by the breakout lead."
    )

    for code in breakouts["breakout_code"].tolist():
        group_df = participants[participants["breakout_code"] == code]
        if group_df.empty:
            continue

        cdf = consensus[consensus["breakout_code"] == code]
        consensus_row = cdf.iloc[0].to_dict() if not cdf.empty else None

        breakout_name_series = breakouts.loc[breakouts["breakout_code"] == code, "breakout_name"]
        breakout_name = breakout_name_series.iloc[0] if not breakout_name_series.empty else ""
        label = f"{code}"
        if breakout_name:
            label += f" · {breakout_name}"
        label += f" · {len(group_df)} participant responses"

        with st.expander(label, expanded=False):
            left, right = st.columns(2)
            with left:
                st.plotly_chart(
                    range_plot_with_consensus(
                        group_df, INTERNAL_DB, "Internal barriers",
                        COLORS["orange"], consensus_row,
                    ),
                    use_container_width=True,
                    key=f"reveal_range_int_{workshop_id}_{code}",
                )
            with right:
                st.plotly_chart(
                    range_plot_with_consensus(
                        group_df, EXTERNAL_DB, "External enabling environment",
                        COLORS["spruce"], consensus_row,
                    ),
                    use_container_width=True,
                    key=f"reveal_range_ext_{workshop_id}_{code}",
                )

            if consensus_row is None:
                st.caption(
                    "The coordinated-decision marker will appear when this breakout submits its final allocation."
                )

    st.markdown("### How the breakouts made their final allocations")
    st.caption(
        "Each stacked column totals 100 and shows the final coordinated allocation submitted by that breakout."
    )

    if consensus.empty:
        st.info("No breakout coordinated allocations have been submitted yet.")
    else:
        left, right = st.columns(2)
        with left:
            fig = consensus_comparison_chart(
                consensus, INTERNAL_DB, "Internal budget · breakout comparison"
            )
            if fig is not None:
                st.plotly_chart(
                    fig,
                    use_container_width=True,
                    key=f"reveal_consensus_internal_{workshop_id}",
                )
        with right:
            fig = consensus_comparison_chart(
                consensus, EXTERNAL_DB, "External enabling priorities · breakout comparison"
            )
            if fig is not None:
                st.plotly_chart(
                    fig,
                    use_container_width=True,
                    key=f"reveal_consensus_external_{workshop_id}",
                )


@st.fragment
def participant_input_fragment(wid, breakouts, default_breakout_index):
    """
    Entire participant data-entry experience runs locally in a Streamlit fragment.
    Number inputs, +/-5 buttons, profile fields and text edits do not rerun the
    outer app and therefore do not read from Supabase.

    The database is touched only when Submit my allocation is clicked:
      1. one lock-state check
      2. one INSERT
    """
    breakout_codes = breakouts["breakout_code"].tolist()

    with st.expander("About you", expanded=True):
        a, b, c = st.columns(3)
        with a:
            participant_name = st.text_input("Name (optional)", key=f"p_name_{wid}")
            st.markdown(
                '<div class="required-field-label">Company <span class="required-asterisk">*</span></div>',
                unsafe_allow_html=True,
            )
            company = st.text_input("Company", key=f"p_company_{wid}", label_visibility="collapsed")
        with b:
            function_name = st.selectbox("Function", FUNCTIONS, key=f"p_function_{wid}")
            st.markdown(
                '<div class="required-field-label">Sector <span class="required-asterisk">*</span></div>',
                unsafe_allow_html=True,
            )
            sector = st.text_input("Sector", key=f"p_sector_{wid}", label_visibility="collapsed")
        with c:
            cdr_maturity = st.selectbox("CDR maturity", MATURITY, key=f"p_maturity_{wid}")
            breakout_code = st.selectbox(
                "Breakout",
                breakout_codes,
                index=default_breakout_index,
                format_func=lambda code: (
                    f"{code} · " +
                    str(
                        breakouts.loc[
                            breakouts["breakout_code"] == code,
                            "breakout_name"
                        ].iloc[0] or ""
                    )
                ).rstrip(" ·"),
                key=f"p_breakout_{wid}",
            )

    st.markdown("### Internal investment · 100 units")
    st.write(
        "Prioritise barriers your company can directly address through budget, capability and internal decision-making."
    )
    internal_values, internal_total = allocation_editor(f"p_int_{wid}", INTERNAL)

    st.markdown("---")
    st.markdown("### External enabling environment · 100 units")
    st.write(
        "Now allocate a separate 100 influence units across external conditions that need progress through "
        "advocacy, standards, market development or collective action. These are not taken from the internal 100."
    )
    external_values, external_total = allocation_editor(f"p_ext_{wid}", EXTERNAL)

    st.markdown("---")
    biggest_reason = st.text_area(
        "What is the single biggest reason your organisation is not moving faster on CDR today?",
        max_chars=300,
        placeholder="One concise sentence...",
        key=f"p_reason_{wid}",
    )

    profile_ready = bool(company.strip()) and bool(sector.strip())
    allocations_ready = internal_total == 100 and external_total == 100
    ready = profile_ready and allocations_ready

    if not profile_ready:
        st.caption("Company and Sector are required.")
    if not allocations_ready:
        st.caption("Complete both 100-unit allocations before submitting.")

    if st.button(
        "Submit my allocation",
        type="primary",
        disabled=not ready,
        use_container_width=True,
        key=f"p_submit_{wid}",
    ):
        # Fresh database checks only when the participant actually submits.
        active_now = active_workshop_direct()
        if not active_now or active_now["workshop_id"] != wid:
            st.error(
                "This workshop is no longer active. Your response was not saved. "
                "Refresh the page to join the active workshop."
            )
            clear_configuration_cache()
            return

        current_state = load_workshop_state(wid)
        if bool(current_state["submissions_locked"]):
            st.error("Submissions were just locked by the facilitator. Your response was not saved.")
            return

        submission_id = f"{wid}-{breakout_code}-{uuid.uuid4().hex[:8].upper()}"
        row = {
            "submission_id": submission_id,
            "submitted_at": now_iso(),
            "workshop_id": wid,
            "participant_name": participant_name.strip(),
            "company": company.strip(),
            "function_name": function_name,
            "sector": sector.strip(),
            "cdr_maturity": cdr_maturity,
            "breakout_code": breakout_code,
            "internal_leadership": internal_values["Leadership buy-in"],
            "internal_governance": internal_values["Governance & decision-making"],
            "internal_budget": internal_values["Budget allocation"],
            "internal_capability": internal_values["Internal capability"],
            "internal_procurement": internal_values["Procurement complexity"],
            "external_cost": external_values["Cost"],
            "external_standards": external_values["Standards & accounting"],
            "external_technology": external_values["Technology maturity"],
            "external_quality": external_values["Credit quality & integrity"],
            "external_demand": external_values["Customer demand"],
            "external_reputation": external_values["Reputation / greenwashing risk"],
            "external_other": external_values["Other"],
            "biggest_reason": biggest_reason.strip(),
        }

        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO participant_submissions (
                    submission_id, submitted_at, workshop_id, participant_name, company, function_name, sector,
                    cdr_maturity, breakout_code, internal_leadership, internal_governance, internal_budget,
                    internal_capability, internal_procurement, external_cost, external_standards, external_technology,
                    external_quality, external_demand, external_reputation, external_other, biggest_reason
                ) VALUES (
                    :submission_id, :submitted_at, :workshop_id, :participant_name, :company, :function_name, :sector,
                    :cdr_maturity, :breakout_code, :internal_leadership, :internal_governance, :internal_budget,
                    :internal_capability, :internal_procurement, :external_cost, :external_standards, :external_technology,
                    :external_quality, :external_demand, :external_reputation, :external_other, :biggest_reason
                )
            """), row)

        st.session_state[f"submitted_{wid}"] = True
        st.session_state[f"submitted_breakout_{wid}"] = breakout_code
        st.rerun(scope="app")


def participant_view():
    st.markdown('<div class="section-label">01 · Individual perspective</div>', unsafe_allow_html=True)
    st.subheader("Where would you allocate scarce attention and resources?")

    # Participants can only enter the facilitator-designated active workshop.
    active = active_workshop_direct()
    if not active:
        st.warning("There is currently no active workshop. Please wait for the facilitator.")
        return

    wid = active["workshop_id"]
    workshop_display = active["workshop_name"]
    if active.get("event_name"):
        workshop_display += f" · {active['event_name']}"

    # Visibly fixed/greyed-out field: participants cannot choose another workshop.
    st.text_input(
        "Active workshop",
        value=workshop_display,
        disabled=True,
        key=f"participant_active_workshop_{wid}",
    )
    st.caption("The facilitator controls the active workshop. Participant submissions can only be written to this workshop.")

    preset_breakout = st.query_params.get("group", "").upper()
    breakouts = load_breakouts_cached(wid)
    if breakouts.empty:
        st.warning("The active workshop has no breakout groups configured.")
        return

    breakout_codes = breakouts["breakout_code"].tolist()
    default_breakout_index = (
        breakout_codes.index(preset_breakout)
        if preset_breakout in breakout_codes
        else 0
    )

    submitted_key = f"submitted_{wid}"
    if st.session_state.get(submitted_key):
        st.success("Your allocation has been submitted.")
        st.info(
            "You can now open the public Results view from the sidebar. "
            "Results are published when the facilitator refreshes the workshop snapshot."
        )
        return

    # Read lock state once on entry; submit re-checks it directly before writing.
    participant_state_key = f"participant_initial_state_{wid}"
    if participant_state_key not in st.session_state:
        st.session_state[participant_state_key] = load_workshop_state(wid)
    state = st.session_state[participant_state_key]

    if bool(state["submissions_locked"]):
        st.markdown(
            '<div class="locked-box"><b>Submissions are currently locked.</b> '
            'The facilitator has closed the individual allocation stage.</div>',
            unsafe_allow_html=True,
        )
        return

    participant_input_fragment(wid, breakouts, default_breakout_index)


# -----------------------------------------------------------------------------
# Breakout lead
# -----------------------------------------------------------------------------
def breakout_lead_view():
    st.markdown('<div class="section-label">02 · Breakout decision</div>', unsafe_allow_html=True)
    st.subheader("Turn independent views into one coordinated recommendation")
    if not check_breakout_pin():
        return
    wid = select_workshop("Workshop", key="lead_workshop")
    if not wid:
        st.warning("No workshop configured.")
        return
    breakouts = load_breakouts(wid)
    if breakouts.empty:
        return
    preset_breakout = st.query_params.get("group", "").upper()
    codes = breakouts["breakout_code"].tolist()
    idx = codes.index(preset_breakout) if preset_breakout in codes else 0
    breakout_code = st.selectbox("Breakout", codes, index=idx)
    participants = load_participants(wid)
    group = participants[participants["breakout_code"] == breakout_code]

    st.metric("Individual submissions", len(group))
    if group.empty:
        st.info("No individual responses have been submitted for this breakout yet.")
        return

    st.markdown("### Starting point: low · average · high")
    st.caption("The line shows the full participant range. The dot is the breakout average. Large ranges are discussion prompts, not noise to hide.")
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(range_plot(group, INTERNAL_DB, "Internal barriers", COLORS["orange"]), use_container_width=True)
    with c2:
        st.plotly_chart(range_plot(group, EXTERNAL_DB, "External enabling environment", COLORS["spruce"]), use_container_width=True)

    with st.expander("Show the underlying low / average / high table"):
        st.dataframe(summary_table(group, INTERNAL_DB), hide_index=True, use_container_width=True)
        st.dataframe(summary_table(group, EXTERNAL_DB), hide_index=True, use_container_width=True)

    st.markdown("### Agree one coordinated allocation")
    st.caption(
        "Each allocation starts from the rounded average of this breakout's individual responses. "
        "This is only a starting point: the group should discuss and adjust the values, and both sections "
        "must total exactly 100 before submission."
    )

    internal_defaults = {
        barrier: int(round(float(group[col].mean())))
        for barrier, col in INTERNAL_DB.items()
    }
    external_defaults = {
        barrier: int(round(float(group[col].mean())))
        for barrier, col in EXTERNAL_DB.items()
    }

    st.markdown("#### Internal consensus · 100 units")
    internal_values, internal_total = allocation_editor(
        f"c_int_{wid}_{breakout_code}",
        INTERNAL,
        defaults=internal_defaults,
    )

    st.markdown("---")
    st.markdown("#### External enabling environment consensus · 100 units")
    external_values, external_total = allocation_editor(
        f"c_ext_{wid}_{breakout_code}",
        EXTERNAL,
        defaults=external_defaults,
    )

    st.markdown("---")
    rationale = st.text_area(
        "Why did the group make this allocation?",
        max_chars=900,
        key=f"rationale_{wid}_{breakout_code}",
    )
    intervention = st.text_area(
        "What one intervention would most help companies progress?",
        max_chars=450,
        key=f"intervention_{wid}_{breakout_code}",
    )

    consensus_ready = internal_total == 100 and external_total == 100
    if not consensus_ready:
        st.caption("Both consensus allocations must total exactly 100 before saving.")
    if st.button("Save breakout consensus", type="primary", disabled=not consensus_ready, use_container_width=True):
        row = {
            "workshop_id": wid, "breakout_code": breakout_code, "submitted_at": now_iso(),
            "internal_leadership": internal_values["Leadership buy-in"],
            "internal_governance": internal_values["Governance & decision-making"],
            "internal_budget": internal_values["Budget allocation"],
            "internal_capability": internal_values["Internal capability"],
            "internal_procurement": internal_values["Procurement complexity"],
            "external_cost": external_values["Cost"], "external_standards": external_values["Standards & accounting"],
            "external_technology": external_values["Technology maturity"],
            "external_quality": external_values["Credit quality & integrity"],
            "external_demand": external_values["Customer demand"],
            "external_reputation": external_values["Reputation / greenwashing risk"],
            "external_other": external_values["Other"], "rationale": rationale.strip(),
            "wbcsd_intervention": intervention.strip(),
        }
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM breakout_consensus WHERE workshop_id=:wid AND breakout_code=:code"), {"wid": wid, "code": breakout_code})
            conn.execute(text("""
                INSERT INTO breakout_consensus (
                    workshop_id, breakout_code, submitted_at, internal_leadership, internal_governance,
                    internal_budget, internal_capability, internal_procurement, external_cost, external_standards,
                    external_technology, external_quality, external_demand, external_reputation, external_other,
                    rationale, wbcsd_intervention
                ) VALUES (
                    :workshop_id, :breakout_code, :submitted_at, :internal_leadership, :internal_governance,
                    :internal_budget, :internal_capability, :internal_procurement, :external_cost, :external_standards,
                    :external_technology, :external_quality, :external_demand, :external_reputation, :external_other,
                    :rationale, :wbcsd_intervention
                )
            """), row)
        st.success(f"Consensus saved for {breakout_code}.")

# -----------------------------------------------------------------------------
# Facilitator dashboard
# -----------------------------------------------------------------------------

def render_breakout_comparison(participants, consensus, breakouts, wid, key_prefix):
    """Shared comparison view used by Facilitator and public Results."""
    if participants.empty:
        st.info("No participant submissions have been published yet.")
        return

    st.markdown("### Every breakout · participant range vs coordinated decision")
    st.caption(
        "For each breakout, the range is the lowest-to-highest participant response, "
        "the coloured dot is the participant average, and the charcoal diamond is the final breakout allocation."
    )
    for code in breakouts["breakout_code"].tolist():
        g = participants[participants["breakout_code"] == code]
        if g.empty:
            continue
        cdf = consensus[consensus["breakout_code"] == code]
        crow = cdf.iloc[0].to_dict() if not cdf.empty else None
        with st.expander(f"{code} · {len(g)} participant responses", expanded=False):
            lcol, rcol = st.columns(2)
            with lcol:
                st.plotly_chart(
                    range_plot_with_consensus(
                        g, INTERNAL_DB, "Internal barriers", COLORS["orange"], crow
                    ),
                    use_container_width=True,
                    key=f"{key_prefix}_range_int_{wid}_{code}",
                )
            with rcol:
                st.plotly_chart(
                    range_plot_with_consensus(
                        g, EXTERNAL_DB, "External enabling environment", COLORS["spruce"], crow
                    ),
                    use_container_width=True,
                    key=f"{key_prefix}_range_ext_{wid}_{code}",
                )

    st.markdown("### Final coordinated allocation · breakout comparison")
    if consensus.empty:
        st.info("No breakout coordinated allocations have been submitted yet.")
    else:
        lcol, rcol = st.columns(2)
        with lcol:
            fig = consensus_comparison_chart(
                consensus, INTERNAL_DB, "Internal budget allocation by breakout"
            )
            if fig is not None:
                st.plotly_chart(
                    fig, use_container_width=True,
                    key=f"{key_prefix}_consensus_int_{wid}",
                )
        with rcol:
            fig = consensus_comparison_chart(
                consensus, EXTERNAL_DB, "External enabling priorities by breakout"
            )
            if fig is not None:
                st.plotly_chart(
                    fig, use_container_width=True,
                    key=f"{key_prefix}_consensus_ext_{wid}",
                )

    st.markdown("### Priority heat maps")
    hi, he = st.tabs(["Internal", "External"])
    with hi:
        fig = breakout_heatmap(
            participants, INTERNAL_DB, "mean",
            "Average internal allocation by breakout"
        )
        if fig:
            st.plotly_chart(
                fig, use_container_width=True,
                key=f"{key_prefix}_priority_int_{wid}",
            )
    with he:
        fig = breakout_heatmap(
            participants, EXTERNAL_DB, "mean",
            "Average external allocation by breakout"
        )
        if fig:
            st.plotly_chart(
                fig, use_container_width=True,
                key=f"{key_prefix}_priority_ext_{wid}",
            )

    st.markdown("### Agreement heat maps")
    ai, ae = st.tabs(["Internal", "External"])
    with ai:
        fig = breakout_heatmap(
            participants, INTERNAL_DB, "std",
            "Internal disagreement by breakout · higher = more divergent"
        )
        if fig:
            st.plotly_chart(
                fig, use_container_width=True,
                key=f"{key_prefix}_agreement_int_{wid}",
            )
    with ae:
        fig = breakout_heatmap(
            participants, EXTERNAL_DB, "std",
            "External disagreement by breakout · higher = more divergent"
        )
        if fig:
            st.plotly_chart(
                fig, use_container_width=True,
                key=f"{key_prefix}_agreement_ext_{wid}",
            )

    st.markdown("### Compare one barrier across breakouts")
    category = st.radio(
        "Barrier type",
        ["Internal", "External"],
        horizontal=True,
        key=f"{key_prefix}_barrier_type_{wid}",
    )
    mapping = INTERNAL_DB if category == "Internal" else EXTERNAL_DB
    barrier = st.selectbox(
        "Barrier",
        list(mapping.keys()),
        key=f"{key_prefix}_barrier_{wid}",
    )
    col = mapping[barrier]

    rows = []
    for code, g in participants.groupby("breakout_code"):
        rows.append({
            "Breakout": code,
            "Low": g[col].min(),
            "Average": g[col].mean(),
            "High": g[col].max(),
            "Std dev": g[col].std(ddof=0),
        })
    comp = pd.DataFrame(rows).sort_values("Average", ascending=True)

    fig = go.Figure()
    for _, r in comp.iterrows():
        fig.add_trace(go.Scatter(
            x=[r["Low"], r["High"]],
            y=[r["Breakout"], r["Breakout"]],
            mode="lines",
            line=dict(color=COLORS["sand"], width=9),
            showlegend=False,
            hoverinfo="skip",
        ))
    fig.add_trace(go.Scatter(
        x=comp["Average"],
        y=comp["Breakout"],
        mode="markers",
        marker=dict(size=13, color=COLORS["orange"]),
        showlegend=False,
        customdata=np.stack([comp["Low"], comp["High"], comp["Std dev"]], axis=-1),
        hovertemplate=(
            "%{y}<br>Average %{x:.1f}<br>Low %{customdata[0]:.1f}"
            "<br>High %{customdata[1]:.1f}<br>Std dev %{customdata[2]:.1f}<extra></extra>"
        ),
    ))
    fig.update_layout(
        title=barrier,
        xaxis=dict(range=[0,100], title="Allocation units"),
        yaxis_title=None,
        height=max(300, 65*len(comp)),
        plot_bgcolor="white",
    )
    st.plotly_chart(
        fig, use_container_width=True,
        key=f"{key_prefix}_barrier_plot_{wid}",
    )


def get_facilitator_snapshot(wid, force=False):
    """
    Keep a local session snapshot of workshop results.
    Database reads happen once on entry and only again when the facilitator
    explicitly presses Refresh results.
    """
    key = f"fac_snapshot_{wid}"
    if force or key not in st.session_state:
        participants = load_participants(wid)
        consensus = load_consensus(wid)
        workshops = load_workshops_cached()
        breakouts = load_breakouts_cached(wid)
        wdf = workshops[workshops["workshop_id"] == wid]
        wrow = wdf.iloc[0].to_dict() if not wdf.empty else {}
        status_df = build_submission_status(
            breakouts,
            participants,
            consensus,
            int(wrow.get("participant_target") or 0),
        )
        st.session_state[key] = {
            "participants": participants,
            "consensus": consensus,
            "breakouts": breakouts,
            "wrow": wrow,
            "status_df": status_df,
            "refreshed_at": datetime.now().strftime("%H:%M:%S"),
        }
    return st.session_state[key]


def build_submission_status(breakouts, participants, consensus, participant_target):
    breakout_count = max(len(breakouts), 1)
    expected_per_breakout = (
        int(round(participant_target / breakout_count))
        if participant_target else None
    )

    rows = []
    for _, br in breakouts.iterrows():
        code = br["breakout_code"]
        submitted = (
            int((participants["breakout_code"] == code).sum())
            if not participants.empty else 0
        )
        consensus_done = (
            bool((consensus["breakout_code"] == code).any())
            if not consensus.empty else False
        )
        rows.append({
            "Breakout": code,
            "Name": br.get("breakout_name") or "",
            "Expected": (
                expected_per_breakout
                if expected_per_breakout is not None else ""
            ),
            "Submitted": submitted,
            "Consensus": "Complete" if consensus_done else "Pending",
            "Ready": (
                "Yes"
                if consensus_done and (
                    expected_per_breakout is None
                    or submitted >= expected_per_breakout
                )
                else "No"
            ),
        })
    return pd.DataFrame(rows)


def get_facilitator_state(wid):
    key = f"fac_state_{wid}"
    if key not in st.session_state:
        st.session_state[key] = load_workshop_state(wid)
    return st.session_state[key]


def live_controls(wid):
    state = get_facilitator_state(wid)
    st.markdown("### Submission controls")
    c1, c2 = st.columns([1.4, 3.6])

    with c1:
        if bool(state["submissions_locked"]):
            if st.button("Reopen submissions", use_container_width=True):
                update_workshop_state(wid, locked=0)
                state["submissions_locked"] = 0
                st.session_state[f"fac_state_{wid}"] = state
                st.rerun()
        else:
            if st.button("Lock submissions", type="primary", use_container_width=True):
                update_workshop_state(wid, locked=1)
                state["submissions_locked"] = 1
                st.session_state[f"fac_state_{wid}"] = state
                st.rerun()

    with c2:
        status = "Submissions locked" if state["submissions_locked"] else "Submissions open"
        st.markdown(
            f'<div class="callout"><b>Status:</b> {status}. '
            'Results are always available through the public Results view and update when you press Refresh results.</div>',
            unsafe_allow_html=True,
        )
    return state


def facilitator_view():
    st.markdown('<div class="section-label">03 · Facilitator</div>', unsafe_allow_html=True)
    st.subheader("See the room, surface disagreement, and guide the discussion")
    if not check_facilitator_pin():
        return
    wid = select_workshop("Workshop", key="fac_workshop")
    if not wid:
        return

    active_now = active_workshop_direct()
    if active_now and active_now["workshop_id"] == wid:
        st.success(f"Active workshop · {active_now['workshop_name']}")
    elif active_now:
        st.info(
            f"You are viewing an inactive workshop. Public Participant and Results pages currently use "
            f"**{active_now['workshop_name']}**."
        )
    else:
        st.warning("No workshop is active. Participant submissions and public Results are currently unavailable.")

    live_controls(wid)

    refresh_col, info_col = st.columns([1.2, 3.8])
    with refresh_col:
        refresh_clicked = st.button(
            "Refresh results",
            type="primary",
            use_container_width=True,
            help="Fetch the latest participant submissions and breakout decisions from the database.",
        )

    snapshot = get_facilitator_snapshot(wid, force=refresh_clicked)
    active_now = active_workshop_direct()
    is_active_view = bool(active_now and active_now["workshop_id"] == wid)

    if refresh_clicked and is_active_view:
        # Only the active workshop can publish to the public Results view.
        touch_results_snapshot(wid)
    elif refresh_clicked and not is_active_view:
        st.warning(
            "This workshop snapshot was refreshed for the facilitator, but it was not "
            "published to the public Results page because it is not the active workshop."
        )
    participants = snapshot["participants"]
    consensus = snapshot["consensus"]
    breakouts = snapshot["breakouts"]
    wrow = snapshot["wrow"]
    status_df = snapshot["status_df"]

    with info_col:
        st.markdown(
            f'<div class="callout"><b>Results snapshot:</b> refreshed at '
            f'{snapshot["refreshed_at"]} · {database_backend_label()}</div>',
            unsafe_allow_html=True,
        )

    st.markdown("### Submission status")
    if not status_df.empty:
        st.dataframe(status_df, hide_index=True, use_container_width=True)
    if participants.empty:
        st.warning("No participant submissions yet.")
        return

    target = int(wrow.get("participant_target") or 0)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Submissions", len(participants))
    m2.metric("Companies", participants["company"].nunique())
    m3.metric("Breakouts active", participants["breakout_code"].nunique())
    m4.metric("Completion", f"{len(participants)}/{target}" if target else str(len(participants)))

    overview, comparisons, qualitative, reporting = st.tabs([
        "Live overview", "Breakout comparison", "Qualitative intelligence", "Report & export"
    ])

    with overview:
        breakout_options = ["All"] + sorted(participants["breakout_code"].dropna().unique().tolist())
        selected = st.selectbox("View", breakout_options, key="overview_breakout")
        data = participants if selected == "All" else participants[participants["breakout_code"] == selected]
        selected_consensus_row = None
        if selected != "All":
            selected_consensus = consensus[consensus["breakout_code"] == selected]
            if not selected_consensus.empty:
                selected_consensus_row = selected_consensus.iloc[0].to_dict()

        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(
                range_plot_with_consensus(
                    data, INTERNAL_DB,
                    "Internal · low / average / high + breakout decision",
                    COLORS["orange"], selected_consensus_row,
                ),
                use_container_width=True,
            )
        with c2:
            st.plotly_chart(
                range_plot_with_consensus(
                    data, EXTERNAL_DB,
                    "External · low / average / high + breakout decision",
                    COLORS["spruce"], selected_consensus_row,
                ),
                use_container_width=True,
            )
        st.markdown("### Agreement / disagreement")
        combined = pd.concat([
            summary_table(data, INTERNAL_DB).assign(Type="Internal"),
            summary_table(data, EXTERNAL_DB).assign(Type="External"),
        ], ignore_index=True).sort_values("Std dev", ascending=False)
        st.dataframe(combined[["Type", "Barrier", "Low", "Average", "High", "Std dev", "Agreement"]], hide_index=True, use_container_width=True)

    with comparisons:
        render_breakout_comparison(
            participants, consensus, breakouts, wid, key_prefix="fac"
        )

    with qualitative:
        texts = participants["biggest_reason"].fillna("")
        texts = [t for t in texts if str(t).strip()]
        if not texts:
            st.info("No qualitative responses yet.")
        else:
            c1, c2 = st.columns([1.2, 1])
            with c1:
                st.markdown("### Word cloud")
                wc = make_wordcloud(texts)
                if wc is not None:
                    st.image(wc, use_container_width=True)
                st.caption("Word cloud is descriptive only; frequent words are not automatically the most important themes.")
            with c2:
                st.markdown("### AI-assisted theme clustering")
                clustered, theme_summary = cluster_qualitative(texts)
                if theme_summary is None:
                    st.info("At least four substantive responses are needed for clustering.")
                else:
                    st.dataframe(theme_summary[["Theme", "Responses"]], hide_index=True, use_container_width=True)
                    st.caption("Clusters are generated locally with TF-IDF + k-means; participant text is not sent to an external AI service.")
            if 'clustered' in locals() and clustered is not None:
                with st.expander("Review clustered responses"):
                    st.dataframe(clustered[["Theme", "Response"]].sort_values("Theme"), hide_index=True, use_container_width=True)

    with reporting:
        st.markdown("### WBCSD-branded workshop report")
        texts = [t for t in participants["biggest_reason"].fillna("") if str(t).strip()]
        _, theme_summary = cluster_qualitative(texts) if texts else (None, None)
        pdf_bytes = build_pdf_report(wrow, participants, consensus, breakouts, theme_summary)
        st.download_button(
            "Download PDF report", data=pdf_bytes,
            file_name=f"{re.sub(r'[^A-Za-z0-9_-]+', '_', wrow['workshop_name']).strip('_')}_CDR_Decision_Lab.pdf",
            mime="application/pdf", type="primary", use_container_width=True,
        )
        excel_buf = io.BytesIO()
        with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
            participants.to_excel(writer, sheet_name="Participants", index=False)
            consensus.to_excel(writer, sheet_name="Breakout Consensus", index=False)
            breakouts.to_excel(writer, sheet_name="Breakouts", index=False)
        st.download_button(
            "Download raw workshop data (Excel)", data=excel_buf.getvalue(),
            file_name="WBCSD_CDR_Decision_Lab_Data.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True,
        )


@st.fragment
def public_results_fragment():
    """
    Public results follows the facilitator-designated active workshop without
    automatic polling. The displayed snapshot changes only after the facilitator
    presses Refresh results and the Results view is subsequently loaded/rerun.
    """
    active = active_workshop_direct()
    if not active:
        st.warning("There is currently no active workshop.")
        return

    wid = active["workshop_id"]
    workshop_display = active["workshop_name"]
    if active.get("event_name"):
        workshop_display += f" · {active['event_name']}"

    st.text_input(
        "Active workshop",
        value=workshop_display,
        disabled=True,
        key=f"results_active_workshop_{wid}",
    )

    state = load_workshop_state(wid)
    token = state.get("updated_at")
    active_key = "public_results_current_active"
    token_key = f"public_results_token_{wid}"
    snapshot_key = f"public_results_snapshot_{wid}"

    active_changed = st.session_state.get(active_key) != wid
    token_changed = st.session_state.get(token_key) != token

    if active_changed or token_changed or snapshot_key not in st.session_state:
        st.session_state[active_key] = wid
        st.session_state[token_key] = token
        st.session_state[snapshot_key] = {
            "participants": load_participants(wid),
            "consensus": load_consensus(wid),
            "breakouts": load_breakouts_cached(wid),
            "published_at": token,
        }

    snapshot = st.session_state[snapshot_key]
    st.caption(
        "This view shows the latest results published by the facilitator. "
        f"Published results snapshot: {snapshot.get('published_at') or 'Not yet refreshed'}"
    )

    render_breakout_comparison(
        snapshot["participants"],
        snapshot["consensus"],
        snapshot["breakouts"],
        wid,
        key_prefix="public",
    )


def results_view():
    st.markdown('<div class="section-label">Results</div>', unsafe_allow_html=True)
    st.subheader("Workshop results")
    public_results_fragment()



# -----------------------------------------------------------------------------
# Workshop configuration / admin
# -----------------------------------------------------------------------------
def workshop_configuration_view():
    st.markdown('<div class="section-label">Admin · workshop configuration</div>', unsafe_allow_html=True)
    st.subheader("Configure and control the active workshop")
    if not check_facilitator_pin(key="config_facilitator_pin"):
        return

    if database_health():
        st.success(f"Database connected: {database_backend_label()}")
    else:
        st.error(f"Database connection problem: {database_backend_label()}")

    # ------------------------------------------------------------------
    # ACTIVE WORKSHOP CONTROL
    # ------------------------------------------------------------------
    st.markdown("### Active workshop")
    st.caption(
        "There is one source of truth. The active workshop is automatically used by "
        "Participant submissions and the public Results page."
    )

    workshops = load_workshops()
    if workshops.empty:
        st.info("No workshops exist yet. Create one below.")
        active = None
    else:
        active_rows = workshops[workshops["is_active"] == 1]
        active = None if active_rows.empty else active_rows.iloc[0].to_dict()

        options = ["__NONE__"] + workshops["workshop_id"].tolist()
        labels = {"__NONE__": "No active workshop"}
        for _, r in workshops.iterrows():
            suffix = " · ACTIVE" if bool(r["is_active"]) else ""
            labels[r["workshop_id"]] = (
                f'{r["workshop_name"]} · {r["event_name"] or "Workshop"}{suffix}'
            )

        current = active["workshop_id"] if active else "__NONE__"
        selected_active = st.selectbox(
            "Workshop used by participants and public Results",
            options,
            index=options.index(current),
            format_func=lambda x: labels[x],
            key="active_workshop_control",
        )

        c1, c2 = st.columns([1.3, 3.7])
        with c1:
            if st.button(
                "Apply active workshop",
                type="primary",
                use_container_width=True,
                key="apply_active_workshop",
            ):
                set_active_workshop(
                    None if selected_active == "__NONE__" else selected_active
                )
                # Clear public session snapshot so this browser follows immediately.
                st.session_state.pop("public_results_current_active", None)
                st.success("Active workshop updated.")
                st.rerun()
        with c2:
            if active:
                st.markdown(
                    f'<div class="callout"><b>Currently active:</b> {active["workshop_name"]}. '
                    'This is the workshop participants can submit to and the Results page displays.</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<div class="callout"><b>No workshop is active.</b> Participant submission and public Results are disabled.</div>',
                    unsafe_allow_html=True,
                )

    st.markdown("---")

    # ------------------------------------------------------------------
    # CREATE WORKSHOP
    # ------------------------------------------------------------------
    with st.expander("Create a new workshop", expanded=workshops.empty):
        st.caption(
            "A new workshop is created inactive. Set it as Active above when you are ready "
            "for participants to use it."
        )
        with st.form("create_workshop_form"):
            c1, c2 = st.columns(2)
            with c1:
                workshop_name = st.text_input(
                    "Workshop name",
                    placeholder="CDR Barrier Auction",
                )
                event_name = st.text_input(
                    "Event / programme",
                    placeholder="New York Climate Week 2026",
                )
                event_date = st.date_input("Event date")
            with c2:
                participant_target = st.number_input(
                    "Expected participants", 1, 1000, 40
                )
                duration_minutes = st.number_input(
                    "Workshop duration (minutes)", 10, 240, 45
                )
                number_breakouts = st.number_input(
                    "Number of breakout groups", 1, 30, 5
                )
            code_style = st.selectbox(
                "Default breakout codes",
                ["B1, B2, B3…", "BLUE1, BLUE2, BLUE3…"],
            )
            create = st.form_submit_button(
                "Create workshop",
                type="primary",
                use_container_width=True,
            )

        if create:
            if not workshop_name.strip():
                st.error("Workshop name is required.")
            else:
                wid_new = f"WS-{uuid.uuid4().hex[:8].upper()}"
                codes = [
                    f"BLUE{i}" if code_style.startswith("BLUE") else f"B{i}"
                    for i in range(1, int(number_breakouts) + 1)
                ]
                try:
                    with engine.begin() as conn:
                        conn.execute(text("""
                            INSERT INTO workshops (
                                workshop_id, workshop_name, event_name, event_date,
                                participant_target, duration_minutes, is_active, created_at
                            )
                            VALUES (
                                :wid,:name,:event,:date,:target,:duration,0,:created
                            )
                        """), {
                            "wid": wid_new,
                            "name": workshop_name.strip(),
                            "event": event_name.strip(),
                            "date": str(event_date),
                            "target": int(participant_target),
                            "duration": int(duration_minutes),
                            "created": now_iso(),
                        })
                        conn.execute(text("""
                            INSERT INTO workshop_state (
                                workshop_id, submissions_locked, results_revealed, updated_at
                            )
                            VALUES (:wid,0,0,:updated)
                        """), {"wid": wid_new, "updated": now_iso()})
                        for i, code in enumerate(codes, 1):
                            conn.execute(text("""
                                INSERT INTO workshop_breakouts (
                                    workshop_id, breakout_code, breakout_name
                                )
                                VALUES (:wid,:code,:name)
                            """), {
                                "wid": wid_new,
                                "code": code,
                                "name": f"Breakout {i}",
                            })
                    clear_configuration_cache()
                    st.success(
                        "Workshop created as inactive. Select it under Active workshop when ready."
                    )
                    st.rerun()
                except Exception as exc:
                    st.error("The workshop could not be created.")
                    st.exception(exc)

    # Reload after any create path.
    workshops = load_workshops()
    if workshops.empty:
        return

    st.markdown("---")

    # ------------------------------------------------------------------
    # MANAGE ONE WORKSHOP
    # ------------------------------------------------------------------
    st.markdown("### Manage workshop")
    st.caption(
        "Selecting a workshop here does not make it active. Use the Active workshop control above "
        "to determine what participants and the public Results page use."
    )

    options = workshops["workshop_id"].tolist()
    active_rows = workshops[workshops["is_active"] == 1]
    default_manage = (
        active_rows.iloc[0]["workshop_id"]
        if not active_rows.empty
        else options[0]
    )

    wid = st.selectbox(
        "Workshop to manage",
        options,
        index=options.index(default_manage),
        format_func=lambda x: (
            workshops.loc[workshops["workshop_id"] == x, "workshop_name"].iloc[0]
            + (
                " · ACTIVE"
                if bool(
                    workshops.loc[
                        workshops["workshop_id"] == x, "is_active"
                    ].iloc[0]
                )
                else ""
            )
        ),
        key="config_workshop",
    )

    row = workshops[workshops["workshop_id"] == wid].iloc[0]
    c1, c2, c3 = st.columns(3)
    c1.metric("Expected participants", int(row["participant_target"] or 0))
    c2.metric("Duration", f"{int(row['duration_minutes'] or 0)} min")
    c3.metric("Status", "ACTIVE" if bool(row["is_active"]) else "Inactive")

    st.markdown("### Breakout groups")
    breakouts = load_breakouts(wid)
    edited = st.data_editor(
        breakouts[["breakout_code", "breakout_name"]].copy(),
        hide_index=True,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "breakout_code": st.column_config.TextColumn("Code", required=True),
            "breakout_name": st.column_config.TextColumn("Name"),
        },
        key=f"breakout_editor_{wid}",
    )

    if st.button(
        "Save breakout groups",
        type="primary",
        use_container_width=True,
        key=f"save_breakouts_{wid}",
    ):
        clean = edited.copy()
        clean["breakout_code"] = (
            clean["breakout_code"].astype(str).str.strip().str.upper()
        )
        clean["breakout_name"] = (
            clean["breakout_name"].fillna("").astype(str).str.strip()
        )
        clean = clean[clean["breakout_code"] != ""]

        if clean["breakout_code"].duplicated().any():
            st.error("Breakout codes must be unique.")
        else:
            with engine.begin() as conn:
                conn.execute(
                    text("DELETE FROM workshop_breakouts WHERE workshop_id=:wid"),
                    {"wid": wid},
                )
                for _, br in clean.iterrows():
                    conn.execute(text("""
                        INSERT INTO workshop_breakouts (
                            workshop_id, breakout_code, breakout_name
                        )
                        VALUES (:wid,:code,:name)
                    """), {
                        "wid": wid,
                        "code": br["breakout_code"],
                        "name": br["breakout_name"],
                    })
            clear_configuration_cache()
            st.success("Breakout groups saved.")
            st.rerun()

    st.markdown("### Submission status")
    status_df = workshop_submission_status(wid)
    if status_df.empty:
        st.info("No breakout groups configured.")
    else:
        st.dataframe(status_df, hide_index=True, use_container_width=True)

    # ------------------------------------------------------------------
    # RESET RESPONSES
    # ------------------------------------------------------------------
    st.markdown("---")
    st.markdown("### Reset workshop responses")
    st.warning(
        "This clears participant submissions, breakout decisions and qualitative responses, "
        "but keeps the workshop configuration and breakout groups."
    )
    reset_key = f"reset_confirm_{wid}"
    if st.session_state.pop(f"clear_reset_confirm_next_{wid}", False):
        st.session_state[reset_key] = ""

    reset_confirmation = st.text_input(
        "Type RESET to clear responses",
        key=reset_key,
        placeholder="RESET",
    )
    if st.button(
        "Clear responses only",
        disabled=reset_confirmation.strip().upper() != "RESET",
        use_container_width=True,
        key=f"reset_button_{wid}",
    ):
        reset_workshop_responses(wid)
        st.session_state.pop(f"fac_snapshot_{wid}", None)
        st.session_state.pop(f"fac_state_{wid}", None)
        st.session_state.pop(f"public_results_snapshot_{wid}", None)
        st.session_state.pop(f"public_results_token_{wid}", None)
        st.session_state[f"clear_reset_confirm_next_{wid}"] = True
        st.success("Responses cleared; workshop configuration retained.")
        st.rerun()

    # ------------------------------------------------------------------
    # DELETE ENTIRE WORKSHOP
    # ------------------------------------------------------------------
    st.markdown("---")
    st.markdown("### Delete entire workshop")
    st.error(
        "This permanently removes the workshop configuration, breakout groups, participant "
        "submissions, breakout decisions and results. This cannot be undone."
    )
    delete_key = f"delete_confirm_{wid}"
    if st.session_state.pop(f"clear_delete_confirm_next_{wid}", False):
        st.session_state[delete_key] = ""

    delete_confirmation = st.text_input(
        "Type DELETE to permanently remove this workshop",
        key=delete_key,
        placeholder="DELETE",
    )
    if st.button(
        "Delete entire workshop",
        disabled=delete_confirmation.strip().upper() != "DELETE",
        use_container_width=True,
        key=f"delete_workshop_{wid}",
    ):
        was_active = bool(row["is_active"])
        st.session_state[f"clear_delete_confirm_next_{wid}"] = True
        delete_workshop(wid)
        if was_active:
            # Deliberately leave no active workshop rather than silently choosing another.
            set_active_workshop(None)
        st.success(
            "Workshop permanently deleted. "
            + ("No workshop is active; choose one explicitly above." if was_active else "")
        )
        st.rerun()

    st.markdown("### Links")
    base_url = st.text_input(
        "Deployed app URL",
        placeholder="https://your-app.streamlit.app",
    ).rstrip("/")
    if base_url:
        st.markdown("**Participant links**")
        for _, br in load_breakouts(wid).iterrows():
            st.code(
                f"{base_url}/?group={br['breakout_code']}",
                language=None,
            )
        st.caption(
            "Participant links no longer carry a workshop ID. They always resolve against "
            "the currently active workshop."
        )
        st.markdown("**Facilitator / Results link**")
        st.code(base_url, language=None)


# -----------------------------------------------------------------------------
# Navigation
# -----------------------------------------------------------------------------
header()
lead_mode = str(st.query_params.get("lead", "0")) == "1"

nav_options = ["Participant", "Breakout lead", "Results", "Facilitator", "Workshop configuration"]
default_idx = 1 if lead_mode else 0

mode = st.sidebar.radio("View", nav_options, index=default_idx)
st.sidebar.markdown("---")
st.sidebar.caption("WBCSD · CDR Decision Lab · Version 1.1.8")
st.sidebar.caption("Participant and Results are visible. Breakout lead and facilitator/admin areas use separate PINs.")

if mode == "Participant":
    participant_view()
elif mode == "Breakout lead":
    breakout_lead_view()
elif mode == "Results":
    results_view()
elif mode == "Facilitator":
    facilitator_view()
else:
    workshop_configuration_view()
