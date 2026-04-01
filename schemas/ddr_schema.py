"""
schemas/ddr_schema.py
----------------------
Pydantic v2 models matching the Assignment DDR structure as per the Main DDR.pdf reference.

Sections:
  1. Property Issue Summary  (executive summary)
  2. Area-wise Observations  (negative side / positive side per area, with images)
  3. Probable Root Cause
  4. Severity Assessment      (with reasoning)
  5. Recommended Actions
  6. Additional Notes
  7. Missing or Unclear Information
  + Conflicts (between inspection & thermal)
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ── Sub-models ────────────────────────────────────────────────────────────────

class FieldCriteria(BaseModel):
    """A generic dynamic input field/checklist criteria for an area."""
    question: str = Field(
        description="The criteria question or param, e.g., 'Condition of leakage at adjacent walls:'"
    )
    options: list[str] = Field(
        description="The available multiple-choice options, e.g., ['No leakage', 'Dampness', 'Seepage']"
    )
    selected_option: str = Field(
        description="The option from the list that was selected/marked."
    )

class ConditionTableRow(BaseModel):
    """A generic Good/Moderate/Poor observation matrix row."""
    parameter: str = Field(
        description="The physical component, e.g., 'Condition of cracks observed on RCC'"
    )
    good: bool = Field(description="True if condition is identified as Good.")
    moderate: bool = Field(description="True if condition is identified as Moderate.")
    poor: bool = Field(description="True if condition is identified as Poor.")
    remarks: str = Field(
        description="Any specific remarks noted for this condition. 'Not Available' if none."
    )


class AreaObservation(BaseModel):
    """
    Observations for a single area, split into negative side
    (where damage is visible) and positive side (source/exposure area),
    matching Assignment's negative-side / positive-side inspection model.
    """

    area_name: str = Field(
        description="Short, client-friendly name of the area (e.g. 'Hall Ceiling', 'Master Bedroom – 1st Floor', 'External Wall')."
    )
    negative_side_observations: list[str] = Field(
        description=(
            "Observations on the NEGATIVE (damaged/impacted) side. "
            "Each item is one clear sentence. Do NOT invent. Write ['Not Available'] if none."
        )
    )
    positive_side_observations: list[str] = Field(
        default_factory=list,
        description=(
            "Observations on the POSITIVE (source/exposure) side — where the leak, crack, or issue originates. "
            "Write ['Not Available'] if not identifiable."
        )
    )
    image_paths: list[str] = Field(
        default_factory=list,
        description=(
            "Absolute file paths of images relevant to this area from the extracted image list. "
            "Use ONLY paths provided in the image metadata. Leave empty if none apply."
        ),
    )
    data_source: Literal["inspection", "thermal", "both", "Not Available"] = Field(
        description="Which report(s) this observation is derived from."
    )
    field_criteria: list[FieldCriteria] = Field(
        default_factory=list,
        description="List of dynamic survey checklist questions/inputs for this area."
    )
    condition_tables: list[ConditionTableRow] = Field(
        default_factory=list,
        description="Rows depicting structural conditions matrices (Good/Moderate/Poor) for this area."
    )


class SeverityItem(BaseModel):
    """Severity rating for a specific area or issue."""

    area: str = Field(description="The area or issue being rated.")
    severity: Literal["Low", "Medium", "Moderate", "High", "Severe", "Critical"] = Field(
        description=(
            "Low = cosmetic. "
            "Medium = requires attention within 3–6 months. "
            "High = significant damage, act soon. "
            "Critical = immediate safety risk or structural failure."
        )
    )
    reasoning: str = Field(
        description="One or two plain-English sentences explaining the rating."
    )


class SummaryTableRow(BaseModel):
    """One row of the negative ↔ positive side summary table."""

    point_no: str = Field(description="Row identifier, e.g. '1', '2'.")
    impacted_area_negative_side: str = Field(
        description="Brief description of damage on the negative (impacted) side."
    )
    exposed_area_positive_side: str = Field(
        description="Brief description of the source/exposure on the positive side."
    )


class ConflictNote(BaseModel):
    """Records a conflict found between the Inspection and Thermal reports."""

    topic: str = Field(description="The area or measurement where conflict was found.")
    inspection_says: str = Field(description="What the Inspection report states.")
    thermal_says: str = Field(description="What the Thermal report states.")


# ── Root DDR output model ─────────────────────────────────────────────────────


class DDROutput(BaseModel):
    """
    Complete Detailed Diagnostic Report matching Assignment DDR format.
    """

    property_issue_summary: str = Field(
        description=(
            "2–4 sentence executive summary of the property's overall condition "
            "in plain English for a non-technical client. No jargon. "
            "Write 'Not Available' if insufficient data."
        )
    )

    area_wise_observations: list[AreaObservation] = Field(
        description=(
            "One entry per distinct area. Merge information from both reports for the same area. "
            "Do NOT duplicate observations. Split into negative side and positive side."
        )
    )

    summary_table: list[SummaryTableRow] = Field(
        default_factory=list,
        description=(
            "A paired summary table mapping each impacted (negative side) area "
            "to its corresponding source (positive side) area. "
            "Mirror the area_wise_observations list."
        )
    )

    probable_root_cause: str = Field(
        description=(
            "Explanation of the most likely underlying cause(s) of the issues. "
            "Plain English. Write 'Not Available' if cannot be determined."
        )
    )

    severity_assessment: list[SeverityItem] = Field(
        description="Severity rating per area or issue."
    )

    recommended_actions: list[str] = Field(
        description=(
            "Ordered list of recommended actions from most to least urgent. "
            "Each item is a clear, actionable instruction in plain English."
        )
    )

    additional_notes: str = Field(
        description=(
            "Any further context not covered above. "
            "Write 'Not Available' if nothing applies."
        )
    )

    missing_or_unclear_info: str = Field(
        description=(
            "Anything missing, ambiguous, or requiring follow-up. "
            "Write 'Not Available' if everything was clear."
        )
    )

    conflicts: list[ConflictNote] = Field(
        default_factory=list,
        description=(
            "Document any contradictions between the two reports. "
            "Leave empty if there are none."
        ),
    )
