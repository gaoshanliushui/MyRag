"""
Structural Cleaner

Noise reduction for document content:
- Table cleaning and normalization
- Header/footer detection and removal
- Formula preservation
- Whitespace normalization
- Special character handling
"""

import re
from typing import Any

from app.utils.logging import get_logger

logger = get_logger("core.preprocessing.cleaner")


class StructuralCleaner:
    """Clean document content for better retrieval."""

    def __init__(self):
        # Common header/footer patterns
        self.header_patterns = [
            r"^Page \d+$",
            r"^第\s*\d+\s*页$",
            r"^\d+\s*/\s*\d+$",
            r"^\d{4}-\d{2}-\d{2}",  # Date patterns
            r"^Copyright",
            r"^版权",
        ]

        # Common noise patterns
        self.noise_patterns = [
            r"\[\d+\]",  # Reference markers [1], [2]
            r"\(见图\s*\d+\)",  # Figure references
            r"\(见表\s*\d+\)",  # Table references
        ]

    def clean_content(self, content: str, content_type: str = "text") -> str:
        """
        Clean content based on type.

        Args:
            content: Raw content
            content_type: text, table, formula, etc.

        Returns:
            Cleaned content
        """
        if content_type == "table":
            return self._clean_table(content)
        elif content_type == "formula":
            return self._clean_formula(content)
        else:
            return self._clean_text(content)

    def _clean_text(self, text: str) -> str:
        """Clean regular text content."""
        # Normalize whitespace
        text = self._normalize_whitespace(text)

        # Remove excessive newlines
        text = re.sub(r"\n{3,}", "\n\n", text)

        # Remove header/footer patterns (if short lines at start/end)
        lines = text.split("\n")
        if lines:
            # Check first line for header
            first = lines[0].strip()
            for pattern in self.header_patterns:
                if re.match(pattern, first, re.IGNORECASE):
                    lines[0] = ""
                    break

            # Check last line for footer
            last = lines[-1].strip()
            for pattern in self.header_patterns:
                if re.match(pattern, last, re.IGNORECASE):
                    lines[-1] = ""
                    break

        text = "\n".join(lines)

        # Remove standalone page numbers
        text = re.sub(r"\n\s*\d+\s*\n", "\n", text)

        # Normalize punctuation spacing
        text = re.sub(r"\s+([.,;:!?])", r"\1", text)
        text = re.sub(r"([.,;:!?])([^\s\d])", r"\1 \2", text)

        # Remove control characters except newlines
        text = re.sub(r"[^\x20-\x7E\n\r一-鿿]", "", text)

        return text.strip()

    def _clean_table(self, table_text: str) -> str:
        """Clean table content."""
        # Normalize table separators
        table_text = re.sub(r"\|+", "|", table_text)

        # Remove empty cells
        table_text = re.sub(r"\|\s*\|", "|", table_text)

        # Normalize spacing in cells
        lines = table_text.split("\n")
        cleaned_lines = []
        for line in lines:
            # Ensure proper | separators
            if "|" in line:
                cells = [c.strip() for c in line.split("|") if c.strip()]
                cleaned_lines.append("| " + " | ".join(cells) + " |")

        return "\n".join(cleaned_lines)

    def _clean_formula(self, formula_text: str) -> str:
        """Clean formula content - preserve formatting."""
        # Remove extra whitespace but preserve formula structure
        formula_text = re.sub(r"\s+", " ", formula_text)

        # Normalize common formula patterns
        formula_text = formula_text.strip()

        return formula_text

    def _normalize_whitespace(self, text: str) -> str:
        """Normalize whitespace characters."""
        # Replace various whitespace with standard space
        text = re.sub(r"[ \t]+", " ", text)

        # Remove trailing whitespace from lines
        lines = text.split("\n")
        lines = [line.rstrip() for line in lines]

        return "\n".join(lines)

    def detect_header_footer(
        self,
        content: str,
        position: dict[str, Any] | None = None,
    ) -> dict[str, bool]:
        """
        Detect if content is header/footer.

        Uses position info and content patterns.
        """
        result = {"is_header": False, "is_footer": False}

        if not position:
            return result

        bbox = position.get("bbox", [])
        page_height = position.get("page_height", 0)

        if bbox and page_height:
            y_pos = bbox[1]  # Top y position

            # Header: top 15% of page
            if y_pos < page_height * 0.15:
                result["is_header"] = True

            # Footer: bottom 15% of page
            if y_pos > page_height * 0.85:
                result["is_footer"] = True

        # Check content patterns
        content_stripped = content.strip()
        for pattern in self.header_patterns:
            if re.match(pattern, content_stripped, re.IGNORECASE):
                result["is_header"] = True
                result["is_footer"] = True  # Could be either

        return result

    def clean_chunk(
        self,
        chunk: Any,
    ) -> Any:
        """
        Clean a SemanticChunk.

        Returns cleaned chunk (modifies in place).
        """
        chunk.content = self.clean_content(
            chunk.content,
            chunk.chunk_type
        )

        # Update metadata
        chunk.chunk_metadata["cleaned"] = True

        return chunk

    def clean_parsed_document(
        self,
        parsed_doc: Any,
    ) -> Any:
        """
        Clean all sections in parsed document.

        Removes headers/footers and normalizes content.
        """
        cleaned_sections = []

        for section in parsed_doc.sections:
            content = section["content"]
            section_type = section.get("section_type", "text")
            position = section.get("position", {})

            # Check for header/footer
            detection = self.detect_header_footer(content, position)

            # Skip headers/footers unless they have meaningful content
            if detection["is_header"] or detection["is_footer"]:
                # Keep if content is substantial (>50 chars)
                if len(content.strip()) < 50:
                    continue

            # Clean content
            cleaned_content = self.clean_content(content, section_type)

            if cleaned_content:
                section["content"] = cleaned_content
                section["metadata"] = {
                    "cleaned": True,
                    "was_header": detection["is_header"],
                    "was_footer": detection["is_footer"],
                }
                cleaned_sections.append(section)

        parsed_doc.sections = cleaned_sections

        logger.info(
            f"Cleaned {parsed_doc.filename}: "
            f"{len(cleaned_sections)} sections retained"
        )

        return parsed_doc


def get_cleaner() -> StructuralCleaner:
    """Get structural cleaner instance."""
    return StructuralCleaner()