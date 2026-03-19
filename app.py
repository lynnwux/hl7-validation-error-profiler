import json
import re
from datetime import datetime
from pathlib import Path

import os
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

import pandas as pd
import plotly.express as px
import streamlit as st

# Support Streamlit Cloud secrets as fallback for .env
if not os.environ.get("OPENAI_API_KEY") and "OPENAI_API_KEY" in st.secrets:
    os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]

import openai

st.set_page_config(page_title="HL7 Validation Error Profiler", layout="wide")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NORMALIZATION_RULES = [
    (re.compile(r"Missing field 18.*PID", re.IGNORECASE),
     "Missing Patient Account Number (PID-18)"),
    (re.compile(r"Missing required PV1 element", re.IGNORECASE),
     "Missing Segment (PV1)"),
    (re.compile(r"Invalid value.*PID.*field 8", re.IGNORECASE),
     "Invalid Administrative Sex (PID-8)"),
    (re.compile(r"Invalid date/time value.*MSH.*field 7", re.IGNORECASE),
     "Invalid Timestamp (MSH-7)"),
    (re.compile(r"Invalid date/time value.*EVN.*field 2", re.IGNORECASE),
     "Invalid Timestamp (EVN-2)"),
    (re.compile(r"Unescaped separator", re.IGNORECASE),
     "Unescaped Separator(s) Found (DG1-3)"),
    (re.compile(r"Component data structure", re.IGNORECASE),
     "Unescaped Separator(s) Found (DG1-3)"),
]


def extract_validation_errors(text: str) -> list[str]:
    """Split the Text field on '+' and strip the 'Not forwarding...' preamble."""
    # The first error chunk often starts with "Not forwarding ... because of
    # validation failure: ERROR ..." – strip everything up to the first real
    # ERROR after the preamble.
    parts = re.split(r"\n?\+\n?", text)
    errors = []
    for part in parts:
        part = part.strip()
        # Remove the "Not forwarding ..." wrapper if present
        match = re.search(
            r"because of validation failure:\s*(.*)", part, re.DOTALL
        )
        if match:
            part = match.group(1).strip()
        if part:
            errors.append(part)
    return errors


def normalize_error(raw: str) -> str:
    """Map a raw error string to a friendly category."""
    for pattern, label in NORMALIZATION_RULES:
        if pattern.search(raw):
            return label
    return raw.strip()[:120]  # fallback – truncated raw text


def load_and_process(csv_path: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (message_df, error_summary_df)."""
    df = pd.read_csv(csv_path)
    # Filter to only router_Router validation rows
    df = df[df["ConfigName"] == "router_Router"].copy()
    df = df.reset_index(drop=True)

    rows = []
    for _, row in df.iterrows():
        raw_errors = extract_validation_errors(str(row["Text"]))
        normalized = [normalize_error(e) for e in raw_errors]
        # Deduplicate within a single message
        normalized = list(dict.fromkeys(normalized))
        rows.append(
            {
                "MessageId": row["MessageId"],
                "SessionId": row["SessionId"],
                "TimeLogged": row["TimeLogged"],
                "error_count": len(normalized),
                "error_list": ", ".join(normalized),
                "errors": normalized,
            }
        )

    msg_df = pd.DataFrame(rows)
    total = len(msg_df)

    # Build summary
    from collections import Counter

    counter: Counter[str] = Counter()
    for errs in msg_df["errors"]:
        counter.update(errs)

    summary_rows = []
    for error_type, count in counter.most_common():
        summary_rows.append(
            {
                "error_type": error_type,
                "count": count,
                "percentage": round(count / total * 100, 1) if total else 0,
            }
        )
    summary_df = pd.DataFrame(summary_rows)

    return msg_df, summary_df


INTERSYSTEMS_TEAL = "#00B2A9"
INTERSYSTEMS_NAVY = "#002B5C"


def build_report_spec(msg_df: pd.DataFrame, summary_df: pd.DataFrame, org_name: str = "") -> dict:
    """Build a JSON spec describing the report data."""
    total = len(msg_df)
    error_counts = msg_df["error_count"].value_counts().sort_index()
    return {
        "title": "HL7 Validation Error Profiler",
        "organization": org_name,
        "total_messages": total,
        "high_frequency_warnings": [
            {
                "error_type": r["error_type"],
                "percentage": r["percentage"],
                "count": int(r["count"]),
            }
            for _, r in summary_df[summary_df["percentage"] > 50].iterrows()
        ],
        "error_summary": [
            {
                "error_type": r["error_type"],
                "count": int(r["count"]),
                "percentage": r["percentage"],
            }
            for _, r in summary_df.iterrows()
        ],
        "errors_per_message_distribution": [
            {"num_errors": int(n), "message_count": int(c)}
            for n, c in error_counts.items()
        ],
        "brand_colors": {
            "teal": INTERSYSTEMS_TEAL,
            "navy": INTERSYSTEMS_NAVY,
        },
    }


@st.cache_data(show_spinner=False)
def generate_html_via_openai(spec_json: str) -> str:
    """Send the report spec to OpenAI and get back styled HTML."""
    spec = json.loads(spec_json)
    client = openai.OpenAI()
    prompt = f"""Generate a single-page printable HTML report (US Letter portrait, 8.5x11 inches).

Requirements:
- All CSS must be inline in a <style> tag — no external resources
- Use the brand colors: teal {spec['brand_colors']['teal']} and navy {spec['brand_colors']['navy']}
- Professional, clean layout with good use of whitespace
- Include: title, organization name, total messages, high-frequency warnings (full-width amber/orange banner spanning the entire page width), error summary table, a CSS-based horizontal bar chart for error distribution, and a summary of errors-per-message distribution
- The page must fit on exactly one printed page (use @media print and @page rules)
- Use modern CSS (flexbox/grid) for layout
- Make it visually polished — suitable for presenting to a client
- Include a footer at the bottom of the page: "© {datetime.now().year} Yours Truly HIE. All rights reserved."

Here is the report data as JSON:

{json.dumps(spec, indent=2)}

Return ONLY the complete HTML document, no markdown fences or explanation."""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()


@st.cache_data(show_spinner=False)
def html_to_pdf(html: str) -> bytes:
    """Convert HTML to PDF by calling html_to_pdf.py in a subprocess."""
    import subprocess, sys
    script = str(Path(__file__).parent / "html_to_pdf.py")
    python = sys.executable
    result = subprocess.run(
        [python, script],
        input=html.encode("utf-8"),
        capture_output=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"PDF conversion failed: {result.stderr.decode()}")
    return result.stdout


def generate_pdf(msg_df: pd.DataFrame, summary_df: pd.DataFrame, org_name: str = "") -> bytes:
    """Build spec → OpenAI HTML → PDF."""
    spec = build_report_spec(msg_df, summary_df, org_name)
    spec_json = json.dumps(spec, sort_keys=True)
    html = generate_html_via_openai(spec_json)
    # Strip markdown fences if present
    html = re.sub(r"^```html?\s*\n?", "", html)
    html = re.sub(r"\n?```\s*$", "", html)
    return html_to_pdf(html)


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

st.title("HL7 Validation Error Profiler")

# File selection – default to bundled sample, or allow upload
default_csv = Path(__file__).parent / "exportQueryN.csv"

upload = st.sidebar.file_uploader("Upload a CSV error log", type=["csv"])
if upload is not None:
    csv_source = upload
elif default_csv.exists():
    csv_source = str(default_csv)
else:
    st.warning("Please upload a CSV file to get started.")
    st.stop()

msg_df, summary_df = load_and_process(csv_source)

_is_cloud = not Path(__file__).parent.joinpath(".env").exists()

@st.fragment
def _pdf_sidebar():
    st.markdown("---")
    st.markdown("### Export PDF Report")
    if _is_cloud:
        st.text_input("Who is the report for?", placeholder="e.g. Community Hospital", disabled=True)
        st.button("Generate PDF Report", disabled=True)
        st.caption("PDF export is only available when running locally.")
        return
    org = st.text_input("Who is the report for?", placeholder="e.g. Community Hospital")
    if org.strip():
        if st.button("Generate PDF Report"):
            with st.spinner("Generating PDF report..."):
                safe = re.sub(r"[^\w\s-]", "", org.strip()).replace(" ", "_")
                pdf_bytes = generate_pdf(msg_df, summary_df, org.strip())
                st.session_state["_pdf_bytes"] = pdf_bytes
                st.session_state["_pdf_fname"] = f"HL7_Validation_Report_{safe}.pdf"
                st.rerun(scope="fragment")
        if "_pdf_bytes" in st.session_state:
            st.download_button(
                label="Download PDF Report",
                data=st.session_state["_pdf_bytes"],
                file_name=st.session_state["_pdf_fname"],
                mime="application/pdf",
            )
    else:
        st.info("Enter an organization name to enable PDF export.")

with st.sidebar:
    _pdf_sidebar()
total_messages = len(msg_df)

# --- Header + Ring + Summary (compact) ---
st.markdown("---")

col_stats, col_ring = st.columns([3, 1])
with col_stats:
    st.metric("Total Messages Analyzed", total_messages)
    # High-frequency warnings
    high_freq = summary_df[summary_df["percentage"] > 50]
    for _, row in high_freq.iterrows():
        st.warning(
            f"High frequency issue detected: **{row['error_type']}** "
            f"appears in {row['percentage']}% of messages "
            f"({row['count']} of {total_messages})."
        )
    # Error Summary inline
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("## Error Summary")
    summary_cols = st.columns(3)
    for i, (_, row) in enumerate(summary_df.iterrows()):
        with summary_cols[i % 3]:
            st.markdown(
                f"<p style='font-size:0.86em; color:gray; margin:0.2em 0'>"
                f"{row['error_type']} : <span style='font-size:0.94em; font-weight:bold; color:#002B5C'>{row['percentage']}%</span></p>",
                unsafe_allow_html=True,
            )

with col_ring:
    error_counts = msg_df["error_count"].value_counts().sort_index()
    ring_data = pd.DataFrame({
        "category": [f"{n} error{'s' if n != 1 else ''}" for n in error_counts.index],
        "count": error_counts.values,
    })
    ring_fig = px.pie(
        ring_data,
        values="count",
        names="category",
        hole=0.55,
        color_discrete_sequence=["#00B2A9", "#005F6B", "#002B5C", "#7C3AED", "#DB2777"],
    )
    ring_fig.update_layout(
        margin=dict(t=0, b=0, l=0, r=0),
        height=365,
        showlegend=True,
        legend=dict(font=dict(size=12), orientation="h", y=-0.15),
        annotations=[dict(text="Errors<br>per Msg", x=0.5, y=0.5, font_size=13, showarrow=False)],
    )
    ring_fig.update_traces(textinfo="value+percent", textfont_size=12)
    st.plotly_chart(ring_fig, width="stretch")

st.markdown("<br>", unsafe_allow_html=True)
st.markdown("---")
st.markdown("<br>", unsafe_allow_html=True)

# --- Bar Chart ---
st.markdown("## Error Distribution")
INTERSYSTEMS_TEAL = "#00B2A9"
INTERSYSTEMS_NAVY = "#002B5C"

fig = px.bar(
    summary_df,
    x="error_type",
    y="count",
    text="percentage",
    labels={"error_type": "Error Type", "count": "Message Count"},
    color="count",
    color_continuous_scale=[INTERSYSTEMS_NAVY, INTERSYSTEMS_TEAL],
)
fig.update_traces(
    texttemplate="%{text}%",
    textposition="outside",
    textfont_size=20,
)
fig.update_coloraxes(showscale=False)
fig.update_layout(
    xaxis_tickangle=-30,
    xaxis_tickfont_size=20,
    yaxis_tickfont_size=20,
    xaxis_title_font_size=24,
    yaxis_title_font_size=24,
    showlegend=False,
    margin=dict(b=160),
)
st.plotly_chart(fig, width="stretch")

st.markdown("<br>", unsafe_allow_html=True)
st.markdown("---")
st.markdown("<br>", unsafe_allow_html=True)

# --- Message-Level Table ---
st.markdown("## Message Details")

# Filter by error type
all_types = ["All"] + summary_df["error_type"].tolist()
selected_type = st.selectbox("Filter by error type", all_types)

VISUAL_TRACE_URL = (
    "http://localhost/healthconnect/csp/healthshare/healthcareinterop/"
    "EnsPortal.VisualTrace.zen?SESSIONID={session_id}"
)

display_df = msg_df[["MessageId", "SessionId", "TimeLogged", "error_count", "error_list"]].copy()
display_df["MessageId"] = display_df["SessionId"].apply(
    lambda sid: VISUAL_TRACE_URL.format(session_id=sid)
)
if selected_type != "All":
    display_df = display_df[
        msg_df["errors"].apply(lambda errs: selected_type in errs)
    ]

import re as _re

def _build_table(df):
    rows_html = ""
    for _, r in df.iterrows():
        msg_id = _re.search(r"(\d+)$", r["MessageId"])
        mid = msg_id.group(1) if msg_id else r["MessageId"]
        url = r["MessageId"]
        rows_html += (
            f"<tr>"
            f"<td style='white-space:nowrap'><a href='{url}' target='_blank'>{mid}</a></td>"
            f"<td style='text-align:center'>{r['error_count']}</td>"
            f"<td style='white-space:nowrap'>{r['TimeLogged']}</td>"
            f"<td>{r['error_list']}</td>"
            f"</tr>"
        )
    return (
        "<table style='width:100%; border-collapse:collapse; font-size:0.95em'>"
        "<thead><tr style='border-bottom:2px solid #ddd; text-align:left'>"
        "<th style='padding:6px 8px'>Msg ID</th>"
        "<th style='padding:6px 8px; text-align:center'>Errors</th>"
        "<th style='padding:6px 8px'>Time Logged</th>"
        "<th style='padding:6px 8px'>Error Details</th>"
        "</tr></thead><tbody style='border-top:1px solid #eee'>"
        + rows_html
        + "</tbody></table>"
    )

st.markdown(_build_table(display_df), unsafe_allow_html=True)
