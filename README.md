# UrbanRoof — DDR Pipeline

An AI-powered pipeline that converts technical PDF inspection reports into structured, client-ready **Detailed Diagnostic Reports (DDR)**.

## Architecture

```
PDF Inspection Report  ┐
                       ├──► Node 1: Parser ──► Node 2: LLM Extractor ──► Node 3: Generator ──► DDR HTML/PDF
PDF Thermal Report     ┘         (PyMuPDF)         (GPT-4o + Pydantic)        (Jinja2 + WeasyPrint)
```

## Project Structure

```
urbanroof/
├── app.py                    # Streamlit UI
├── requirements.txt
├── .env.example
├── parser/
│   ├── pdf_parser.py         # Text + image extraction
│   └── image_tagger.py       # Context tagging for images
├── schemas/
│   └── ddr_schema.py         # Pydantic v2 DDR models
├── llm/
│   ├── extractor.py          # GPT-4o structured output call
│   └── prompts.py            # Prompt templates
├── generator/
│   └── report_generator.py   # Jinja2 → HTML/PDF
├── templates/
│   └── ddr_template.html     # Report HTML template
├── extracted_images/         # Auto-created at runtime
└── tests/
    └── test_pdf_parser.py    # Smoke tests
```

## DDR Output Sections

1. Property Issue Summary
2. Area-wise Observations (with embedded images)
3. Probable Root Cause
4. Severity Assessment
5. Recommended Actions
6. Additional Notes
7. Missing or Unclear Information

## Quick Start

### 1. Install Dependencies

```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

> **WeasyPrint on Windows**: requires GTK runtime. Download from [GTK for Windows](https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer). If you skip this, the app still works — PDF export will be unavailable but HTML export works fine.

### 2. Set API Key

```bash
copy .env.example .env
# Edit .env and set OPENAI_API_KEY=sk-...
```

Or enter it directly in the Streamlit sidebar.

### 3. Run the App

```bash
streamlit run app.py
```

Open `http://localhost:8501`, upload both PDFs, click **Generate Report**.

### 4. Run Tests

```bash
python -m pytest tests/ -v
```

## Logic Rules

| Rule | Behaviour |
|------|-----------|
| Missing data | Writes `"Not Available"` |
| Missing image | Renders `"Image Not Available"` badge |
| Duplicate observations | Deduplicated by LLM instruction |
| Conflicting reports | Captured in `conflicts[]` section |
| Invented facts | Prevented by strict system prompt |

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | — | Required — your OpenAI key |
| `OPENAI_MODEL` | `gpt-4o` | Model to use (also in UI) |
