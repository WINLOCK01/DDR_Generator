"""
generator/report_generator.py
------------------------------
Node 3: DDR Generator

Converts a DDROutput Pydantic object → rendered HTML → PDF bytes.

Two public functions:
  render_html(ddr, date)  → HTML string
  render_pdf(ddr, date)   → PDF bytes (via WeasyPrint)
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from schemas.ddr_schema import DDROutput

# ── Template path ─────────────────────────────────────────────────────────────
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


# ── Jinja2 environment setup ──────────────────────────────────────────────────

def _make_env() -> Environment:
    """Create and configure the Jinja2 environment with custom filters."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=True,
    )
    # Custom filter: extract filename from an absolute path
    env.filters["basename"] = lambda p: Path(p).name if p else ""
    return env


# ── HTML rendering ────────────────────────────────────────────────────────────

def render_html(ddr: DDROutput, generated_date: str | None = None) -> str:
    """
    Render the DDROutput into an HTML string using the Jinja2 template.

    Args:
        ddr:            Populated DDROutput model.
        generated_date: Report date string; defaults to today if not provided.

    Returns:
        Rendered HTML string.
    """
    if generated_date is None:
        generated_date = datetime.now().strftime("%d %B %Y")

    env = _make_env()
    template = env.get_template("ddr_template.html")

    return template.render(
        ddr=ddr,
        generated_date=generated_date,
    )


# ── PDF rendering ─────────────────────────────────────────────────────────────

def render_pdf(ddr: DDROutput, generated_date: str | None = None) -> bytes:
    """
    Render the DDROutput into a PDF (bytes) via Playwright CLI subprocess.

    Uses subprocess.run() to invoke the playwright CLI directly, completely
    bypassing the Python 3.14 asyncio ProactorEventLoop subprocess incompatibility
    that crashes the sync_playwright() API on Windows.
    """
    import sys
    import subprocess
    import tempfile

    html_string = render_html(ddr, generated_date)

    # Inject base tag so local images inside templates/ resolve correctly
    base_uri = TEMPLATES_DIR.as_uri() + "/"
    if "<head>" in html_string:
        html_string = html_string.replace("<head>", f'<head><base href="{base_uri}">', 1)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        html_file = tmp / "report.html"
        pdf_file = tmp / "report.pdf"

        html_file.write_text(html_string, encoding="utf-8")

        # Build a tiny inline Node/Python script that Playwright CLI can run
        script = tmp / "pw_print.js"
        script.write_text(
            f"""
const {{ chromium }} = require('playwright');
(async () => {{
    const browser = await chromium.launch({{ args: ['--no-sandbox', '--disable-gpu'] }});
    const page = await browser.newPage();
    await page.goto('file:///{html_file.as_posix()}', {{ waitUntil: 'networkidle' }});
    await page.pdf({{
        path: '{pdf_file.as_posix()}',
        format: 'A4',
        printBackground: true,
        margin: {{ top: '1cm', right: '1cm', bottom: '1cm', left: '1cm' }}
    }});
    await browser.close();
}})();
""",
            encoding="utf-8",
        )

        # Locate node executable
        node_exe = "node"

        # Locate the playwright package folder so we can resolve the require()
        try:
            import playwright as _pw_pkg
            pw_pkg_dir = Path(_pw_pkg.__file__).parent
        except Exception:
            pw_pkg_dir = None

        env = os.environ.copy()
        if pw_pkg_dir:
            node_modules = pw_pkg_dir.parent / "playwright" / "node_modules"
            if not node_modules.exists():
                # Try the venv site-packages layout
                node_modules = pw_pkg_dir / "driver" / "node_modules"
            env["NODE_PATH"] = str(node_modules)

        result = subprocess.run(
            [node_exe, str(script)],
            capture_output=True,
            timeout=120,
            env=env,
        )

        if result.returncode != 0:
            err = result.stderr.decode(errors="replace")
            # Fallback: try python-based playwright via a fresh subprocess
            # (avoids the eventloop issue by running in a brand-new process)
            py_script = tmp / "pw_print.py"
            py_script.write_text(
                f"""
import sys, pathlib
sys.path.insert(0, r'{Path(__file__).resolve().parent.parent}')
from playwright.sync_api import sync_playwright
html = pathlib.Path(r'{html_file}').read_text(encoding='utf-8')
with sync_playwright() as p:
    browser = p.chromium.launch(args=['--no-sandbox', '--disable-gpu'])
    page = browser.new_page()
    page.set_content(html, wait_until='networkidle')
    page.pdf(
        path=r'{pdf_file}',
        format='A4',
        print_background=True,
        margin={{'top':'1cm','right':'1cm','bottom':'1cm','left':'1cm'}}
    )
    browser.close()
""",
                encoding="utf-8",
            )
            result2 = subprocess.run(
                [sys.executable, str(py_script)],
                capture_output=True,
                timeout=120,
            )
            if result2.returncode != 0:
                err2 = result2.stderr.decode(errors="replace")
                raise RuntimeError(
                    f"PDF generation failed.\n"
                    f"Node attempt: {err}\n"
                    f"Python attempt: {err2}"
                )

        if not pdf_file.exists():
            raise RuntimeError("Playwright ran successfully but no PDF file was created.")

        return pdf_file.read_bytes()
