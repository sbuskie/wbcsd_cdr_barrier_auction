
import io
import os
import uuid
from datetime import datetime, timezone

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import create_engine, text

st.set_page_config(
    page_title="WBCSD CDR Barrier Auction",
    page_icon="🧱",
    layout="wide",
)

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
}

st.markdown(
    f"""
    <style>
    html, body, [class*="css"] {{
        font-family: Arial, sans-serif;
        color: {COLORS["charcoal"]};
    }}
    .block-container {{
        padding-top: 1.3rem;
        padding-bottom: 2.5rem;
    }}
    .wbcsd-banner {{
        border-left: 8px solid {COLORS["orange"]};
        background: {COLORS["pearl"]};
        padding: 0.9rem 1.1rem;
        margin: 0.4rem 0 1.2rem 0;
    }}
    .wbcsd-banner h2 {{
        margin: 0;
        color: {COLORS["charcoal"]};
        font-weight: 600;
    }}
    .helper {{
        color: {COLORS["spruce"]};
        font-size: 0.95rem;
    }}
    .ok {{
        background: {COLORS["sage"]};
        border-radius: 8px;
        padding: 0.45rem 0.7rem;
    }}
    .warn {{
        background: {COLORS["gold"]};
        border-radius: 8px;
        padding: 0.45rem 0.7rem;
    }}
    .bad {{
        background: #f8d4d5;
        border-radius: 8px;
        padding: 0.45rem 0.7rem;
    }}
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
    "Sustainability",
    "Procurement",
    "Finance",
    "Strategy",
    "Operations",
    "Legal / Risk",
    "Executive leadership",
    "Other",
]

DATABASE_URL = None
try:
    DATABASE_URL = st.secrets.get("DATABASE_URL")
except Exception:
    DATABASE_URL = None

DATABASE_URL = DATABASE_URL or os.getenv("DATABASE_URL") or "sqlite:///cdr_barrier_auction.db"

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False, "timeout": 30}

engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def init_db():
    with engine.begin() as conn:
        if DATABASE_URL.startswith("sqlite"):
            conn.execute(text("PRAGMA journal_mode=WAL;"))

        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS participant_submissions (
            submission_id TEXT PRIMARY KEY,
            submitted_at TEXT NOT NULL,
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
        )
        """))

        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS breakout_consensus (
            breakout_code TEXT PRIMARY KEY,
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
            wbcsd_intervention TEXT
        )
        """))

init_db()

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

def load_participants():
    return pd.read_sql("SELECT * FROM participant_submissions ORDER BY submitted_at", engine)

def load_consensus():
    return pd.read_sql("SELECT * FROM breakout_consensus ORDER BY breakout_code", engine)

def agreement_label(std):
    if pd.isna(std):
        return "n/a"
    if std <= 8:
        return "High"
    if std <= 15:
        return "Medium"
    return "Low"

def allocation_editor(prefix, labels, defaults=None):
    defaults = defaults or {}
    cols = st.columns(2)
    values = {}
    for i, label in enumerate(labels):
        with cols[i % 2]:
            values[label] = st.number_input(
                label,
                min_value=0,
                max_value=100,
                value=int(defaults.get(label, 0)),
                step=1,
                key=f"{prefix}_{i}",
            )
    total = int(sum(values.values()))
    remaining = 100 - total
    if total == 100:
        st.markdown(f'<div class="ok"><b>Total: {total}</b> · Ready to submit</div>', unsafe_allow_html=True)
    elif total < 100:
        st.markdown(f'<div class="warn"><b>Total: {total}</b> · {remaining} units remaining</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="bad"><b>Total: {total}</b> · {-remaining} units over budget</div>', unsafe_allow_html=True)
    return values, total

def header():
    c1, c2 = st.columns([1.2, 4.8])
    with c1:
        st.image("assets/wbcsd_logo.jpg", use_container_width=True)
    with c2:
        st.markdown(
            """
            <div class="wbcsd-banner">
              <h2>CDR Barrier Auction</h2>
              <div class="helper">New York Climate Week 2026 · individual priorities → group decision → WBCSD action</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

def check_pin():
    expected = None
    try:
        expected = st.secrets.get("FACILITATOR_PIN")
    except Exception:
        expected = None
    expected = expected or os.getenv("FACILITATOR_PIN") or "wbcsd-demo"
    supplied = st.text_input("Facilitator PIN", type="password")
    if supplied != expected:
        st.info("Enter the facilitator PIN to continue.")
        return False
    return True

def participant_view():
    st.subheader("1 · Your perspective")
    st.caption("Your individual response is captured before breakout discussion so we preserve how people independently think about CDR barriers.")

    preset_breakout = ""
    try:
        preset_breakout = st.query_params.get("group", "")
    except Exception:
        preset_breakout = ""

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
            breakout_code = st.text_input("Breakout code", value=str(preset_breakout).upper()).strip().upper()

    st.markdown("### Internal investment priorities")
    st.write("Allocate **exactly 100 units** across barriers your company can address through its own budget, capability and decision-making.")
    internal_values, internal_total = allocation_editor("p_internal", INTERNAL)

    st.markdown("### External enabling environment")
    st.write("Allocate **exactly 100 influence units** across external conditions where progress is needed through advocacy, standards, market development or collective action.")
    external_values, external_total = allocation_editor("p_external", EXTERNAL)

    biggest_reason = st.text_area(
        "What is the single biggest reason your organisation is not moving faster on CDR today?",
        max_chars=250,
        placeholder="One concise sentence…",
    )

    ready = (
        internal_total == 100
        and external_total == 100
        and bool(company.strip())
        and bool(sector.strip())
        and bool(breakout_code.strip())
    )

    if not ready:
        st.caption("To submit: both allocations must total 100, and Company, Sector and Breakout code are required.")

    if st.button("Submit my allocation", type="primary", disabled=not ready, use_container_width=True):
        submission_id = f"NYCW26-{breakout_code}-{uuid.uuid4().hex[:8].upper()}"
        row = {
            "submission_id": submission_id,
            "submitted_at": now_iso(),
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
                    submission_id, submitted_at, participant_name, company, function_name, sector,
                    cdr_maturity, breakout_code,
                    internal_leadership, internal_governance, internal_budget, internal_capability, internal_procurement,
                    external_cost, external_standards, external_technology, external_quality,
                    external_demand, external_reputation, external_other, biggest_reason
                ) VALUES (
                    :submission_id, :submitted_at, :participant_name, :company, :function_name, :sector,
                    :cdr_maturity, :breakout_code,
                    :internal_leadership, :internal_governance, :internal_budget, :internal_capability, :internal_procurement,
                    :external_cost, :external_standards, :external_technology, :external_quality,
                    :external_demand, :external_reputation, :external_other, :biggest_reason
                )
            """), row)
        st.success(f"Submitted. Your response ID is **{submission_id}**.")
        st.balloons()

def breakout_lead_view():
    st.subheader("2 · Breakout consensus")
    st.caption("Use this after discussing the individual results. Capture the coordinated decision the group would make together.")
    if not check_pin():
        return

    participants = load_participants()
    available = sorted(participants["breakout_code"].dropna().unique().tolist()) if not participants.empty else []
    breakout_code = st.selectbox("Breakout", available) if available else st.text_input("Breakout code").strip().upper()
    if not breakout_code:
        return

    group = participants[participants["breakout_code"] == breakout_code]
    st.metric("Individual submissions in this breakout", len(group))

    if not group.empty:
        st.markdown("#### Individual starting point")
        internal_avg = {label: float(group[col].mean()) for label, col in INTERNAL_DB.items()}
        external_avg = {label: float(group[col].mean()) for label, col in EXTERNAL_DB.items()}
        c1, c2 = st.columns(2)
        with c1:
            idf = pd.DataFrame({"Barrier": list(internal_avg.keys()), "Average": list(internal_avg.values())}).sort_values("Average")
            fig = px.bar(idf, x="Average", y="Barrier", orientation="h", title="Internal · participant average")
            fig.update_traces(marker_color=COLORS["orange"])
            fig.update_layout(height=340, margin=dict(l=0, r=10, t=45, b=0))
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            edf = pd.DataFrame({"Barrier": list(external_avg.keys()), "Average": list(external_avg.values())}).sort_values("Average")
            fig = px.bar(edf, x="Average", y="Barrier", orientation="h", title="External · participant average")
            fig.update_traces(marker_color=COLORS["spruce"])
            fig.update_layout(height=340, margin=dict(l=0, r=10, t=45, b=0))
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Agree one coordinated allocation")
    internal_values, internal_total = allocation_editor(f"c_internal_{breakout_code}", INTERNAL)
    external_values, external_total = allocation_editor(f"c_external_{breakout_code}", EXTERNAL)

    rationale = st.text_area(
        "Why did the group make this allocation?",
        max_chars=800,
        placeholder="Capture the key trade-offs, disagreements and reasons behind the final decision.",
    )
    intervention = st.text_area(
        "What one intervention would most help companies progress?",
        max_chars=400,
        placeholder="Practical guidance, peer learning, standards, advocacy, market intervention…",
    )

    ready = internal_total == 100 and external_total == 100
    if st.button("Save breakout consensus", type="primary", disabled=not ready, use_container_width=True):
        row = {
            "breakout_code": breakout_code,
            "submitted_at": now_iso(),
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
            "rationale": rationale.strip(),
            "wbcsd_intervention": intervention.strip(),
        }
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM breakout_consensus WHERE breakout_code=:breakout_code"), {"breakout_code": breakout_code})
            conn.execute(text("""
                INSERT INTO breakout_consensus (
                    breakout_code, submitted_at,
                    internal_leadership, internal_governance, internal_budget, internal_capability, internal_procurement,
                    external_cost, external_standards, external_technology, external_quality, external_demand,
                    external_reputation, external_other, rationale, wbcsd_intervention
                ) VALUES (
                    :breakout_code, :submitted_at,
                    :internal_leadership, :internal_governance, :internal_budget, :internal_capability, :internal_procurement,
                    :external_cost, :external_standards, :external_technology, :external_quality, :external_demand,
                    :external_reputation, :external_other, :rationale, :wbcsd_intervention
                )
            """), row)
        st.success(f"Consensus saved for {breakout_code}.")

def ranking_table(df, mapping):
    rows = []
    for label, col in mapping.items():
        rows.append({
            "Barrier": label,
            "Average": round(df[col].mean(), 1),
            "Median": round(df[col].median(), 1),
            "Std dev": round(df[col].std(ddof=0), 1),
        })
    out = pd.DataFrame(rows).sort_values("Average", ascending=False).reset_index(drop=True)
    out.insert(0, "Rank", range(1, len(out)+1))
    out["Agreement"] = out["Std dev"].apply(agreement_label)
    return out

def excel_export(participants, consensus):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        participants.to_excel(writer, sheet_name="Participants", index=False)
        consensus.to_excel(writer, sheet_name="Breakout Consensus", index=False)
    return buf.getvalue()

def breakout_report_html(code, group, consensus_row):
    internal_rank = ranking_table(group, INTERNAL_DB) if not group.empty else pd.DataFrame()
    external_rank = ranking_table(group, EXTERNAL_DB) if not group.empty else pd.DataFrame()
    internal_top = internal_rank.iloc[0]["Barrier"] if not internal_rank.empty else "No data"
    external_top = external_rank.iloc[0]["Barrier"] if not external_rank.empty else "No data"
    reason_lines = group["biggest_reason"].dropna()
    reason_lines = [x for x in reason_lines.tolist() if str(x).strip()][:6]
    rationale = ""
    intervention = ""
    if consensus_row is not None:
        rationale = consensus_row.get("rationale", "") or ""
        intervention = consensus_row.get("wbcsd_intervention", "") or ""

    bullets = "".join(f"<li>{r}</li>" for r in reason_lines) or "<li>No qualitative responses captured.</li>"
    return f"""
    <html><head><meta charset="utf-8"><style>
    body{{font-family:Arial,sans-serif;color:#2a2825;margin:32px}}
    h1{{border-left:10px solid #f8781e;padding-left:14px}}
    h2{{color:#465c66}}
    .grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}
    .box{{background:#f0ede6;padding:14px;border-radius:8px}}
    .metric{{font-size:28px;font-weight:bold}}
    </style></head><body>
    <h1>CDR Barrier Auction · {code}</h1>
    <div class="grid">
      <div class="box"><div>Submissions</div><div class="metric">{len(group)}</div></div>
      <div class="box"><div>Highest internal priority</div><div class="metric">{internal_top}</div></div>
      <div class="box"><div>Highest external priority</div><div class="metric">{external_top}</div></div>
      <div class="box"><div>WBCSD intervention</div><div>{intervention or "Not yet recorded"}</div></div>
    </div>
    <h2>Why participants are not moving faster</h2>
    <ul>{bullets}</ul>
    <h2>Breakout rationale</h2>
    <p>{rationale or "Not yet recorded"}</p>
    </body></html>
    """.encode("utf-8")

def facilitator_view():
    st.subheader("3 · Facilitator dashboard")
    if not check_pin():
        return

    participants = load_participants()
    consensus = load_consensus()

    if participants.empty:
        st.warning("No participant submissions yet.")
        return

    breakout_options = ["All"] + sorted(participants["breakout_code"].dropna().unique().tolist())
    selected = st.selectbox("View", breakout_options)

    data = participants if selected == "All" else participants[participants["breakout_code"] == selected]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Submissions", len(data))
    m2.metric("Companies", data["company"].nunique())
    m3.metric("Breakouts", data["breakout_code"].nunique())
    m4.metric("Consensus reports", len(consensus) if selected == "All" else int((consensus["breakout_code"] == selected).sum()))

    int_rank = ranking_table(data, INTERNAL_DB)
    ext_rank = ranking_table(data, EXTERNAL_DB)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### Internal priorities")
        st.dataframe(int_rank, hide_index=True, use_container_width=True)
        p = int_rank.sort_values("Average")
        fig = px.bar(p, x="Average", y="Barrier", orientation="h")
        fig.update_traces(marker_color=COLORS["orange"])
        fig.update_layout(height=360, margin=dict(l=0, r=10, t=10, b=0))
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.markdown("### External enabling environment")
        st.dataframe(ext_rank, hide_index=True, use_container_width=True)
        p = ext_rank.sort_values("Average")
        fig = px.bar(p, x="Average", y="Barrier", orientation="h")
        fig.update_traces(marker_color=COLORS["spruce"])
        fig.update_layout(height=360, margin=dict(l=0, r=10, t=10, b=0))
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Where participants disagree")
    disagreement = pd.concat([
        int_rank.assign(Type="Internal"),
        ext_rank.assign(Type="External")
    ], ignore_index=True).sort_values("Std dev", ascending=False)
    st.dataframe(
        disagreement[["Type", "Barrier", "Average", "Std dev", "Agreement"]].head(8),
        hide_index=True,
        use_container_width=True,
    )

    if selected != "All":
        row_df = consensus[consensus["breakout_code"] == selected]
        consensus_row = row_df.iloc[0].to_dict() if not row_df.empty else None

        if consensus_row:
            st.markdown("### Individual average vs breakout consensus")
            comp_rows = []
            for label, col in INTERNAL_DB.items():
                comp_rows.append({
                    "Barrier": label,
                    "Participant average": round(data[col].mean(), 1),
                    "Consensus": consensus_row[col],
                    "Difference": round(consensus_row[col] - data[col].mean(), 1),
                })
            st.dataframe(pd.DataFrame(comp_rows), hide_index=True, use_container_width=True)
            st.info(f"**Breakout rationale:** {consensus_row.get('rationale') or 'Not recorded'}")
            st.info(f"**Recommended WBCSD intervention:** {consensus_row.get('wbcsd_intervention') or 'Not recorded'}")

        st.download_button(
            "Download one-page breakout report (HTML)",
            data=breakout_report_html(selected, data, consensus_row),
            file_name=f"CDR_Barrier_Auction_{selected}_Report.html",
            mime="text/html",
            use_container_width=True,
        )

    st.markdown("### Qualitative responses")
    q = data[["company", "function_name", "breakout_code", "biggest_reason"]].copy()
    q = q[q["biggest_reason"].fillna("").str.strip() != ""]
    st.dataframe(q, hide_index=True, use_container_width=True)

    st.download_button(
        "Download full workshop dataset (Excel)",
        data=excel_export(participants, consensus),
        file_name="WBCSD_CDR_Barrier_Auction_Results.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    st.caption("The dashboard refreshes on every Streamlit interaction. Change the View selector or refresh the page during the live reveal to pull the latest submissions.")

header()

mode = st.sidebar.radio(
    "Mode",
    ["Participant", "Breakout lead", "Facilitator"],
)
st.sidebar.markdown("---")
st.sidebar.caption("WBCSD · CDR implementation workshop")
st.sidebar.caption("SQLite for local MVP; configure DATABASE_URL for persistent Postgres/Supabase.")

if mode == "Participant":
    participant_view()
elif mode == "Breakout lead":
    breakout_lead_view()
else:
    facilitator_view()
