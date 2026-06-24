"""Real Claude proposer for Story A (issue #2) — Phase-0 interior loop.

DESIGN PRINCIPLE (load-bearing):
The proposer is the **only agentic, nondeterministic** part of the loop.
It has NO ability to apply, measure, or score. That separation is what keeps
the autoresearch metric an objective judge. In this single-shot SDK implementation,
"read-only" is enforced trivially: the model is given DB context as text and
returns a structured proposal; it gets no mutating tools.

FUTURE EXTENSION (Story C):
Phase-1 swaps the injected text-context for live read-only Aiven MCP tools
(pg_read, EXPLAIN, pg_stat_statements) behind the same `propose()` seam.
"""

import os
from cleanroom.types import Candidate


class ClaudeProposer:
    """Agentic proposer using Claude API to suggest database optimization candidates.

    Proposes index candidates based on task context (schema, slow queries, objectives)
    and past acceptance history. Uses forced tool_use for structured output validation.

    Constructor args:
        model: Model ID to use (default: "claude-haiku-4-5-20251001").
            Can be overridden per instance, e.g., ClaudeProposer(model="claude-sonnet-4-6").
        max_tokens: Max tokens for the model's response (default: 1024).
        client: Anthropic client instance. If None, lazily construct on first call.
                (Exists for test injection; see unit tests for mock examples.)
    """

    def __init__(self, *, model: str = "claude-haiku-4-5-20251001", max_tokens: int = 1024, client=None):
        """Initialize the proposer.

        Args:
            model: Model ID to use (default: Haiku).
            max_tokens: Max tokens for response (default: 1024).
            client: Optional pre-constructed Anthropic client for testing.
        """
        self.model = model
        self.max_tokens = max_tokens
        self._client = client

    @property
    def client(self):
        """Lazy-load Anthropic client on first access."""
        if self._client is None:
            import anthropic
            api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("anthropic_api_key")
            if not api_key:
                raise ValueError(
                    "No ANTHROPIC_API_KEY or anthropic_api_key in environment. "
                    "Set one to use ClaudeProposer with the real API."
                )
            self._client = anthropic.Anthropic(api_key=api_key)
        return self._client

    def propose(self, task_spec: dict, history: list) -> Candidate:
        """Propose a database optimization candidate using Claude.

        Also stores the latest response metadata (usage, tokens) in self.last_response
        for introspection and metrics collection.

        Args:
            task_spec: Dict with optional keys:
                - objective: str, e.g. "minimize p99 on workload job_q1, cost ≤ budget"
                - context: dict with:
                    - schema: str, DDL or table/column summary
                    - slow_queries: str (optional), problematic queries
                    - stat_statements: str (optional), pg_stat_statements output
            history: List of prior accepted Candidate objects (as JSON dicts or Candidate instances).
                     The proposer inspects this to avoid re-proposing.

        Attributes set after successful call:
            last_response: The full response object from client.messages.create().
                          Includes response.usage with input_tokens, output_tokens, etc.

        Returns:
            Candidate: A validated Candidate with type, params (table+columns for index),
                      and reversible flag.

        Raises:
            ValueError: If the model's response lacks a propose_candidate tool use,
                       or if the tool input is malformed (missing table/columns, etc.).
        """
        self.last_response = None  # Will be set after API call
        """Propose a database optimization candidate using Claude.

        Builds a prompt from task_spec (objective, context with schema and slow_queries),
        includes prior accepted history to avoid re-proposing, and calls Claude via
        the Messages API with forced tool use for structured output.

        Args:
            task_spec: Dict with optional keys:
                - objective: str, e.g. "minimize p99 on workload job_q1, cost ≤ budget"
                - context: dict with:
                    - schema: str, DDL or table/column summary
                    - slow_queries: str (optional), problematic queries
                    - stat_statements: str (optional), pg_stat_statements output
            history: List of prior accepted Candidate objects (as JSON dicts or Candidate instances).
                     The proposer inspects this to avoid re-proposing.

        Returns:
            Candidate: A validated Candidate with type, params (table+columns for index),
                      and reversible flag.

        Raises:
            ValueError: If the model's response lacks a propose_candidate tool use,
                       or if the tool input is malformed (missing table/columns, etc.).
        """
        # Build the system prompt
        system_prompt = (
            "You are a database optimization expert. Your task is to propose a single "
            "database optimization candidate (index or GUC parameter) to improve query performance.\n\n"
            "IMPORTANT: You have NO ability to apply changes, measure results, or score candidates. "
            "You ONLY propose. The decision loop will measure, gate, and decide.\n\n"
            "You must call the propose_candidate tool with exactly one proposal. "
            "Choose either a multi-column index or a PostgreSQL parameter change."
        )

        # Build history context
        history_text = ""
        if history:
            history_text = "\n\nPRIOR ACCEPTED CANDIDATES (do not re-propose these):\n"
            for i, h in enumerate(history, 1):
                if isinstance(h, Candidate):
                    h_dict = {"type": h.type, "params": h.params}
                else:
                    h_dict = h
                history_text += f"{i}. {h_dict}\n"

        # Extract context
        context = task_spec.get("context", {})
        schema = context.get("schema", "(No schema provided)")
        slow_queries = context.get("slow_queries", "(No slow queries provided)")
        stat_statements = context.get("stat_statements", "(No stat_statements provided)")
        objective = task_spec.get("objective", "(No explicit objective)")

        # Build the user prompt
        user_prompt = f"""Task Objective:
{objective}

Database Schema:
{schema}

Slow Queries / Problem Workload:
{slow_queries}

Query Statistics (if available):
{stat_statements}
{history_text}

Based on the schema and problem workload, propose ONE candidate optimization:
- If proposing an INDEX: choose a table, list the columns that would most improve query performance
- If proposing a GUC parameter: choose a PostgreSQL parameter name and a new value

Call the propose_candidate tool with your proposal.
"""

        # Define the tool for structured output
        tools = [
            {
                "name": "propose_candidate",
                "description": "Propose a database optimization candidate (index or parameter change)",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": ["index", "guc"],
                            "description": "Type of candidate: 'index' for database index, 'guc' for PostgreSQL parameter",
                        },
                        "params": {
                            "type": "object",
                            "description": (
                                "For index: {'table': str, 'columns': [str, ...]}. "
                                "For guc: {'param': str, 'value': str or number}"
                            ),
                        },
                        "reversible": {
                            "type": "boolean",
                            "description": "Whether this change can be rolled back",
                        },
                    },
                    "required": ["type", "params", "reversible"],
                },
            }
        ]

        # Call the model with forced tool use
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system_prompt,
            tools=tools,
            tool_choice={"type": "tool", "name": "propose_candidate"},
            messages=[
                {
                    "role": "user",
                    "content": user_prompt,
                }
            ],
        )

        # Store response for introspection (usage, metadata, etc.)
        self.last_response = response

        # Extract the tool use block
        tool_use_block = None
        for block in response.content:
            if block.type == "tool_use":
                tool_use_block = block
                break

        if tool_use_block is None:
            raise ValueError(
                "Model response did not contain a propose_candidate tool use. "
                f"Response: {response.content}"
            )

        # Parse the tool input
        tool_input = tool_use_block.input

        # Validate and construct Candidate
        candidate_type = tool_input.get("type")
        params = tool_input.get("params", {})
        reversible = tool_input.get("reversible", True)

        if candidate_type not in ("index", "guc"):
            raise ValueError(
                f"Invalid candidate type '{candidate_type}'. Must be 'index' or 'guc'."
            )

        if candidate_type == "index":
            # Validate index params
            table = params.get("table")
            columns = params.get("columns")

            if not table or not isinstance(table, str):
                raise ValueError(
                    f"Index candidate missing or invalid 'table' in params: {params}"
                )
            if not columns or not isinstance(columns, list) or len(columns) == 0:
                raise ValueError(
                    f"Index candidate missing or empty 'columns' in params: {params}"
                )
            if not all(isinstance(c, str) for c in columns):
                raise ValueError(
                    f"Index candidate 'columns' must be a list of strings: {columns}"
                )

        return Candidate(type=candidate_type, params=params, reversible=reversible)


class ClaudeCodeProposer:
    """Claude Code containerized researcher for Story A interior loop.

    This is the PRIMARY proposer: a containerized agent that queries a read-only
    Postgres instance via MCP, inspects schema/statistics, and proposes optimizations.

    DESIGN PRINCIPLE (load-bearing — document it):
    The researcher ONLY proposes; it cannot apply, measure, or score. "Read-only"
    is enforced THREE ways (defense in depth):
      (1) Connects as the researcher_ro SELECT-only DB role
      (2) Via a read-only Postgres MCP (all queries run in READ-ONLY transactions)
      (3) The claude CLI --allowedTools whitelist + --disallowedTools blacklist
    This is what makes "the optimizer can't grade its own homework" a config fact,
    not a promise.

    Constructor args:
        model: Model ID to use in the container (default: "claude-haiku-4-5-20251001").
        image: Docker image name (default: "sunstead-proposer:latest").
        timeout: Seconds to wait for the container run (default: 180).
    """

    def __init__(
        self,
        *,
        model: str = "claude-haiku-4-5-20251001",
        image: str = "sunstead-proposer:latest",
        timeout: int = 180,
    ):
        """Initialize the proposer.

        Args:
            model: Model ID to use in the container.
            image: Docker image name.
            timeout: Seconds to wait for container completion.
        """
        self.model = model
        self.image = image
        self.timeout = timeout
        self.last_response = None

    def propose(self, task_spec: dict, history: list) -> Candidate:
        """Propose a database optimization candidate using Claude Code in a container.

        The container connects to a read-only Postgres replica (or the local DB via
        host.docker.internal:55432) and inspects schema, table sizes, and statistics
        to propose a single index. Prior accepted candidates are passed as context
        to avoid re-proposing.

        Args:
            task_spec: Dict with optional keys:
                - objective: str, e.g. "minimize p99 on the title⋈cast_info production_year query"
                - context: dict (optional, may be ignored by the container
                  since it fetches live stats via MCP)
            history: List of prior accepted Candidate objects (Candidate instances or dicts).
                     The container is instructed not to re-propose these.

        Returns:
            Candidate: A validated Candidate with type="index", params with "table" and "columns",
                      and reversible=true.

        Raises:
            ValueError: If docker, the image, or the container is unavailable; or if parsing fails.
        """
        import json
        import os
        import subprocess

        # Check that docker is available
        try:
            subprocess.run(
                ["docker", "version"],
                capture_output=True,
                timeout=5,
                check=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            raise ValueError(
                f"Docker is not available or not running. "
                f"ClaudeCodeProposer requires Docker to run the containerized researcher. Error: {e}"
            )

        # Check that the image exists
        try:
            result = subprocess.run(
                ["docker", "images", "-q", self.image],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )
            if not result.stdout.strip():
                raise ValueError(
                    f"Docker image '{self.image}' not found. "
                    f"Build it with: docker build -t {self.image} proposer-container/"
                )
        except subprocess.CalledProcessError as e:
            raise ValueError(
                f"Failed to check Docker image '{self.image}': {e}"
            )

        # Build the TASK prompt
        objective = task_spec.get("objective", "minimize query latency")
        history_text = ""
        if history:
            history_text = "\n\nPRIOR ACCEPTED CANDIDATES (do not re-propose these):\n"
            for i, h in enumerate(history, 1):
                if isinstance(h, Candidate):
                    h_dict = {"type": h.type, "params": h.params}
                else:
                    h_dict = h
                history_text += f"  {i}. {h_dict}\n"

        task_prompt = f"""Objective:
{objective}

Your task: Inspect the Postgres schema and query statistics using the pg query tool.
Then propose exactly ONE index to speed up the workload.

IMPORTANT: Do not re-propose any of these prior candidates:{history_text}

Your FINAL response must be ONLY a raw JSON object (no markdown, no explanation):
{{"type":"index","params":{{"table":"<table>","columns":["<col>",...]}},"reversible":true}}
"""

        # Get API key from environment
        api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("anthropic_api_key")
        if not api_key:
            raise ValueError(
                "No ANTHROPIC_API_KEY or anthropic_api_key in environment. "
                "Set one to run ClaudeCodeProposer."
            )

        # Run the container
        try:
            result = subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-e",
                    f"ANTHROPIC_API_KEY={api_key}",
                    "-e",
                    f"TASK={task_prompt}",
                    "-e",
                    f"MODEL={self.model}",
                    self.image,
                ],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,  # Don't raise on non-zero exit; we'll parse stderr/stdout
            )
        except subprocess.TimeoutExpired as e:
            raise ValueError(
                f"Container run timed out after {self.timeout}s. "
                f"Increase timeout or optimize the researcher. Error: {e}"
            )
        except Exception as e:
            raise ValueError(
                f"Failed to run container '{self.image}': {e}"
            )

        if result.returncode != 0:
            error_msg = result.stderr or result.stdout
            raise ValueError(
                f"Container exited with code {result.returncode}. "
                f"stderr/stdout: {error_msg[:500]}"
            )

        # Parse the container output (raw JSON from claude --output-format json)
        stdout = result.stdout.strip()
        candidate = self._parse_candidate(stdout)

        return candidate

    def _parse_candidate(self, stdout: str) -> Candidate:
        """Parse and validate a Candidate from containerized claude output.

        The container (via claude --output-format json) outputs a JSON envelope.
        We extract the "result" field, then parse the embedded JSON object
        (handling fenced blocks like ```json ... ```).

        Args:
            stdout: Raw JSON output from the container.

        Returns:
            Candidate: A validated Candidate.

        Raises:
            ValueError: If parsing or validation fails.
        """
        import json
        import re

        # Parse the top-level envelope
        try:
            envelope = json.loads(stdout)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Failed to parse container JSON envelope: {e}. "
                f"stdout: {stdout[:500]}"
            )

        # Extract the "result" field (the model's final output as a string)
        result_str = envelope.get("result")
        if not result_str:
            raise ValueError(
                f"No 'result' field in container JSON. "
                f"envelope keys: {list(envelope.keys())}"
            )

        # The result may be wrapped in markdown fences; extract the JSON
        # Look for ```json ... ``` or just bare JSON
        fenced_match = re.search(r"```(?:json)?\s*(.*?)\s*```", result_str, re.DOTALL)
        if fenced_match:
            json_str = fenced_match.group(1)
        else:
            # Try bare JSON
            json_str = result_str

        # Parse the extracted JSON
        try:
            obj = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Failed to parse embedded JSON from result: {e}. "
                f"result: {result_str[:500]}"
            )

        # Validate structure
        candidate_type = obj.get("type")
        params = obj.get("params", {})
        reversible = obj.get("reversible", True)

        if candidate_type != "index":
            raise ValueError(
                f"Expected type='index', got '{candidate_type}'. "
                f"Full object: {obj}"
            )

        # Validate index params
        table = params.get("table")
        columns = params.get("columns")

        if not table or not isinstance(table, str):
            raise ValueError(
                f"Index candidate missing or invalid 'table': {params}"
            )

        if not isinstance(columns, list):
            raise ValueError(
                f"Index candidate 'columns' must be list of strings, got {type(columns).__name__}: {params}"
            )

        if len(columns) == 0:
            raise ValueError(
                f"Index candidate missing or empty 'columns': {params}"
            )

        if not all(isinstance(c, str) for c in columns):
            raise ValueError(
                f"Index candidate 'columns' must be list of strings: {columns}"
            )

        return Candidate(type=candidate_type, params=params, reversible=reversible)
