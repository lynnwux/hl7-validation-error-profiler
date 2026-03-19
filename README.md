# HL7 Validation Error Profiler

A Streamlit dashboard for analyzing HL7 validation error logs exported from InterSystems HealthConnect/Ensemble. Designed for interoperability engineers onboarding new HL7 source systems who need rapid quality assessment of sample messages.

## Features

- **Error Parsing & Normalization**: Automatically parses and categorizes raw validation errors into friendly labels
- **Interactive Dashboard**: Total messages analyzed, error frequency breakdown, high-frequency warnings
- **Visual Trace Integration**: Message IDs link directly to InterSystems HealthConnect Visual Trace
- **Error Distribution Chart**: Plotly bar chart with InterSystems brand colors
- **Filterable Message Table**: Filter by error type to drill into specific issues
- **PDF Export** (local only): One-page professional report generated via OpenAI GPT-4o and Playwright

## Live Demo

[hl7-validation-error-profiler.streamlit.app](https://hl7-validation-error-profiler.streamlit.app)

> Note: PDF export is disabled on Streamlit Cloud due to Chromium dependencies. Run locally for full functionality.

## Quick Start

```bash
pip install -r requirements.txt
playwright install chromium
streamlit run app.py
```

Create a `.env` file with your OpenAI API key (required for PDF export):

```
OPENAI_API_KEY=sk-...
```

## Tech Stack

Python | Streamlit | Pandas | Plotly | OpenAI | Playwright
