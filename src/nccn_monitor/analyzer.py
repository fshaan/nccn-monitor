"""Extract update notes from PDF and generate AI-powered change summaries."""

import logging
from pathlib import Path

from pypdf import PdfReader

logger = logging.getLogger(__name__)


def extract_update_notes(pdf_path: str | Path, max_pages: int = 5) -> str:
    """Extract text from the first N pages of a guideline PDF.

    NCCN guideline PDFs typically include update notes / summary of changes
    in the first few pages before the clinical content begins.

    Args:
        pdf_path: Path to the downloaded PDF file.
        max_pages: Number of pages to extract from the beginning.

    Returns:
        Extracted text from the first N pages, or empty string on failure.
    """
    try:
        reader = PdfReader(str(pdf_path))
        pages_to_read = min(max_pages, len(reader.pages))

        text_parts: list[str] = []
        for i in range(pages_to_read):
            page_text = reader.pages[i].extract_text(extraction_mode="layout")
            if page_text:
                text_parts.append(f"--- Page {i + 1} ---\n{page_text}")

        full_text = "\n\n".join(text_parts)
        logger.info(
            "Extracted %d chars from first %d pages of %s",
            len(full_text),
            pages_to_read,
            Path(pdf_path).name,
        )
        return full_text

    except Exception as e:
        logger.error("Failed to extract PDF text from %s: %s", pdf_path, e)
        return ""


def build_summary_prompt(
    guideline_name: str,
    old_version: str,
    new_version: str,
    update_notes_text: str,
    language: str = "zh-CN",
) -> str:
    """Build the prompt for AI-powered change summary.

    This prompt is the core value of the tool — it transforms raw English
    update notes into structured, actionable intelligence in the user's
    preferred language.

    Args:
        guideline_name: Name of the guideline (e.g. "Non-Small Cell Lung Cancer").
        old_version: Previous version string.
        new_version: New version string.
        update_notes_text: Raw text extracted from PDF first pages.
        language: Output language code (default: zh-CN for Simplified Chinese).

    Returns:
        A formatted prompt string ready to send to an LLM.
    """
    # TODO: This is where YOUR domain expertise matters.
    # The prompt below is a starting point. You may want to customize:
    # - Which types of changes to prioritize (new drugs? staging changes? biomarkers?)
    # - How to structure the output (by category? by significance?)
    # - Whether to include PubMed references for cited studies
    #
    # See config.example.yaml for the `analysis.language` setting.

    lang_instruction = {
        "zh-CN": "请用简体中文输出。",
        "en": "Please respond in English.",
    }.get(language, f"Please respond in {language}.")

    return f"""You are an oncology clinical guidelines expert. Analyze the following update notes
from the NCCN {guideline_name} guideline (version change: {old_version} → {new_version}).

{lang_instruction}

## Task
1. **Key Changes Summary**: List the most clinically significant changes (new recommendations,
   removed recommendations, evidence level changes, new drugs/regimens added).
2. **Clinical Impact**: For each key change, briefly explain its potential impact on clinical practice.
3. **Notable Details**: Any other noteworthy updates (staging changes, biomarker recommendations,
   supportive care updates).

## Format
Use clear headings and bullet points. Prioritize changes by clinical significance.
If the update notes are unclear or incomplete, state what information is missing.

## Update Notes (extracted from PDF pages 1-5):
{update_notes_text}
"""
