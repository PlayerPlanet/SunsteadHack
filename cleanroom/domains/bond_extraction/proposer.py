"""Bond extraction proposer — suggests config deltas via scripted sequence or Claude.

The proposer is the only agentic part. It receives ONLY the train split (never holdout)
and the objective. It proposes config deltas (field patterns, validation flags) but can
NEVER see or alter _grader, _eval, or _loss_hash.
"""

from cleanroom.types import Candidate


class ScriptedExtractor:
    """Deterministic test proposer — cycles through a fixed sequence of config deltas.

    Used for offline curve scripts and deterministic testing. The sequence
    progressively adds field patterns and enables validation, simulating
    improved extraction quality.
    """

    def __init__(self, sequence: list = None):
        """Initialize with a sequence of config deltas.

        Args:
            sequence: List of dicts, each representing a config_delta.
                     If None, uses a default sequence that progressively
                     improves extraction by adding patterns.
        """
        self._sequence = sequence or [
            # Step 0: No patterns, no validation — baseline (poor extraction).
            {"field_patterns": {}, "validation_enabled": False, "field_schema": []},
            # Step 1: Add ISIN pattern.
            {
                "field_patterns": {"isin": r"[A-Z]{2}[A-Z0-9]{9}[0-9]"},
                "validation_enabled": False,
                "field_schema": [],
            },
            # Step 2: Add coupon_rate and currency patterns.
            {
                "field_patterns": {
                    "isin": r"[A-Z]{2}[A-Z0-9]{9}[0-9]",
                    "coupon_rate": r"\b\d+(?:\.\d+)?\s*%?\b",
                    "currency": r"\b[A-Z]{3}\b",
                },
                "validation_enabled": False,
                "field_schema": [],
            },
            # Step 3: Enable validation to improve recall.
            {
                "field_patterns": {
                    "isin": r"[A-Z]{2}[A-Z0-9]{9}[0-9]",
                    "coupon_rate": r"\b\d+(?:\.\d+)?\s*%?\b",
                    "currency": r"\b[A-Z]{3}\b",
                },
                "validation_enabled": True,
                "field_schema": ["isin", "coupon_rate", "currency", "maturity_date"],
            },
            # Step 4: Add maturity_date pattern (for future dates).
            {
                "field_patterns": {
                    "isin": r"[A-Z]{2}[A-Z0-9]{9}[0-9]",
                    "coupon_rate": r"\b\d+(?:\.\d+)?\s*%?\b",
                    "currency": r"\b[A-Z]{3}\b",
                    "maturity_date": r"\b\d{4}-\d{2}-\d{2}\b",
                },
                "validation_enabled": True,
                "field_schema": ["isin", "coupon_rate", "currency", "maturity_date"],
            },
        ]
        self._idx = 0

    def propose(self, task_spec: dict, history: list) -> Candidate:
        """Return the next config delta from the sequence.

        Args:
            task_spec: Dict with task metadata (unused in scripted mode).
            history: List of prior accepted Candidate objects (unused).

        Returns:
            Candidate with type="extractor_config", params={"config_delta": {...}}.
        """
        delta = self._sequence[self._idx % len(self._sequence)]
        self._idx += 1
        return Candidate(
            type="extractor_config",
            params={"config_delta": dict(delta)},
            reversible=True,
        )


class BondProposer:
    """Claude-based proposer for bond extractor config optimization (optional, not used in base).

    If implemented, would receive TRAIN split only and propose field patterns/validation.
    For now, the control plane uses ScriptedExtractor for deterministic offline runs.
    """

    def __init__(self, model: str = "claude-haiku-4-5-20251001", client=None):
        """Initialize the proposer.

        Args:
            model: Model ID (default: Haiku).
            client: Optional Anthropic client (for injection in tests).
        """
        self.model = model
        self._client = client

    def propose(self, task_spec: dict, history: list) -> Candidate:
        """Propose a config delta using Claude (placeholder).

        For now, this is not implemented. Use ScriptedExtractor instead.
        """
        raise NotImplementedError(
            "BondProposer is a placeholder. Use ScriptedExtractor for deterministic testing."
        )
