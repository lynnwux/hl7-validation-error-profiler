# HL7 Validation Error Profiler – Project Specification

## Goal

Build a lightweight application that reads an exported CSV error log generated from HL7 message validation (InterSystems HealthConnect/Ensemble) and produces an intuitive summary dashboard showing error statistics across a batch of messages (typically ~100).

The application should help quickly answer:

* How many messages were analyzed?
* What types of validation failures occurred?
* How frequently did each error occur?
* Which messages contain which errors?

The target user is an interoperability engineer onboarding a new HL7 source system and needing rapid quality assessment of sample messages.

---

## Input Data

### Source File

CSV file exported from the HL7 validation process (InterSystems HealthConnect Event Log).

Default sample file: `exportQueryN.csv`

### Key CSV Columns

| Column      | Description                                    |
| ----------- | ---------------------------------------------- |
| MessageId   | Unique message identifier                      |
| SessionId   | Session identifier (used for Visual Trace URL) |
| ConfigName  | Source component name (filter to `router_Router`) |
| TimeLogged  | Timestamp of the log entry                     |
| Text        | Raw validation error text                      |

### Error Text Format

Multiple errors in the same message are separated by `+` (with optional newlines: `\n+\n`).

The first error often has a preamble: `"Not forwarding message ... because of validation failure: ERROR ..."` which is stripped during parsing.

Only `router_Router` rows are used; `FromHL7Service` dispatch errors are ignored.

---

## Error Normalization

Errors are categorized via regex pattern matching into friendly labels:

| Pattern                                  | Normalized Label                          |
| ---------------------------------------- | ----------------------------------------- |
| `Missing field 18.*PID`                  | Missing Patient Account Number (PID-18)   |
| `Missing required PV1 element`           | Missing Segment (PV1)                     |
| `Invalid value.*PID.*field 8`            | Invalid Administrative Sex (PID-8)        |
| `Invalid date/time value.*MSH.*field 7`  | Invalid Timestamp (MSH-7)                 |
| `Invalid date/time value.*EVN.*field 2`  | Invalid Timestamp (EVN-2)                 |
| `Unescaped separator`                    | Unescaped Separator(s) Found (DG1-3)      |
| `Component data structure`               | Unescaped Separator(s) Found (DG1-3)      |

Note: "Unescaped separator" and "Component data structure" errors map to the same label — they share the same root cause (unescaped `&` in DG1-3 values like `bark &bite`).

Errors are deduplicated within each message after normalization.

---

## Technology Stack

| Component        | Technology                                |
| ---------------- | ----------------------------------------- |
| Language         | Python 3.12                               |
| Web framework    | Streamlit                                 |
| Data processing  | Pandas                                    |
| Charts           | Plotly Express                            |
| PDF HTML gen     | OpenAI GPT-4o API                         |
| PDF rendering    | Playwright (headless Chromium)            |
| Environment      | python-dotenv (`.env` for API keys)       |

### Dependencies (`requirements.txt`)

```
streamlit>=1.30.0
pandas>=2.0.0
plotly>=5.18.0
openai>=1.0.0
playwright>=1.40.0
python-dotenv>=1.0.0
```

### Running

```
streamlit run app.py
```

---

## Files

| File              | Purpose                                              |
| ----------------- | ---------------------------------------------------- |
| `app.py`          | Main Streamlit application (UI, parsing, PDF export)  |
| `html_to_pdf.py`  | Standalone subprocess script for HTML-to-PDF via Playwright |
| `.env`            | OpenAI API key storage                               |
| `exportQueryN.csv`| Default sample CSV (100 rows, 88 router_Router rows) |
| `project.md`      | This specification                                   |

---

## User Interface

### Branding

* InterSystems Teal: `#00B2A9`
* InterSystems Navy: `#002B5C`

### Sidebar

* **CSV upload**: Drag-and-drop or browse; defaults to `exportQueryN.csv`
* **PDF export** (rendered as `@st.fragment` to avoid graying out the main page):
  - Text input: "Who is the report for?" (organization name)
  - "Generate PDF Report" button (only appears when org name is entered)
  - "Download PDF Report" button (appears after generation completes)

### Header Section (compact layout)

Left column (3/4 width):
* `st.metric` showing Total Messages Analyzed
* High-frequency warning banners (amber) for errors appearing in >50% of messages
* **Error Summary**: 3-column layout showing each error type with percentage in gray text, percentages in bold navy

Right column (1/4 width):
* Donut/ring chart showing errors-per-message distribution (1 error, 2 errors, etc.)

### Error Distribution Chart

* Plotly bar chart with InterSystems navy-to-teal gradient
* Large percentage labels above bars (20px font)
* X-axis: error type, Y-axis: message count

### Message Details Table

* Custom HTML table for column width control
* Columns: Msg ID (hyperlinked), Errors (count), Time Logged, Error Details
* **Msg ID links** to InterSystems Visual Trace:
  `http://localhost/healthconnect/csp/healthshare/healthcareinterop/EnsPortal.VisualTrace.zen?SESSIONID={session_id}`
* Filterable by error type via selectbox

---

## PDF Export Pipeline

The PDF export generates a one-page professional report (no message detail table):

1. **Build JSON spec** (`build_report_spec`): Collects title, organization, total messages, high-frequency warnings, error summary, errors-per-message distribution, and brand colors
2. **Generate HTML via OpenAI** (`generate_html_via_openai`): Sends spec to GPT-4o with styling requirements (US Letter portrait, inline CSS, brand colors, @page print rules). Cached with `@st.cache_data`
3. **Convert to PDF** (`html_to_pdf`): Runs `html_to_pdf.py` as a subprocess (avoids Playwright sync API conflict with Streamlit's async event loop). Cached with `@st.cache_data`

The subprocess (`html_to_pdf.py`) reads HTML from stdin, renders via Playwright headless Chromium, and writes PDF bytes to stdout. Uses Letter format with 0.4in top/bottom and 0.5in left/right margins.

### PDF Content
- Title, organization name, total messages analyzed
- High-frequency warnings (amber/orange styled)
- Error summary table with CSS-based horizontal bar chart
- Errors-per-message distribution summary
- Footer: "© {current year} Indiana Health Information Exchange. All rights reserved."

### PDF UX
- Sidebar export section is wrapped in `@st.fragment` so PDF generation does not gray out the main dashboard
- User must enter an organization name before the "Generate PDF Report" button appears
- A spinner shows progress during generation; after completion, a "Download PDF Report" button appears
- Both `generate_html_via_openai` and `html_to_pdf` are cached with `@st.cache_data` — repeated exports with the same data/org are instant

PDF filename format: `HL7_Validation_Report_{OrgName}.pdf`

---

## Special Highlight Logic

The dashboard automatically highlights high-frequency errors (>50% of messages) with an amber/orange warning banner:

> "High frequency issue detected: Missing Patient Account Number (PID-18) appears in 94.0% of messages (94 of 100)."

---

## Success Criteria

The tool is successful if a user can:

1. Load a CSV error log (upload or default)
2. Immediately see total messages analyzed, most common validation failures, which HL7 requirements are violated, and which messages contain which errors
3. Click through to Visual Trace for any message
4. Export a polished PDF report for a named organization

All within a single screen.
