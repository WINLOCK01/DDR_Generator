"""
parser/pdf_parser.py
--------------------
Node 1: Document Ingestion & Parser

Extracts text and images from an Inspection or Thermal PDF using PyMuPDF.
Returns a ParsedDocument containing full text (with page markers) and a list
of ImageMeta objects ready for contextual tagging.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import pymupdf as fitz  # PyMuPDF — use pymupdf directly to avoid fitz namespace conflict

# ── Output directory for extracted images ────────────────────────────────────
IMAGES_DIR = Path(__file__).resolve().parent.parent / "extracted_images"


@dataclass
class ImageMeta:
    """Holds an extracted image and the textual context surrounding it."""

    path: str                          # Absolute path to saved PNG
    page_number: int                   # 1-indexed PDF page number
    image_index: int                   # Image order on the page (0-indexed)
    report_type: Literal["inspection", "thermal"]
    surrounding_text: str = ""         # Filled in by image_tagger


@dataclass
class ParsedDocument:
    """Result of parsing one PDF document."""

    report_type: Literal["inspection", "thermal"]
    full_text: str                     # Entire text with [PAGE N] markers
    images: list[ImageMeta] = field(default_factory=list)
    page_texts: dict[int, str] = field(default_factory=dict)  # page → text


def parse_pdf(pdf_path: str | Path, report_type: Literal["inspection", "thermal"]) -> ParsedDocument:
    """
    Parse a PDF and extract:
      - Full concatenated text with [PAGE N] markers
      - All embedded images saved to extracted_images/

    Args:
        pdf_path:    Absolute path to the PDF file.
        report_type: "inspection" or "thermal" — used for file naming & metadata.

    Returns:
        ParsedDocument with text and image metadata.
    """
    pdf_path = Path(pdf_path).resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(pdf_path))

    all_page_texts: dict[int, str] = {}
    all_images: list[ImageMeta] = []
    full_text_parts: list[str] = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        page_label = page_num + 1  # 1-indexed

        # ── Text extraction ──────────────────────────────────────────────────
        page_text = page.get_text("text").strip()
        all_page_texts[page_label] = page_text
        full_text_parts.append(f"[PAGE {page_label}]\n{page_text}")

        # ── Image extraction ──────────────────────────────────────────────────
        image_list = page.get_images(full=True)
        valid_images_this_page = 0
        
        for img_idx, img_info in enumerate(image_list):
            if valid_images_this_page >= 4:
                break  # Max 4 visible photos per page to ignore thermal camera 'ghost layers'
                
            xref = img_info[0]
            try:
                base_image = doc.extract_image(xref)
                
                # Filter out small graphics (e.g. header logos, tiny UI icons)
                # A real site photo will almost always be > 250px in both dimensions
                if base_image.get("width", 0) < 250 or base_image.get("height", 0) < 250:
                    continue

                img_bytes = base_image["image"]

                file_name = f"{report_type}_page{page_label}_img{img_idx}.png"
                save_path = IMAGES_DIR / file_name

                with open(save_path, "wb") as f:
                    f.write(img_bytes)

                meta = ImageMeta(
                    path=str(save_path),
                    page_number=page_label,
                    image_index=img_idx,
                    report_type=report_type,
                )
                all_images.append(meta)
                valid_images_this_page += 1

            except Exception as exc:  # noqa: BLE001
                print(f"[Parser] Warning: could not extract image xref={xref} on page {page_label}: {exc}")

    doc.close()

    return ParsedDocument(
        report_type=report_type,
        full_text="\n\n".join(full_text_parts),
        images=all_images,
        page_texts=all_page_texts,
    )
