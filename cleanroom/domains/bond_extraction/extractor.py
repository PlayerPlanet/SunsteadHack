"""Bond field extractor — deterministic value extraction from source text.

The StubExtractor is the CONTESTANT (agent under optimization). It extracts
field values from a source text (e.g., term sheet) using configurable patterns
and validation rules. Quality improves with better config (regex patterns,
validation markers). Crucially, EXTRACTED VALUES are always true spans of the
source text (never fabricated) to pass the no-fabrication check.
"""

import re


class StubExtractor:
    """Deterministic bond field extractor.

    The extractor receives a config dict that can include:
      - field_patterns: dict mapping field_name -> regex pattern
      - validation_enabled: bool, enable format validation
      - field_schema: list of field names to extract (hints for recall)

    Quality heuristics:
      1. If field_patterns[field_name] is provided, use it to search the text.
      2. If validation_enabled=True and field_schema is set, enable higher recall.
      3. Otherwise, return "" (a miss).
    """

    def extract(self, field_name: str, source_text: str, config: dict) -> str:
        """Extract a field value from source text.

        Returns a true substring of source_text (never fabricated) or "".

        Args:
            field_name: The field to extract (e.g., "coupon_rate", "isin").
            source_text: The source document text to search.
            config: Extraction config dict (field_patterns, validation_enabled, field_schema).

        Returns:
            A substring of source_text matching the field, or "".
        """
        if not source_text or not field_name:
            return ""

        field_patterns = config.get("field_patterns", {})
        validation_enabled = config.get("validation_enabled", False)
        field_schema = config.get("field_schema", [])

        # Try pattern-based extraction first.
        if field_name in field_patterns:
            pattern = field_patterns[field_name]
            match = re.search(pattern, source_text, re.IGNORECASE)
            if match:
                # Return the matched span (always a substring of source_text).
                return match.group(0)

        # If validation and field_schema are enabled, try heuristic extraction.
        if validation_enabled and field_name in field_schema:
            # Simple heuristic: look for common markers by field type.
            result = self._heuristic_extract(field_name, source_text)
            if result:
                return result

        # No extraction; return a miss.
        return ""

    @staticmethod
    def _heuristic_extract(field_name: str, source_text: str) -> str:
        """Heuristic extraction for common bond fields.

        Args:
            field_name: The field to extract.
            source_text: The source text to search.

        Returns:
            A substring or "".
        """
        patterns = {
            "isin": r"[A-Z]{2}[A-Z0-9]{9}[0-9]",
            "coupon_rate": r"\b\d+(?:\.\d+)?\s*%?\b",
            "currency": r"\b[A-Z]{3}\b",
            "maturity_date": r"\b\d{4}-\d{2}-\d{2}\b",
        }

        if field_name in patterns:
            match = re.search(patterns[field_name], source_text)
            if match:
                return match.group(0)

        return ""
