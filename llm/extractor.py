"""
llm/extractor.py
----------------
Node 2: Structured Extraction & Logic

Uses the google-genai SDK (google.genai) with gemini-2.0-flash.
Calls Gemini with JSON output mode, then validates into DDROutput via Pydantic.
Since Gemini 2.0 has a 1 million token context window, this runs in a single fast pass.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from google import genai
from google.genai import types

from schemas.ddr_schema import DDROutput
from llm.prompts import SYSTEM_PROMPT, build_user_prompt
from parser.pdf_parser import ParsedDocument
from parser.image_tagger import tag_images, build_image_context_list

DEFAULT_MODEL = "gemini-2.0-flash"


# ── Image path validation ─────────────────────────────────────────────────────

def _validate_image_paths(ddr: DDROutput) -> DDROutput:
    """Replace any missing/invalid image path with sentinel IMAGE_NOT_AVAILABLE."""
    for area in ddr.area_wise_observations:
        validated: list[str] = []
        for p in area.image_paths:
            if p and p != "IMAGE_NOT_AVAILABLE" and Path(p).exists():
                validated.append(p)
            else:
                validated.append("IMAGE_NOT_AVAILABLE")
        area.image_paths = validated
    return ddr


# ── Main extraction function ──────────────────────────────────────────────────

def extract_ddr(
    inspection_doc: ParsedDocument,
    thermal_doc: ParsedDocument,
    api_key: str | None = None,
    model: str = DEFAULT_MODEL,
) -> DDROutput:
    """
    Full Node 2 pipeline:
      1. Tag images with context.
      2. Build prompt.
      3. Call Gemini (google-genai SDK) with JSON response type.
      4. Validate response into DDROutput.
      5. Validate image paths on disk.
    """
    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise ValueError(
            "Gemini API key not found. Set GEMINI_API_KEY in .env or enter it in the sidebar."
        )

    # Step 1: Tag images
    inspection_doc = tag_images(inspection_doc)
    thermal_doc = tag_images(thermal_doc)

    # Step 2: Build prompt (no need for extreme truncation with Gemini's 1M window)
    image_context = build_image_context_list(inspection_doc, thermal_doc)
    user_prompt = build_user_prompt(
        inspection_text=inspection_doc.full_text,
        thermal_text=thermal_doc.full_text,
        image_context_list=image_context,
    )

    # Append schema hint so Gemini knows the exact structure expected
    schema_hint = (
        "\n\nCRITICAL: You MUST return a single JSON object INSTANCE filled with actual data matching this exact structure layout. "
        "Do NOT output the raw JSON Schema strings. Return the actual extracted property data.\n"
        + json.dumps(DDROutput.model_json_schema(), indent=2)
    )
    full_prompt = f"{SYSTEM_PROMPT}\n\n{user_prompt}{schema_hint}"

    # Step 3: Call Gemini with the new google-genai SDK
    client = genai.Client(api_key=key)

    response = client.models.generate_content(
        model=model,
        contents=full_prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,
        ),
    )

    raw_text = response.text.strip()

    # Strip markdown code fences if present
    if raw_text.startswith("```"):
        parts = raw_text.split("```")
        raw_text = parts[1] if len(parts) > 1 else raw_text
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
        raw_text = raw_text.strip()

    # Step 4: Parse into Pydantic model
    try:
        data = json.loads(raw_text)
        ddr = DDROutput.model_validate(data)
    except (json.JSONDecodeError, Exception) as exc:
        raise ValueError(
            f"Gemini returned invalid JSON or schema mismatch.\n"
            f"Error: {exc}\n"
            f"Raw response (first 500 chars): {raw_text[:500]}"
        ) from exc

    # Step 5: Validate image paths
    ddr = _validate_image_paths(ddr)
    return ddr
