"""Pure page/text analysis helpers used by the pipeline orchestrator."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


def clean_markdown(text: str) -> str:
    """Remove markdown code-fence wrappers from model output."""
    normalized = (text or "").strip()
    if normalized.startswith("```"):
        lines = normalized.splitlines()
        if lines and lines[0].lstrip().startswith("```"):  # pragma: no branch
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        normalized = "\n".join(lines).strip()
    if normalized.startswith("```markdown"):  # pragma: no cover - handled by generic fence strip
        normalized = normalized.replace("```markdown\n", "", 1)
    if normalized.endswith("```"):
        normalized = normalized[:-3].strip()
    return normalized.strip()


def looks_like_atomic_markdown_line(line: str) -> bool:
    """Return whether line should be kept as-is in normalized markdown."""
    if not line:
        return True
    if line.startswith(("#", ">", "```", "|")):
        return True
    if re.match(r"^(?:[-*+]|\d+[.)])\s+", line):
        return True
    if re.match(r"^\[([ xX])\]\s+", line):
        return True
    if re.match(r"^\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?$", line):
        return True
    if len(line) <= 60 and (line.isupper() or line.endswith(":")):
        return True
    return False


def normalize_whitespace(text: str) -> str:
    """Collapse repeated whitespace and canonicalize line endings."""
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def word_count(text: str) -> int:
    """Count words with unicode support."""
    return len(re.findall(r"\b[\wÀ-ÿ]+\b", text or "", flags=re.UNICODE))


def normalize_markdown_document(text: str) -> str:
    """Normalize markdown spacing while preserving structural lines."""
    normalized = normalize_whitespace(clean_markdown(text))
    if not normalized:
        return normalized

    lines = normalized.splitlines()
    output_lines: List[str] = []
    paragraph: List[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            output_lines.append(" ".join(paragraph).strip())
            paragraph.clear()

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            if output_lines and output_lines[-1] != "":  # pragma: no branch
                output_lines.append("")
            continue

        if looks_like_atomic_markdown_line(line):
            flush_paragraph()
            output_lines.append(line)
            continue

        paragraph.append(line)

    flush_paragraph()

    compacted: List[str] = []
    previous_blank = False
    for line in output_lines:
        if not line:
            if not previous_blank:  # pragma: no branch
                compacted.append("")
            previous_blank = True
            continue
        compacted.append(line)
        previous_blank = False

    return "\n".join(compacted).strip()


def page_text_layer(page: Any) -> Tuple[str, int, int, int, int]:
    """Extract text-layer metrics from a page-like object."""
    text = page.get_text("text") or ""
    blocks = page.get_text("blocks") or []
    image_count = len(page.get_images(full=True) or [])
    block_count = sum(1 for block in blocks if len(block) > 4 and str(block[4]).strip())
    return (
        normalize_whitespace(text),
        len(text.strip()),
        word_count(text),
        block_count,
        image_count,
    )


def page_text_confidence(text_chars: int, word_count_value: int, structure_count: int) -> float:
    """Compute a bounded confidence heuristic for text-layer extraction."""
    if text_chars <= 0:
        return 0.0
    length_score = min(0.5, text_chars / 1200.0)
    word_score = min(0.2, word_count_value / 120.0)
    structure_score = min(0.2, structure_count / 40.0)
    base = 0.55 + length_score + word_score + structure_score
    return round(min(base, 0.99), 3)


def inspect_text_layer(page: Any, text_min_chars: int) -> Optional[Dict[str, Any]]:
    """Return inspection payload when a page has usable text-layer content."""
    text, text_chars, words, block_count, image_count = page_text_layer(page)
    if text_chars < text_min_chars or words < 5:
        return None

    warnings: List[str] = []
    if text_chars < 80:
        warnings.append("short_text_layer")
    if block_count == 0:
        warnings.append("low_text_structure")

    return {
        "page_index": page.number,
        "source": "text-layer",
        "text": text,
        "text_chars": text_chars,
        "word_count": words,
        "block_count": block_count,
        "image_count": image_count,
        "confidence": page_text_confidence(text_chars, words, block_count),
        "warnings": warnings,
    }
