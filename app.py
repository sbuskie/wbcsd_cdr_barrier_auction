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
connect_args = {"check_same_thread": False, "timeout": 30} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def init_db():
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

        # Lightweight migration for pre-V1.0 databases.
        for table_name, column_name, column_type in [
            ("participant_submissions", "workshop_id", "TEXT"),
            ("breakout_consensus", "workshop_id", "TEXT"),
        ]:
            try:
                conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))
            except Exception:
                pass

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
# Allocation UI - exact 100 with automatic proportional rebalancing
# -----------------------------------------------------------------------------
def alloc_key(prefix, idx):
    return f"{prefix}__{idx}"


def init_allocation(prefix, labels):
    if all(alloc_key(prefix, i) in st.session_state for i in range(len(labels))):
        return
    base = 100 // len(labels)
    rem = 100 - base * len(labels)
    for i in range(len(labels)):
        st.session_state[alloc_key(prefix, i)] = base + (1 if i < rem else 0)


def proportional_distribution(weights, total):
    if not weights:
        return []
    if total <= 0:
        return [0] * len(weights)
    positive_sum = sum(max(0, w) for w in weights)
    if positive_sum == 0:
        raw = [total / len(weights)] * len(weights)
    else:
        raw = [total * max(0, w) / positive_sum for w in weights]
    floor_vals = [int(math.floor(x)) for x in raw]
    remainder = total - sum(floor_vals)
    order = sorted(range(len(raw)), key=lambda i: raw[i] - floor_vals[i], reverse=True)
    for i in order[:remainder]:
        floor_vals[i] += 1
    return floor_vals


def rebalance_allocation(prefix, labels, changed_idx):
    changed_key = alloc_key(prefix, changed_idx)
    changed = int(max(0, min(100, st.session_state.get(changed_key, 0))))
    st.session_state[changed_key] = changed
    remaining = 100 - changed
    other_indices = [i for i in range(len(labels)) if i != changed_idx]
    weights = [int(st.session_state.get(alloc_key(prefix, i), 0)) for i in other_indices]
    distributed = proportional_distribution(weights, remaining)
    for i, value in zip(other_indices, distributed):
        st.session_state[alloc_key(prefix, i)] = int(value)


def nudge_allocation(prefix, labels, idx, delta):
    key = alloc_key(prefix, idx)
    st.session_state[key] = int(max(0, min(100, st.session_state.get(key, 0) + delta)))
    rebalance_allocation(prefix, labels, idx)


def allocation_editor(prefix, labels, help_text=None):
    init_allocation(prefix, labels)
    if help_text:
        st.caption(help_text)
    st.caption("Change any value and the remaining units are rebalanced proportionally. Use +/-5 for quick adjustments.")
    for i, label in enumerate(labels):
        c_label, c_minus, c_value, c_plus = st.columns([5.2, 0.8, 1.25, 0.8], vertical_alignment="center")
        value = int(st.session_state[alloc_key(prefix, i)])
        with c_label:
            st.markdown(
                f'<div class="allocation-row"><div class="allocation-label">{label}</div>'
                f'<div class="alloc-track"><div class="alloc-fill" style="width:{value}%"></div></div></div>',
                unsafe_allow_html=True,
            )
        with c_minus:
            st.button("−5", key=f"{prefix}_minus_{i}", on_click=nudge_allocation, args=(prefix, labels, i, -5), use_container_width=True)
        with c_value:
            st.number_input(
                label, min_value=0, max_value=100, step=1,
                key=alloc_key(prefix, i), label_visibility="collapsed",
                on_change=rebalance_allocation, args=(prefix, labels, i),
            )
        with c_plus:
            st.button("+5", key=f"{prefix}_plus_{i}", on_click=nudge_allocation, args=(prefix, labels, i, 5), use_container_width=True)
    values = {label: int(st.session_state[alloc_key(prefix, i)]) for i, label in enumerate(labels)}
    total = sum(values.values())
    st.markdown(f'<span class="total-pill">Total {total} / 100</span>', unsafe_allow_html=True)
    return values

# -----------------------------------------------------------------------------
# PDF generation
# -----------------------------------------------------------------------------
def pdf_hex(hex_color):
    return rl_colors.HexColor(hex_color)


def build_pdf_report(workshop_row, participants, consensus, breakouts, theme_summary=None):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, rightMargin=15*mm, leftMargin=15*mm, topMargin=17*mm, bottomMargin=17*mm,
        title=f"{workshop_row['workshop_name']} - CDR Barrier Auction",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="WTitle", parent=styles["Title"], fontName="Helvetica", fontSize=22, leading=25,
        textColor=pdf_hex(COLORS["charcoal"]), alignment=TA_LEFT, spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="WH2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=13,
        textColor=pdf_hex(COLORS["spruce"]), spaceBefore=9, spaceAfter=5,
    ))
    styles.add(ParagraphStyle(
        name="WBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=9.2, leading=12,
        textColor=pdf_hex(COLORS["charcoal"]),
    ))
    story = []
    logo_path = Path("assets/wbcsd_logo.jpg")
    if logo_path.exists():
        story.append(RLImage(str(logo_path), width=58*mm, height=19*mm))
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph(workshop_row["workshop_name"], styles["WTitle"]))
    story.append(Paragraph(
        f"{workshop_row.get('event_name') or ''} | {workshop_row.get('event_date') or ''} | "
        f"{len(participants)} participant submissions | {participants['breakout_code'].nunique() if not participants.empty else 0} breakouts",
        styles["WBody"],
    ))
    story.append(Spacer(1, 5*mm))

    def add_summary_section(title, mapping):
        story.append(Paragraph(title, styles["WH2"]))
        sm = summary_table(participants, mapping)
        data = [["Rank", "Barrier", "Low", "Average", "High", "Agreement"]] + [
            [int(r["Rank"]), r["Barrier"], r["Low"], r["Average"], r["High"], r["Agreement"]]
            for _, r in sm.iterrows()
        ]
        table = Table(data, colWidths=[11*mm, 66*mm, 18*mm, 21*mm, 18*mm, 24*mm], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), pdf_hex(COLORS["charcoal"])),
            ("TEXTCOLOR", (0,0), (-1,0), rl_colors.white),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTNAME", (0,1), (-1,-1), "Helvetica"),
            ("FONTSIZE", (0,0), (-1,-1), 8),
            ("GRID", (0,0), (-1,-1), .35, pdf_hex(COLORS["sand"])),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [rl_colors.white, pdf_hex(COLORS["pearl"])]),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("LEFTPADDING", (0,0), (-1,-1), 4), ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ]))
        story.append(table)

    if not participants.empty:
        add_summary_section("Internal investment priorities", INTERNAL_DB)
        add_summary_section("External enabling environment", EXTERNAL_DB)

    if theme_summary is not None and not theme_summary.empty:
        story.append(Paragraph("Qualitative themes", styles["WH2"]))
        data = [["Theme", "Responses"]] + [[r["Theme"], int(r["Responses"])] for _, r in theme_summary.iterrows()]
        table = Table(data, colWidths=[130*mm, 28*mm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), pdf_hex(COLORS["spruce"])), ("TEXTCOLOR", (0,0), (-1,0), rl_colors.white),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("FONTNAME", (0,1), (-1,-1), "Helvetica"),
            ("FONTSIZE", (0,0), (-1,-1), 8.5), ("GRID", (0,0), (-1,-1), .35, pdf_hex(COLORS["sand"])),
        ]))
        story.append(table)

    story.append(PageBreak())
    story.append(Paragraph("Breakout report-backs", styles["WTitle"]))
    for _, br in breakouts.iterrows():
        code = br["breakout_code"]
        group = participants[participants["breakout_code"] == code]
        c_row = consensus[consensus["breakout_code"] == code]
        story.append(Paragraph(f"{code} - {br.get('breakout_name') or ''}", styles["WH2"]))
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
        if not c_row.empty:
            summary_data.append(["Recommended WBCSD intervention", c_row.iloc[0]["wbcsd_intervention"] or "Not recorded"])
        t = Table(summary_data, colWidths=[48*mm, 110*mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (0,-1), pdf_hex(COLORS["pearl"])), ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
            ("FONTNAME", (1,0), (1,-1), "Helvetica"), ("FONTSIZE", (0,0), (-1,-1), 8.2),
            ("GRID", (0,0), (-1,-1), .35, pdf_hex(COLORS["sand"])), ("VALIGN", (0,0), (-1,-1), "TOP"),
        ]))
        story.append(t)
        story.append(Spacer(1, 4*mm))

    def footer(canvas, doc_obj):
        canvas.saveState()
        canvas.setFillColor(pdf_hex(COLORS["orange"]))
        canvas.rect(0, 0, A4[0], 4*mm, fill=1, stroke=0)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(pdf_hex(COLORS["charcoal"]))
        canvas.drawRightString(A4[0]-15*mm, 8*mm, f"WBCSD CDR Decision Lab | Page {doc_obj.page}")
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
    state = load_workshop_state(workshop_id)
    if not bool(state["results_revealed"]):
        st.markdown('<div class="waiting-box"><b>Response received.</b> Results are hidden until the facilitator triggers the live reveal.</div>', unsafe_allow_html=True)
        return
    group = load_participants(workshop_id)
    group = group[group["breakout_code"] == breakout_code]
    if group.empty:
        return
    st.markdown('<div class="reveal"><div class="callout"><b>Results revealed</b> - this view updates as your breakout completes its individual submissions.</div></div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(range_plot(group, INTERNAL_DB, "Internal barriers · low / average / high", COLORS["orange"]), use_container_width=True, key=f"participant_int_{workshop_id}_{breakout_code}")
    with c2:
        st.plotly_chart(range_plot(group, EXTERNAL_DB, "External enabling environment · low / average / high", COLORS["spruce"]), use_container_width=True, key=f"participant_ext_{workshop_id}_{breakout_code}")

# -----------------------------------------------------------------------------
# Participant
# -----------------------------------------------------------------------------
def participant_view():
    st.markdown('<div class="section-label">01 · Individual perspective</div>', unsafe_allow_html=True)
    st.subheader("Where would you allocate scarce attention and resources?")

    workshops = load_workshops()
    if workshops.empty:
        st.warning("No workshop has been configured yet.")
        return

    preset_workshop = st.query_params.get("workshop", "")
    preset_breakout = st.query_params.get("group", "").upper()
    active = active_workshop()
    workshop_options = workshops["workshop_id"].tolist()
    default_wid = preset_workshop if preset_workshop in workshop_options else (active["workshop_id"] if active else workshop_options[0])
    wid = st.selectbox(
        "Workshop", workshop_options, index=workshop_options.index(default_wid),
        format_func=lambda x: workshops.loc[workshops["workshop_id"] == x, "workshop_name"].iloc[0],
        key="participant_workshop",
    )
    state = load_workshop_state(wid)
    breakouts = load_breakouts(wid)
    if breakouts.empty:
        st.warning("This workshop has no breakout groups configured.")
        return

    breakout_codes = breakouts["breakout_code"].tolist()
    default_breakout_index = breakout_codes.index(preset_breakout) if preset_breakout in breakout_codes else 0

    submitted_key = f"submitted_{wid}"
    if st.session_state.get(submitted_key):
        breakout_code = st.session_state.get(f"submitted_breakout_{wid}")
        participant_reveal_fragment(wid, breakout_code)
        if st.button("Submit another test response", help="Useful during testing; remove this option for a production event if desired."):
            st.session_state[submitted_key] = False
            st.rerun()
        return

    if bool(state["submissions_locked"]):
        st.markdown('<div class="locked-box"><b>Submissions are currently locked.</b> The facilitator has closed the individual allocation stage.</div>', unsafe_allow_html=True)
        if bool(state["results_revealed"]):
            participant_reveal_fragment(wid, breakout_codes[default_breakout_index])
        return

    with st.expander("About you", expanded=True):
        a, b, c = st.columns(3)
        with a:
            participant_name = st.text_input("Name (optional)")
            company = st.text_input("Company")
        with b:
            function_name = st.selectbox("Function", FUNCTIONS)
            sector = st.text_input("Sector")
        with c:
            cdr_maturity = st.selectbox("CDR maturity", MATURITY)
            breakout_code = st.selectbox(
                "Breakout", breakout_codes, index=default_breakout_index,
                format_func=lambda code: (f"{code} · " + str(breakouts.loc[breakouts['breakout_code'] == code, 'breakout_name'].iloc[0] or "")).rstrip(" ·"),
            )

    tab_internal, tab_external = st.tabs(["Internal investment · 100 units", "External enabling environment · 100 units"])
    with tab_internal:
        st.write("Prioritise barriers your company can directly address through budget, capability and internal decision-making.")
        internal_values = allocation_editor(f"p_int_{wid}", INTERNAL)
    with tab_external:
        st.write("Prioritise external conditions that need progress through advocacy, standards, market development or collective action.")
        external_values = allocation_editor(f"p_ext_{wid}", EXTERNAL)

    biggest_reason = st.text_area(
        "What is the single biggest reason your organisation is not moving faster on CDR today?",
        max_chars=300, placeholder="One concise sentence...",
    )
    ready = bool(company.strip()) and bool(sector.strip())
    if not ready:
        st.caption("Company and Sector are required. Both allocations always remain at exactly 100.")

    if st.button("Submit my allocation", type="primary", disabled=not ready, use_container_width=True):
        # Re-check lock at transaction time.
        current_state = load_workshop_state(wid)
        if bool(current_state["submissions_locked"]):
            st.error("Submissions were just locked by the facilitator. Your response was not saved.")
            return
        submission_id = f"{wid}-{breakout_code}-{uuid.uuid4().hex[:8].upper()}"
        row = {
            "submission_id": submission_id, "submitted_at": now_iso(), "workshop_id": wid,
            "participant_name": participant_name.strip(), "company": company.strip(), "function_name": function_name,
            "sector": sector.strip(), "cdr_maturity": cdr_maturity, "breakout_code": breakout_code,
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
            "external_other": external_values["Other"], "biggest_reason": biggest_reason.strip(),
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
        st.session_state[submitted_key] = True
        st.session_state[f"submitted_breakout_{wid}"] = breakout_code
        st.rerun()

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
    ci, ce = st.tabs(["Internal consensus · 100", "External consensus · 100"])
    with ci:
        internal_values = allocation_editor(f"c_int_{wid}_{breakout_code}", INTERNAL)
    with ce:
        external_values = allocation_editor(f"c_ext_{wid}_{breakout_code}", EXTERNAL)
    rationale = st.text_area("Why did the group make this allocation?", max_chars=900)
    intervention = st.text_area("What one intervention would most help companies progress?", max_chars=450)

    if st.button("Save breakout consensus", type="primary", use_container_width=True):
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
def live_controls(wid):
    state = load_workshop_state(wid)
    st.markdown("### Live workshop controls")
    c1, c2, c3 = st.columns([1.3, 1.3, 2.4])
    with c1:
        if bool(state["submissions_locked"]):
            if st.button("Reopen submissions", use_container_width=True):
                update_workshop_state(wid, locked=0)
                st.rerun()
        else:
            if st.button("Lock submissions", type="primary", use_container_width=True):
                update_workshop_state(wid, locked=1)
                st.rerun()
    with c2:
        if bool(state["results_revealed"]):
            if st.button("Hide results", use_container_width=True):
                update_workshop_state(wid, revealed=0)
                st.rerun()
        else:
            if st.button("Reveal results", type="primary", use_container_width=True):
                update_workshop_state(wid, revealed=1)
                st.rerun()
    with c3:
        status = []
        status.append("Submissions locked" if state["submissions_locked"] else "Submissions open")
        status.append("Results visible to participants" if state["results_revealed"] else "Results hidden")
        st.markdown(f'<div class="callout"><b>Stage:</b> {" · ".join(status)}</div>', unsafe_allow_html=True)


def facilitator_view():
    st.markdown('<div class="section-label">03 · Facilitator</div>', unsafe_allow_html=True)
    st.subheader("See the room, surface disagreement, and guide the reveal")
    if not check_facilitator_pin():
        return
    wid = select_workshop("Workshop", key="fac_workshop")
    if not wid:
        return
    live_controls(wid)

    participants = load_participants(wid)
    consensus = load_consensus(wid)
    workshops = load_workshops()
    wrow = workshops[workshops["workshop_id"] == wid].iloc[0].to_dict()
    breakouts = load_breakouts(wid)
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
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(range_plot(data, INTERNAL_DB, "Internal · low / average / high", COLORS["orange"]), use_container_width=True)
        with c2:
            st.plotly_chart(range_plot(data, EXTERNAL_DB, "External · low / average / high", COLORS["spruce"]), use_container_width=True)
        st.markdown("### Agreement / disagreement")
        combined = pd.concat([
            summary_table(data, INTERNAL_DB).assign(Type="Internal"),
            summary_table(data, EXTERNAL_DB).assign(Type="External"),
        ], ignore_index=True).sort_values("Std dev", ascending=False)
        st.dataframe(combined[["Type", "Barrier", "Low", "Average", "High", "Std dev", "Agreement"]], hide_index=True, use_container_width=True)

    with comparisons:
        st.markdown("### Priority heat maps")
        hi, he = st.tabs(["Internal", "External"])
        with hi:
            fig = breakout_heatmap(participants, INTERNAL_DB, "mean", "Average internal allocation by breakout")
            if fig: st.plotly_chart(fig, use_container_width=True)
        with he:
            fig = breakout_heatmap(participants, EXTERNAL_DB, "mean", "Average external allocation by breakout")
            if fig: st.plotly_chart(fig, use_container_width=True)

        st.markdown("### Agreement heat maps")
        ai, ae = st.tabs(["Internal", "External"])
        with ai:
            fig = breakout_heatmap(participants, INTERNAL_DB, "std", "Internal disagreement by breakout · higher = more divergent")
            if fig: st.plotly_chart(fig, use_container_width=True)
        with ae:
            fig = breakout_heatmap(participants, EXTERNAL_DB, "std", "External disagreement by breakout · higher = more divergent")
            if fig: st.plotly_chart(fig, use_container_width=True)

        st.markdown("### Compare one barrier across breakouts")
        category = st.radio("Barrier type", ["Internal", "External"], horizontal=True)
        mapping = INTERNAL_DB if category == "Internal" else EXTERNAL_DB
        barrier = st.selectbox("Barrier", list(mapping.keys()))
        col = mapping[barrier]
        rows = []
        for code, g in participants.groupby("breakout_code"):
            rows.append({"Breakout": code, "Low": g[col].min(), "Average": g[col].mean(), "High": g[col].max(), "Std dev": g[col].std(ddof=0)})
        comp = pd.DataFrame(rows).sort_values("Average", ascending=True)
        fig = go.Figure()
        for _, r in comp.iterrows():
            fig.add_trace(go.Scatter(x=[r["Low"], r["High"]], y=[r["Breakout"], r["Breakout"]], mode="lines", line=dict(color=COLORS["sand"], width=9), showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=comp["Average"], y=comp["Breakout"], mode="markers", marker=dict(size=13, color=COLORS["orange"]), showlegend=False,
                                 customdata=np.stack([comp["Low"], comp["High"], comp["Std dev"]], axis=-1),
                                 hovertemplate="%{y}<br>Average %{x:.1f}<br>Low %{customdata[0]:.1f}<br>High %{customdata[1]:.1f}<br>Std dev %{customdata[2]:.1f}<extra></extra>"))
        fig.update_layout(title=barrier, xaxis=dict(range=[0,100], title="Allocation units"), yaxis_title=None, height=max(300, 65*len(comp)), plot_bgcolor="white")
        st.plotly_chart(fig, use_container_width=True)

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

# -----------------------------------------------------------------------------
# Workshop configuration / admin
# -----------------------------------------------------------------------------
def workshop_configuration_view():
    st.markdown('<div class="section-label">Admin · workshop configuration</div>', unsafe_allow_html=True)
    st.subheader("Configure the room before participants arrive")
    if not check_facilitator_pin(key="config_facilitator_pin"):
        return

    with st.expander("Create a new workshop", expanded=load_workshops().empty):
        with st.form("create_workshop_form"):
            c1, c2 = st.columns(2)
            with c1:
                workshop_name = st.text_input("Workshop name", placeholder="CDR Barrier Auction")
                event_name = st.text_input("Event / programme", placeholder="New York Climate Week 2026")
                event_date = st.date_input("Event date")
            with c2:
                participant_target = st.number_input("Expected participants", 1, 1000, 40)
                duration_minutes = st.number_input("Workshop duration (minutes)", 10, 240, 45)
                number_breakouts = st.number_input("Number of breakout groups", 1, 30, 5)
            code_style = st.selectbox("Default breakout codes", ["B1, B2, B3…", "BLUE1, BLUE2, BLUE3…"])
            create = st.form_submit_button("Create workshop", type="primary", use_container_width=True)
        if create:
            if not workshop_name.strip():
                st.error("Workshop name is required.")
            else:
                wid = f"WS-{uuid.uuid4().hex[:8].upper()}"
                codes = [f"BLUE{i}" if code_style.startswith("BLUE") else f"B{i}" for i in range(1, int(number_breakouts)+1)]
                try:
                    with engine.begin() as conn:
                        conn.execute(text("UPDATE workshops SET is_active=0"))
                        conn.execute(text("""
                            INSERT INTO workshops (workshop_id, workshop_name, event_name, event_date, participant_target, duration_minutes, is_active, created_at)
                            VALUES (:wid,:name,:event,:date,:target,:duration,1,:created)
                        """), {"wid":wid,"name":workshop_name.strip(),"event":event_name.strip(),"date":str(event_date),"target":int(participant_target),"duration":int(duration_minutes),"created":now_iso()})
                        conn.execute(text("INSERT INTO workshop_state (workshop_id, submissions_locked, results_revealed, updated_at) VALUES (:wid,0,0,:updated)"), {"wid":wid,"updated":now_iso()})
                        for i, code in enumerate(codes,1):
                            conn.execute(text("""
                                INSERT INTO workshop_breakouts
                                    (workshop_id, breakout_code, breakout_name)
                                VALUES (:wid,:code,:name)
                            """), {"wid":wid,"code":code,"name":f"Breakout {i}"})
                    st.success("Workshop created.")
                    st.rerun()
                except Exception as exc:
                    st.error(
                        "The workshop could not be created. The most likely cause is an older "
                        "database schema retained from a previous deployment. V1.0.1 includes "
                        "an automatic migration. Restart/redeploy once and try again."
                    )
                    st.exception(exc)

    wid = select_workshop("Workshop to manage", key="config_workshop")
    if not wid:
        return
    workshops = load_workshops()
    row = workshops[workshops["workshop_id"] == wid].iloc[0]
    c1, c2, c3 = st.columns(3)
    c1.metric("Expected participants", int(row["participant_target"] or 0))
    c2.metric("Duration", f"{int(row['duration_minutes'] or 0)} min")
    c3.metric("Status", "Active" if bool(row["is_active"]) else "Inactive")
    if not bool(row["is_active"]) and st.button("Make this the active workshop", use_container_width=True):
        with engine.begin() as conn:
            conn.execute(text("UPDATE workshops SET is_active=0"))
            conn.execute(text("UPDATE workshops SET is_active=1 WHERE workshop_id=:wid"), {"wid":wid})
        st.rerun()

    st.markdown("### Breakout groups")
    breakouts = load_breakouts(wid)
    edited = st.data_editor(
        breakouts[["breakout_code", "breakout_name"]].copy(), hide_index=True, num_rows="dynamic", use_container_width=True,
        column_config={"breakout_code": st.column_config.TextColumn("Code", required=True), "breakout_name": st.column_config.TextColumn("Name")},
    )
    if st.button("Save breakout groups", type="primary", use_container_width=True):
        clean = edited.copy()
        clean["breakout_code"] = clean["breakout_code"].astype(str).str.strip().str.upper()
        clean["breakout_name"] = clean["breakout_name"].fillna("").astype(str).str.strip()
        clean = clean[clean["breakout_code"] != ""]
        if clean["breakout_code"].duplicated().any():
            st.error("Breakout codes must be unique.")
        else:
            with engine.begin() as conn:
                conn.execute(text("DELETE FROM workshop_breakouts WHERE workshop_id=:wid"), {"wid":wid})
                for _, br in clean.iterrows():
                    conn.execute(text("INSERT INTO workshop_breakouts (workshop_id, breakout_code, breakout_name) VALUES (:wid,:code,:name)"), {"wid":wid,"code":br["breakout_code"],"name":br["breakout_name"]})
            st.success("Breakouts saved.")
            st.rerun()

    st.markdown("### Links")
    base_url = st.text_input("Deployed app URL", placeholder="https://your-app.streamlit.app").rstrip("/")
    if base_url:
        st.markdown("**Participant links**")
        for _, br in load_breakouts(wid).iterrows():
            st.code(f"{base_url}/?workshop={wid}&group={br['breakout_code']}", language=None)
        st.markdown("**Breakout lead links**")
        for _, br in load_breakouts(wid).iterrows():
            st.code(f"{base_url}/?lead=1&workshop={wid}&group={br['breakout_code']}", language=None)
        st.markdown("**Facilitator link**")
        st.code(base_url, language=None)
        st.caption("Facilitator and Workshop configuration remain protected by the facilitator PIN.")

# -----------------------------------------------------------------------------
# Navigation
# -----------------------------------------------------------------------------
header()
lead_mode = str(st.query_params.get("lead", "0")) == "1"

nav_options = ["Participant", "Breakout lead", "Facilitator", "Workshop configuration"]
default_idx = 1 if lead_mode else 0

mode = st.sidebar.radio("View", nav_options, index=default_idx)
st.sidebar.markdown("---")
st.sidebar.caption("WBCSD · CDR Decision Lab · Version 1.0.1")
st.sidebar.caption("Breakout lead and facilitator/admin areas are protected by separate PINs.")

if mode == "Participant":
    participant_view()
elif mode == "Breakout lead":
    breakout_lead_view()
elif mode == "Facilitator":
    facilitator_view()
else:
    workshop_configuration_view()
