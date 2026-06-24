"""Golden tests for ClaudeProposer (Story A, issue #2).

Tests the real default Claude proposer with both offline unit tests (stub client)
and optional real API calls (decorated with @pytest.mark.golden and skipped when
API key is not available).

DESIGN NOTE:
The offline unit tests run always (no network, no API key required).
The golden test (real API) runs only when ANTHROPIC_API_KEY or anthropic_api_key
is set in the environment. Use:
  pytest tests/test_proposer_golden.py::TestClaudeProposerGolden::test_golden_real_api
to run the golden test explicitly.
"""

import os
import pytest
from unittest.mock import MagicMock

from cleanroom.loop.proposers import ClaudeProposer
from cleanroom.types import Candidate


class TestClaudeProposerOffline:
    """Offline unit tests with injected fake client (no network)."""

    def test_proposer_init_stores_model(self):
        """Verify model parameter is stored."""
        proposer = ClaudeProposer(model="claude-sonnet-4-6")
        assert proposer.model == "claude-sonnet-4-6"

    def test_proposer_init_stores_max_tokens(self):
        """Verify max_tokens parameter is stored."""
        proposer = ClaudeProposer(max_tokens=512)
        assert proposer.max_tokens == 512

    def test_lazy_client_raises_without_api_key(self):
        """Verify accessing client without API key raises ValueError."""
        # Temporarily hide API keys
        old_key = os.environ.pop("ANTHROPIC_API_KEY", None)
        old_lower_key = os.environ.pop("anthropic_api_key", None)

        try:
            proposer = ClaudeProposer()
            with pytest.raises(ValueError, match="No ANTHROPIC_API_KEY"):
                _ = proposer.client
        finally:
            # Restore
            if old_key:
                os.environ["ANTHROPIC_API_KEY"] = old_key
            if old_lower_key:
                os.environ["anthropic_api_key"] = old_lower_key

    def test_propose_with_fake_client_returns_valid_candidate(self):
        """Propose with a fake client that returns a stubbed tool_use block."""
        # Create a fake client
        fake_client = MagicMock()

        # Create a mock response with a tool_use block
        tool_input = {
            "type": "index",
            "params": {"table": "users", "columns": ["email", "created_at"]},
            "reversible": True,
        }

        mock_tool_use = MagicMock()
        mock_tool_use.type = "tool_use"
        mock_tool_use.name = "propose_candidate"
        mock_tool_use.input = tool_input

        mock_response = MagicMock()
        mock_response.content = [mock_tool_use]

        fake_client.messages.create.return_value = mock_response

        # Create proposer with fake client
        proposer = ClaudeProposer(client=fake_client)

        # Call propose
        task_spec = {
            "objective": "minimize p99",
            "context": {
                "schema": "CREATE TABLE users (id INT, email VARCHAR, created_at TIMESTAMP)",
            },
        }
        history = []

        candidate = proposer.propose(task_spec, history)

        # Verify the candidate
        assert isinstance(candidate, Candidate)
        assert candidate.type == "index"
        assert candidate.params["table"] == "users"
        assert candidate.params["columns"] == ["email", "created_at"]
        assert candidate.reversible is True

        # Verify the client was called
        assert fake_client.messages.create.called

    def test_propose_includes_history_in_prompt(self):
        """Verify history is included in the outgoing prompt."""
        fake_client = MagicMock()

        tool_input = {
            "type": "index",
            "params": {"table": "orders", "columns": ["user_id"]},
            "reversible": True,
        }

        mock_tool_use = MagicMock()
        mock_tool_use.type = "tool_use"
        mock_tool_use.input = tool_input

        mock_response = MagicMock()
        mock_response.content = [mock_tool_use]

        fake_client.messages.create.return_value = mock_response

        proposer = ClaudeProposer(client=fake_client)

        # Create some history
        history = [
            Candidate(type="index", params={"table": "users", "columns": ["id"]}, reversible=True),
            Candidate(type="index", params={"table": "posts", "columns": ["user_id"]}, reversible=True),
        ]

        task_spec = {
            "objective": "cut p99",
            "context": {"schema": "..."},
        }

        candidate = proposer.propose(task_spec, history)

        # Check that create() was called
        assert fake_client.messages.create.called

        # Get the call kwargs
        call_kwargs = fake_client.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]

        # Verify history is in the prompt
        assert "PRIOR ACCEPTED CANDIDATES" in user_content
        assert "users" in user_content
        assert "posts" in user_content

    def test_propose_with_empty_history(self):
        """Propose with an empty history list."""
        fake_client = MagicMock()

        tool_input = {
            "type": "index",
            "params": {"table": "events", "columns": ["timestamp"]},
            "reversible": True,
        }

        mock_tool_use = MagicMock()
        mock_tool_use.type = "tool_use"
        mock_tool_use.input = tool_input

        mock_response = MagicMock()
        mock_response.content = [mock_tool_use]

        fake_client.messages.create.return_value = mock_response

        proposer = ClaudeProposer(client=fake_client)

        task_spec = {
            "objective": "optimize",
            "context": {"schema": "..."},
        }

        candidate = proposer.propose(task_spec, [])

        assert isinstance(candidate, Candidate)
        assert candidate.type == "index"

    def test_propose_raises_on_missing_tool_use(self):
        """Raise ValueError if model response lacks tool_use block."""
        fake_client = MagicMock()

        # Response without tool_use
        mock_response = MagicMock()
        mock_response.content = [MagicMock(type="text")]  # Not a tool_use

        fake_client.messages.create.return_value = mock_response

        proposer = ClaudeProposer(client=fake_client)

        task_spec = {"objective": "...", "context": {"schema": "..."}}

        with pytest.raises(ValueError, match="did not contain a propose_candidate tool use"):
            proposer.propose(task_spec, [])

    def test_propose_raises_on_missing_table_in_index(self):
        """Raise ValueError if index candidate lacks 'table' param."""
        fake_client = MagicMock()

        tool_input = {
            "type": "index",
            "params": {"columns": ["col1", "col2"]},  # Missing 'table'
            "reversible": True,
        }

        mock_tool_use = MagicMock()
        mock_tool_use.type = "tool_use"
        mock_tool_use.input = tool_input

        mock_response = MagicMock()
        mock_response.content = [mock_tool_use]

        fake_client.messages.create.return_value = mock_response

        proposer = ClaudeProposer(client=fake_client)

        task_spec = {"objective": "...", "context": {"schema": "..."}}

        with pytest.raises(ValueError, match="missing or invalid 'table'"):
            proposer.propose(task_spec, [])

    def test_propose_raises_on_missing_columns_in_index(self):
        """Raise ValueError if index candidate lacks 'columns' param."""
        fake_client = MagicMock()

        tool_input = {
            "type": "index",
            "params": {"table": "users"},  # Missing 'columns'
            "reversible": True,
        }

        mock_tool_use = MagicMock()
        mock_tool_use.type = "tool_use"
        mock_tool_use.input = tool_input

        mock_response = MagicMock()
        mock_response.content = [mock_tool_use]

        fake_client.messages.create.return_value = mock_response

        proposer = ClaudeProposer(client=fake_client)

        task_spec = {"objective": "...", "context": {"schema": "..."}}

        with pytest.raises(ValueError, match="missing or empty 'columns'"):
            proposer.propose(task_spec, [])

    def test_propose_raises_on_empty_columns_list(self):
        """Raise ValueError if index candidate has empty columns list."""
        fake_client = MagicMock()

        tool_input = {
            "type": "index",
            "params": {"table": "users", "columns": []},  # Empty columns
            "reversible": True,
        }

        mock_tool_use = MagicMock()
        mock_tool_use.type = "tool_use"
        mock_tool_use.input = tool_input

        mock_response = MagicMock()
        mock_response.content = [mock_tool_use]

        fake_client.messages.create.return_value = mock_response

        proposer = ClaudeProposer(client=fake_client)

        task_spec = {"objective": "...", "context": {"schema": "..."}}

        with pytest.raises(ValueError, match="missing or empty 'columns'"):
            proposer.propose(task_spec, [])

    def test_propose_raises_on_invalid_type(self):
        """Raise ValueError if candidate type is not 'index' or 'guc'."""
        fake_client = MagicMock()

        tool_input = {
            "type": "unknown",  # Invalid type
            "params": {"table": "users", "columns": ["id"]},
            "reversible": True,
        }

        mock_tool_use = MagicMock()
        mock_tool_use.type = "tool_use"
        mock_tool_use.input = tool_input

        mock_response = MagicMock()
        mock_response.content = [mock_tool_use]

        fake_client.messages.create.return_value = mock_response

        proposer = ClaudeProposer(client=fake_client)

        task_spec = {"objective": "...", "context": {"schema": "..."}}

        with pytest.raises(ValueError, match="Invalid candidate type"):
            proposer.propose(task_spec, [])

    def test_propose_accepts_guc_candidates(self):
        """Verify GUC (PostgreSQL parameter) candidates are accepted."""
        fake_client = MagicMock()

        tool_input = {
            "type": "guc",
            "params": {"param": "shared_buffers", "value": "4GB"},
            "reversible": False,
        }

        mock_tool_use = MagicMock()
        mock_tool_use.type = "tool_use"
        mock_tool_use.input = tool_input

        mock_response = MagicMock()
        mock_response.content = [mock_tool_use]

        fake_client.messages.create.return_value = mock_response

        proposer = ClaudeProposer(client=fake_client)

        task_spec = {"objective": "...", "context": {"schema": "..."}}

        candidate = proposer.propose(task_spec, [])

        assert candidate.type == "guc"
        assert candidate.params["param"] == "shared_buffers"


class TestClaudeProposerGolden:
    """Golden tests that hit the real Anthropic API (skip if no key)."""

    @pytest.mark.golden
    @pytest.mark.skipif(
        not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("anthropic_api_key")),
        reason="ANTHROPIC_API_KEY or anthropic_api_key not set",
    )
    def test_golden_real_api_with_join_order_benchmark_schema(self):
        """Call the REAL API with a realistic IMDB/Join-Order-Benchmark schema.

        This test:
        1. Instantiates the real ClaudeProposer (default Haiku model).
        2. Provides a realistic schema (Join Order Benchmark tables).
        3. Provides a slow query example (join with predicates).
        4. Calls propose() once.
        5. Validates the returned Candidate structure.
        6. Prints the actual Candidate and token usage for manual verification.
        """
        # Real schema (simplified IMDB / Join Order Benchmark)
        schema = """
CREATE TABLE title (
    id INTEGER PRIMARY KEY,
    title VARCHAR,
    production_year INTEGER,
    kind_id INTEGER
);

CREATE TABLE cast_info (
    id INTEGER PRIMARY KEY,
    person_id INTEGER,
    movie_id INTEGER,
    role_id INTEGER,
    nr_order INTEGER
);

CREATE TABLE movie_keyword (
    id INTEGER PRIMARY KEY,
    movie_id INTEGER,
    keyword_id INTEGER
);

CREATE TABLE movie_companies (
    id INTEGER PRIMARY KEY,
    movie_id INTEGER,
    company_id INTEGER
);
"""

        slow_query = """
SELECT t.title, COUNT(c.id) as num_actors
FROM title t
JOIN cast_info c ON t.id = c.movie_id
WHERE t.production_year >= 2000
  AND t.production_year <= 2010
GROUP BY t.title
ORDER BY num_actors DESC
LIMIT 10;
"""

        task_spec = {
            "objective": "Minimize p99 latency on Join Order Benchmark queries; cost budget: $500/day",
            "context": {
                "schema": schema,
                "slow_queries": slow_query,
            },
        }

        # Instantiate with default Haiku model (no client injection = real API)
        proposer = ClaudeProposer()

        # Propose with empty history
        candidate = proposer.propose(task_spec, [])

        # Validate structure
        assert isinstance(candidate, Candidate), f"Expected Candidate, got {type(candidate)}"
        assert candidate.type in ("index", "guc"), f"Invalid type: {candidate.type}"
        assert isinstance(candidate.params, dict), f"params must be dict, got {type(candidate.params)}"
        assert isinstance(candidate.reversible, bool), f"reversible must be bool"

        # If it's an index, validate table and columns exist and are reasonable
        if candidate.type == "index":
            assert "table" in candidate.params, "Index missing 'table' param"
            assert "columns" in candidate.params, "Index missing 'columns' param"

            table = candidate.params["table"]
            columns = candidate.params["columns"]

            assert isinstance(table, str) and len(table) > 0, f"Invalid table: {table}"
            assert isinstance(columns, list) and len(columns) > 0, f"Invalid columns: {columns}"
            assert all(isinstance(c, str) for c in columns), f"Columns must be strings: {columns}"

            # Verify table is one of the schema tables
            schema_tables = ["title", "cast_info", "movie_keyword", "movie_companies"]
            assert table in schema_tables, f"Table '{table}' not in schema tables {schema_tables}"

            # (In a full integration, we'd also validate columns against the schema;
            # here we just check they're plausible strings.)

        # Print results for manual verification
        print(f"\n=== GOLDEN TEST RESULT ===")
        print(f"Proposed Candidate:")
        print(f"  type: {candidate.type}")
        print(f"  params: {candidate.params}")
        print(f"  reversible: {candidate.reversible}")

        # Get token usage from the proposer's last response
        if hasattr(proposer, "last_response") and proposer.last_response:
            usage = proposer.last_response.usage
            print(f"\nToken Usage:")
            print(f"  input_tokens: {usage.input_tokens}")
            print(f"  output_tokens: {usage.output_tokens}")
            print(f"  total_tokens: {usage.input_tokens + usage.output_tokens}")
            print(f"  cache_creation_input_tokens: {getattr(usage, 'cache_creation_input_tokens', 0)}")
            print(f"  cache_read_input_tokens: {getattr(usage, 'cache_read_input_tokens', 0)}")
        else:
            print("(No response metadata captured)")
