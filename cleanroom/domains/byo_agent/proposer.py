"""BYO-Agent proposer — suggests config deltas via Claude or scripted sequence.

The proposer is the only agentic part. It receives ONLY the train split (never holdout)
and the objective. It proposes config deltas (system_prompt, few_shot, temperature, etc.)
but can NEVER see or alter _grader, _eval, or _loss_hash.
"""

import os

from cleanroom.types import Candidate


class BYOAgentProposer:
    """Claude-based proposer for agent config optimization.

    Uses forced tool_use to extract a structured config delta.
    The proposer receives the TRAIN split only, never the holdout.
    """

    def __init__(self, model: str = "claude-haiku-4-5-20251001", client=None):
        """Initialize the proposer.

        Args:
            model: Model ID (default: Haiku).
            client: Optional Anthropic client (for injection in tests).
        """
        self.model = model
        self._client = client

    @property
    def client(self):
        """Lazy-load Anthropic client."""
        if self._client is None:
            import anthropic

            api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get(
                "anthropic_api_key"
            )
            if not api_key:
                raise ValueError(
                    "No ANTHROPIC_API_KEY set. Provide one for real Claude proposer, "
                    "or use ScriptedProposer for offline testing."
                )
            self._client = anthropic.Anthropic(api_key=api_key)
        return self._client

    def propose(self, task_spec: dict, history: list) -> Candidate:
        """Propose a config delta using Claude.

        Args:
            task_spec: Dict with:
                - objective: str
                - train_examples: list of {"input", "expected"} from TRAIN split
                - current_config: dict
            history: List of prior accepted Candidate objects.

        Returns:
            Candidate with type="agent_config", params={"config_delta": {...}}.

        Raises:
            ValueError: If the tool response is malformed.
        """
        objective = task_spec.get("objective", "(No objective provided)")
        train_examples = task_spec.get("train_examples", [])
        current_config = task_spec.get("current_config", {})

        # Build history context (only accepted candidates, no eval leakage).
        history_text = ""
        if history:
            history_text = "\n\nPRIOR ACCEPTED CONFIGS:\n"
            for i, h in enumerate(history, 1):
                h_dict = (
                    {"type": h.type, "params": h.params}
                    if isinstance(h, Candidate)
                    else h
                )
                history_text += f"{i}. {h_dict}\n"

        # Build train examples context (NEVER holdout).
        examples_text = ""
        if train_examples:
            examples_text = "\n\nTRAIN SET EXAMPLES (learn from failures):\n"
            for i, ex in enumerate(train_examples[:5], 1):  # Limit to 5 for context
                examples_text += f"{i}. Input: {ex.get('input', '')} | Expected: {ex.get('expected', '')}\n"

        user_prompt = f"""Optimize this agent's config to improve accuracy.

OBJECTIVE:
{objective}

CURRENT CONFIG:
{current_config}

TRAIN SET (do NOT use holdout):
{examples_text}

HISTORY:
{history_text}

You are the PROPOSER (contestant). You have NO ability to measure or judge.
The REFEREE (held-out labels + grader) will evaluate your proposal.

Propose ONE config delta that you believe will improve accuracy.
Config delta should modify one or more of: system_prompt, few_shot, temperature, top_p, max_tokens.
NEVER attempt to modify _agent, _grader, _eval, or _loss_hash (frozen).

Call the propose_config_delta tool with your proposal.
"""

        system_prompt = (
            "You are an AI agent tuning expert. Your job is to propose configuration changes "
            "(system_prompt, few_shot examples, decoding parameters) that improve agent accuracy. "
            "\n\nIMPORTANT: You are the PROPOSER, not the REFEREE. You do NOT measure or judge. "
            "The referee uses held-out labels to evaluate your proposal."
        )

        tools = [
            {
                "name": "propose_config_delta",
                "description": "Propose a config delta to improve the agent",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "rationale": {
                            "type": "string",
                            "description": "Why this change should improve accuracy",
                        },
                        "system_prompt": {
                            "type": "string",
                            "description": "(Optional) New system prompt",
                        },
                        "few_shot": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": "(Optional) Few-shot examples to add/replace",
                        },
                        "temperature": {
                            "type": "number",
                            "description": "(Optional) New temperature (0.0 - 2.0)",
                        },
                        "top_p": {
                            "type": "number",
                            "description": "(Optional) New top_p (0.0 - 1.0)",
                        },
                        "max_tokens": {
                            "type": "integer",
                            "description": "(Optional) New max tokens",
                        },
                    },
                    "required": ["rationale"],
                },
            }
        ]

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=system_prompt,
            tools=tools,
            tool_choice={"type": "tool", "name": "propose_config_delta"},
            messages=[{"role": "user", "content": user_prompt}],
        )

        # Extract tool use from response
        for block in response.content:
            if block.type == "tool_use":
                if block.name != "propose_config_delta":
                    raise ValueError(
                        f"Expected 'propose_config_delta' tool, got '{block.name}'"
                    )

                tool_input = block.input

                # Build config delta (only non-None fields)
                config_delta = {}
                for key in [
                    "system_prompt",
                    "few_shot",
                    "temperature",
                    "top_p",
                    "max_tokens",
                ]:
                    if key in tool_input and tool_input[key] is not None:
                        config_delta[key] = tool_input[key]

                return Candidate(
                    type="agent_config",
                    params={"config_delta": config_delta},
                    reversible=True,
                )

        raise ValueError("Response did not contain a propose_config_delta tool use")


class ScriptedProposer:
    """Deterministic test proposer — cycles through a fixed sequence of config deltas.

    Used for offline curve scripts and deterministic testing.
    """

    def __init__(self, sequence: list = None):
        """Initialize with a sequence of config deltas.

        Args:
            sequence: List of dicts, each representing a config_delta.
        """
        self._sequence = sequence or [
            {"system_prompt": "You are an expert. Answer precisely."},
            {"few_shot": [{"input": "What is 2+2?", "output": "4"}]},
            {"temperature": 0.5},
            {"top_p": 0.9},
            {"system_prompt": "Answer carefully and verify your work."},
        ]
        self._idx = 0

    def propose(self, task_spec: dict, history: list) -> Candidate:
        """Return the next config delta from the sequence."""
        delta = self._sequence[self._idx % len(self._sequence)]
        self._idx += 1
        return Candidate(
            type="agent_config", params={"config_delta": dict(delta)}, reversible=True
        )
