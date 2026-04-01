"""
parser/image_tagger.py
----------------------
Attaches contextual metadata (surrounding text) to each ImageMeta object.

Strategy:
  - For each image, look at the text on the same page (± a window of chars)
    to infer what area or observation the image depicts.
  - This context is later forwarded to the LLM so it can map images to the
    correct AreaObservation section without hallucinating.
"""

from __future__ import annotations

from .pdf_parser import ImageMeta, ParsedDocument

# Characters of page text to include before/after an image's position
CONTEXT_WINDOW = 400


def tag_images(doc: ParsedDocument) -> ParsedDocument:
    """
    Enrich each ImageMeta in `doc` with surrounding_text drawn from the
    page text.  Since PyMuPDF gives us (page_number, image_index) but not a
    character offset, we use a heuristic:

      - Images are ordered top-to-bottom on the page.
      - We partition the page text equally among all images on that page and
        assign a slice to each image.
      - If only one image exists on the page, the whole page text is the context.

    This is intentionally simple and generalisable — no assumptions about
    specific document structure are made.

    Args:
        doc: ParsedDocument returned by parse_pdf (images may have empty surrounding_text)

    Returns:
        The same ParsedDocument with surrounding_text filled in for every ImageMeta.
    """
    # Group images by page
    pages_with_images: dict[int, list[ImageMeta]] = {}
    for img in doc.images:
        pages_with_images.setdefault(img.page_number, []).append(img)

    for page_num, imgs in pages_with_images.items():
        page_text = doc.page_texts.get(page_num, "")
        n = len(imgs)

        if n == 0 or not page_text:
            continue

        if len(page_text) <= 1500:
            # If the page doesn't have much text, give all images the full text
            # This is common for thermal/photo appendix pages.
            for img in imgs:
                img.surrounding_text = page_text.strip()
        else:
            # Divide page text into n roughly-equal slices
            chunk_size = len(page_text) // n
            
            for i, img in enumerate(imgs):
                start = i * chunk_size
                end = start + chunk_size
                
                # Expand the slice by Context Window on both sides
                c_start = max(0, start - CONTEXT_WINDOW)
                c_end = min(len(page_text), end + CONTEXT_WINDOW)
                img.surrounding_text = page_text[c_start : c_end].strip()

    return doc


def build_image_context_list(inspection: ParsedDocument, thermal: ParsedDocument) -> list[dict]:
    """
    Produce a flat list of image context dicts suitable for inclusion in an
    LLM prompt.  Each dict describes one image with enough detail for the
    model to decide which AreaObservation it belongs to.

    Args:
        inspection: Tagged ParsedDocument for the inspection report.
        thermal:    Tagged ParsedDocument for the thermal report.

    Returns:
        List of dicts, each with keys:
            path, report_type, page_number, image_index, surrounding_text
    """
    result = []
    for img in inspection.images + thermal.images:
        result.append(
            {
                "path": img.path,
                "report_type": img.report_type,
                "page_number": img.page_number,
                "image_index": img.image_index,
                "surrounding_text": img.surrounding_text,
            }
        )
    return result
