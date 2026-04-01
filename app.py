"""
app.py
------
Streamlit UI for the Assignment DDR Pipeline.

Upload an Inspection PDF and a Thermal PDF, enter your Gemini API key,
click Generate — and view the structured report inline with a PDF download.
"""

from __future__ import annotations

import sys
import os
import tempfile
from pathlib import Path
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv

# ── Load .env (Gemini API key, model defaults) ──────────────────────────────
load_dotenv()

# ── Ensure project root on sys.path ──────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from parser.pdf_parser import parse_pdf
from llm.extractor import extract_ddr
from generator.report_generator import render_html, render_pdf

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Assignment — DDR Generator",
    page_icon="🏗",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS injection ──────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Outfit:wght@500;700;900&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    h1, h2, h3 {
        font-family: 'Outfit', sans-serif !important;
        background: -webkit-linear-gradient(45deg, #f0c020, #ff6b6b);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 800 !important;
    }

    [data-testid="stAppViewContainer"] {
        background: radial-gradient(circle at top right, #1e1e2f, #0f172a 100%);
    }

    [data-testid="stSidebar"] {
        background: rgba(15, 23, 42, 0.55) !important;
        backdrop-filter: blur(16px) !important;
        -webkit-backdrop-filter: blur(16px) !important;
        border-right: 1px solid rgba(255,255,255,0.06);
    }
    [data-testid="stSidebar"] * { color: #e2e8f0 !important; }

    .stTextInput>div>div>input, .stSelectbox>div>div>div {
        background: rgba(255,255,255,0.05) !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
        color: #fff !important;
        border-radius: 8px;
    }

    [data-testid="stFileUploadDropzone"] {
        background: rgba(255,255,255,0.02) !important;
        border: 2px dashed rgba(255,255,255,0.15) !important;
        border-radius: 12px !important;
        transition: all 0.3s ease !important;
    }
    [data-testid="stFileUploadDropzone"]:hover {
        border-color: #f0c020 !important;
        background: rgba(240,192,32,0.04) !important;
        transform: translateY(-2px);
    }

    .stButton > button {
        background: linear-gradient(135deg, #f0c020, #e06000) !important;
        color: #111 !important;
        border: none !important;
        border-radius: 12px !important;
        font-weight: 800 !important;
        padding: 0.8rem 2.4rem !important;
        font-size: 1.1rem !important;
        width: 100% !important;
        letter-spacing: 1px;
        text-transform: uppercase;
        box-shadow: 0 4px 15px rgba(240,192,32,0.3) !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    }
    .stButton > button:hover {
        transform: translateY(-3px) scale(1.02) !important;
        box-shadow: 0 8px 25px rgba(240,192,32,0.5) !important;
    }
    .stButton > button:active { transform: translateY(1px) scale(0.98) !important; }

    .stDownloadButton > button {
        background: rgba(255,255,255,0.05) !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
        color: #fff !important;
        border-radius: 12px !important;
        font-weight: 600 !important;
        transition: all 0.2s ease !important;
    }
    .stDownloadButton > button:hover {
        background: rgba(255,255,255,0.1) !important;
        transform: translateY(-2px);
    }

    .stAlert {
        border-radius: 12px !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
        background: rgba(255,255,255,0.03) !important;
        color: #e2e8f0 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Sidebar — configuration ───────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
        <div style='padding:12px 0 20px;'>
            <div style='font-family:Outfit,sans-serif;font-size:26px;font-weight:900;
                        background:-webkit-linear-gradient(45deg,#f0c020,#ff6b6b);
                        -webkit-background-clip:text;-webkit-text-fill-color:transparent;
                        margin-bottom:4px;'>DDR ▸ AI</div>
            <div style='color:#64748b;font-size:11px;letter-spacing:1px;text-transform:uppercase;'>
                Detailed Diagnostic Report Generator
            </div>
        </div>
    """, unsafe_allow_html=True)
    st.markdown("---")

    api_key = st.text_input(
        "🔑 Gemini API Key",
        value=os.environ.get("GEMINI_API_KEY", ""),
        type="password",
        help="Google Gemini API key. Get a free key at https://aistudio.google.com",
    )

    model = st.selectbox(
        "🤖 Model",
        options=[
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            "gemini-2.0-pro-exp",
            "gemini-1.5-pro",
            "gemini-1.5-flash",
            "gemini-1.5-flash-8b",
        ],
        index=0,
        help="gemini-2.0-flash is the best balance of speed and reasoning. Use flash-lite for extreme speed.",
    )

    st.markdown("---")

    use_checkpoint = st.checkbox(
        "⏩ Load from Checkpoint",
        value=False,
        help="Skip API extraction and load a previously saved analysis instead.",
    )

    selected_ckpt_path = None
    if use_checkpoint:
        ckpt_dir = Path(".cache/checkpoints")
        if ckpt_dir.exists():
            old_ckpt = Path(".cache/ddr_checkpoint.json")
            if old_ckpt.exists():
                old_ckpt.rename(ckpt_dir / "DDR_Checkpoint_legacy.json")

            ckpts = list(ckpt_dir.glob("*.json"))
            if ckpts:
                ckpts.sort(key=os.path.getmtime, reverse=True)
                ckpt_names = [c.name for c in ckpts]

                def format_ckpt(name: str) -> str:
                    clean = name.replace("DDR_Checkpoint_", "").replace(".json", "")
                    if clean == "legacy":
                        return "Legacy Checkpoint"
                    try:
                        dt = datetime.strptime(clean, "%Y%m%d_%H%M%S")
                        return dt.strftime("%B %d, %Y — %I:%M %p")
                    except ValueError:
                        return name

                selected_name = st.selectbox("📂 Select Checkpoint", options=ckpt_names, format_func=format_ckpt)
                selected_ckpt_path = ckpt_dir / selected_name
            else:
                st.warning("No checkpoints found in `.cache/checkpoints`.")
        else:
            old_ckpt = Path(".cache/ddr_checkpoint.json")
            if old_ckpt.exists():
                ckpt_dir.mkdir(parents=True)
                old_ckpt.rename(ckpt_dir / "DDR_Checkpoint_legacy.json")
                st.rerun()
            else:
                st.warning("No checkpoints directory found.")

    st.markdown("---")
    st.markdown("""
        <div style='color:#475569;font-size:11px;line-height:1.9;'>
            Powered by <b style='color:#f0c020;'>Google Gemini</b><br>
            Upload both PDFs → click Generate.
        </div>
    """, unsafe_allow_html=True)

# ── Main area ─────────────────────────────────────────────────────────────────
st.markdown("""
    <div style='padding:2rem 0 1rem;'>
        <h1 style='font-size:2.6rem;margin-bottom:0.4rem;'>Detailed Diagnostic Report Generator</h1>
        <p style='color:#94a3b8;font-size:1rem;max-width:680px;line-height:1.7;margin:0;'>
            Upload an <b style='color:#f0c020;'>Inspection Report</b> and a
            <b style='color:#f0c020;'>Thermal Report</b> PDF.
            The AI pipeline will merge, validate, and generate a complete structured DDR.
        </p>
    </div>
""", unsafe_allow_html=True)

# Quick stats cards
c1, c2, c3 = st.columns(3)
card_style = "background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);border-radius:12px;padding:18px 20px;"
label_style = "color:#64748b;font-size:11px;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;"
value_style = "color:#f0c020;font-size:2rem;font-weight:800;font-family:Outfit,sans-serif;"

with c1:
    st.markdown(f"<div style='{card_style}'><div style='{label_style}'>DDR Sections</div><div style='{value_style}'>7</div></div>", unsafe_allow_html=True)
with c2:
    st.markdown(f"<div style='{card_style}'><div style='{label_style}'>Source Documents</div><div style='{value_style}'>2</div></div>", unsafe_allow_html=True)
with c3:
    st.markdown(f"<div style='{card_style}'><div style='{label_style}'>AI Engine</div><div style='color:#f0c020;font-size:1.3rem;font-weight:800;font-family:Outfit,sans-serif;'>Gemini</div></div>", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

col1, col2 = st.columns(2)
with col1:
    inspection_file = st.file_uploader(
        "📋 Inspection Report (PDF)",
        type=["pdf"],
        key="inspection_upload",
        help="The site observation / visual inspection PDF.",
    )
with col2:
    thermal_file = st.file_uploader(
        "🌡 Thermal Report (PDF)",
        type=["pdf"],
        key="thermal_upload",
        help="The thermal imaging / temperature reading PDF.",
    )

st.markdown("---")
generate_btn = st.button("⚡ Generate Report", use_container_width=False)

# ── Pipeline ──────────────────────────────────────────────────────────────────
if generate_btn:
    errors = []
    if not inspection_file:
        errors.append("Please upload the **Inspection Report** PDF.")
    if not thermal_file:
        errors.append("Please upload the **Thermal Report** PDF.")
    if not api_key:
        errors.append("Please enter your **Gemini API Key** in the sidebar.")
    if errors:
        for err in errors:
            st.error(err)
        st.stop()

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)

        inspection_path = tmp / "inspection.pdf"
        thermal_path = tmp / "thermal.pdf"
        inspection_path.write_bytes(inspection_file.read())
        thermal_path.write_bytes(thermal_file.read())

        # ── Node 1: Parse PDFs ────────────────────────────────────────────────
        with st.status("📄 Parsing PDFs and extracting images…", expanded=True) as status:
            try:
                inspection_doc = parse_pdf(str(inspection_path), "inspection")
                thermal_doc = parse_pdf(str(thermal_path), "thermal")

                # Token & Cost Estimation
                input_chars = len(inspection_doc.full_text) + len(thermal_doc.full_text)
                input_tokens_est = input_chars // 4
                output_tokens_est = 2500
                total_tokens_est = input_tokens_est + output_tokens_est

                prices = {
                    "gemini-2.0-flash": {"in": 0.10, "out": 0.40},
                    "gemini-2.0-flash-lite": {"in": 0.075, "out": 0.30},
                    "gemini-2.0-pro-exp": {"in": 1.25, "out": 5.00},
                    "gemini-1.5-pro": {"in": 1.25, "out": 5.00},
                    "gemini-1.5-flash": {"in": 0.075, "out": 0.30},
                    "gemini-1.5-flash-8b": {"in": 0.0375, "out": 0.15},
                }

                rates = prices.get(model, {"in": 0.10, "out": 0.40})
                est_cost = (input_tokens_est / 1_000_000) * rates["in"] + (output_tokens_est / 1_000_000) * rates["out"]

                st.info(
                    f"📊 **Estimation for {model}:** ~{total_tokens_est:,} total tokens "
                    f"({input_tokens_est:,} in / {output_tokens_est:,} out). "
                    f"Estimated API Cost: **${est_cost:.5f}**"
                )

                st.write(
                    f"✅ Inspection: {inspection_doc.full_text[:80].strip()!r}…  |  "
                    f"{len(inspection_doc.images)} image(s)"
                )
                st.write(
                    f"✅ Thermal: {thermal_doc.full_text[:80].strip()!r}…  |  "
                    f"{len(thermal_doc.images)} image(s)"
                )
                status.update(label="PDFs parsed successfully.", state="complete")
            except Exception as exc:
                status.update(label="PDF parsing failed.", state="error")
                st.error(f"Error during PDF parsing: {exc}")
                st.stop()

        # ── Checkpointing / LLM extraction ───────────────────────────────────
        ddr = None

        if use_checkpoint and selected_ckpt_path and selected_ckpt_path.exists():
            with st.status("📦 Loading AI extraction from checkpoint…", expanded=True) as status:
                try:
                    import json
                    from schemas.ddr_schema import DDROutput
                    data = json.loads(selected_ckpt_path.read_text(encoding="utf-8"))
                    ddr = DDROutput.model_validate(data)
                    status.update(label=f"Loaded from checkpoint — {len(ddr.area_wise_observations)} area(s).", state="complete")
                except Exception as exc:
                    status.update(label="Failed to load checkpoint.", state="error")
                    st.warning(f"Could not load checkpoint: {exc}")
                    ddr = None

        if not ddr:
            with st.status("🤖 Analysing documents with AI…", expanded=True) as status:
                try:
                    ddr = extract_ddr(
                        inspection_doc=inspection_doc,
                        thermal_doc=thermal_doc,
                        api_key=api_key,
                        model=model,
                    )

                    ckpt_dir = Path(".cache/checkpoints")
                    ckpt_dir.mkdir(parents=True, exist_ok=True)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    new_ckpt = ckpt_dir / f"DDR_Checkpoint_{timestamp}.json"
                    new_ckpt.write_text(ddr.model_dump_json(indent=2), encoding="utf-8")

                    area_count = len(ddr.area_wise_observations)
                    status.update(
                        label=f"AI analysis complete — {area_count} area(s) identified (Saved to checkpoint).",
                        state="complete",
                    )
                except Exception as exc:
                    status.update(label="AI analysis failed.", state="error")
                    st.error(f"Error during LLM extraction: {exc}")
                    st.stop()

        # ── Node 3: Render report ─────────────────────────────────────────────
        with st.status("📝 Generating report…", expanded=False) as status:
            try:
                today = datetime.now().strftime("%d %B %Y")
                html_output = render_html(ddr, today)
                status.update(label="Report generated.", state="complete")
            except Exception as exc:
                status.update(label="Report generation failed.", state="error")
                st.error(f"Error generating report: {exc}")
                st.stop()

        # Try PDF separately so failures are clearly surfaced
        pdf_bytes = None
        has_pdf = False
        with st.status("🖨 Rendering PDF…", expanded=False) as pdf_status:
            try:
                pdf_bytes = render_pdf(ddr, today)
                has_pdf = True
                pdf_status.update(label="PDF ready.", state="complete")
            except Exception as exc:
                pdf_status.update(label=f"PDF rendering failed: {exc}", state="error")
                st.warning(f"⚠️ PDF could not be generated: `{exc}`. HTML download is still available.")

    # ── Display the report ────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 📑 Generated Report")

    dl_col1, dl_col2 = st.columns(2)
    with dl_col1:
        st.download_button(
            label="⬇ Download HTML Report",
            data=html_output.encode("utf-8"),
            file_name=f"DDR_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html",
            mime="text/html",
        )
    with dl_col2:
        if has_pdf and pdf_bytes:
            st.download_button(
                label="⬇ Download PDF Report",
                data=pdf_bytes,
                file_name=f"DDR_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                mime="application/pdf",
            )
        else:
            st.info("PDF download unavailable. Use HTML download above.")

    import base64
    b64 = base64.b64encode(html_output.encode()).decode()
    src = f"data:text/html;base64,{b64}"
    st.markdown(
        f'<iframe src="{src}" width="100%" height="1000px" style="border:none;border-radius:10px;"></iframe>',
        unsafe_allow_html=True,
    )
