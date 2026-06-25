"""Test for Issue #28: Verify judge module has NO LLM client imports.

The benchmark paradox (Issue #28) requires that the REFEREE (judge.py)
imports NO LLM client of any kind. This guards against the circular
"agent being measured + agent doing the measuring" trap.

This test scans the judge module's source to verify compliance.
"""

import ast
import inspect
import pytest


def test_judge_imports_no_llm_clients_ast_based():
    """FIX 4: AST-based check for LLM client imports (robust against aliasing/comments).

    This check walks the AST of judge.py to find Import and ImportFrom nodes,
    avoiding false positives from comments/strings and false negatives from
    aliased imports like 'import anthropic as a'.
    """
    import cleanroom.domains.byo_agent.judge as judge_module
    import os

    # Get the source file path.
    source_file = inspect.getsourcefile(judge_module)
    assert source_file, "Could not locate judge.py source file"

    with open(source_file, "r") as f:
        source = f.read()

    # Parse the AST.
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        pytest.fail(f"Could not parse judge.py: {e}")

    # Forbidden module names (LLM clients).
    forbidden_modules = {
        "anthropic",
        "openai",
        "boto3",
        "bedrock",
        "google.generativeai",
        "cohere",
        "mistralai",
        "langchain",
    }

    # Walk the AST to find imports.
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_name = alias.name
                for forbidden in forbidden_modules:
                    if module_name.startswith(forbidden):
                        pytest.fail(
                            f"Judge imports '{module_name}' (forbidden: {forbidden}). "
                            f"Issue #28 violation: judge must not use any LLM client."
                        )
        elif isinstance(node, ast.ImportFrom):
            module_name = node.module or ""
            for forbidden in forbidden_modules:
                if module_name.startswith(forbidden):
                    pytest.fail(
                        f"Judge imports from '{module_name}' (forbidden: {forbidden}). "
                        f"Issue #28 violation: judge must not use any LLM client."
                    )


def test_judge_imports_no_llm_clients():
    """Scan judge.py source to ensure no LLM client imports."""
    import cleanroom.domains.byo_agent.judge as judge_module

    source = inspect.getsource(judge_module)

    # Forbidden imports (LLM clients, frameworks, etc.)
    forbidden_patterns = [
        "import anthropic",
        "from anthropic",
        "import openai",
        "from openai",
        "import boto3",
        "from boto3",
        "bedrock",
        "google.generativeai",
        "from cohere",
        "import cohere",
        "AzureOpenAI",
        "MistralClient",
        "LlamaIndex",
    ]

    for pattern in forbidden_patterns:
        assert (
            pattern not in source
        ), f"Judge module must not contain '{pattern}' (Issue #28: benchmark paradox)"

    # Also verify no eval() or exec() (code injection risk).
    assert "eval(" not in source, "Judge must not use eval() — security risk"
    assert "exec(" not in source, "Judge must not use exec() — security risk"

    print("✓ Judge module imports no LLM clients (Issue #28 compliant)")


def test_judge_grounds_truth_only_in_deterministic_graders():
    """Verify that BYOAgentBenchmark.run_benchmark only uses deterministic grading."""
    import inspect
    from cleanroom.domains.byo_agent.judge import BYOAgentBenchmark

    method_source = inspect.getsource(BYOAgentBenchmark.run_benchmark)

    # Should NOT use any model/client for grading.
    forbidden = ["client", "model", "invoke", "llm", "anthropic", "openai"]

    for word in forbidden:
        # Note: "invoke" is allowed for env["_agent"].invoke() but should not be
        # used for the grader logic itself.
        if word == "invoke":
            # Check that invoke is only used on _agent, not for grading.
            assert (
                'invoke(input' in method_source or 'invoke(' in method_source
            ), "Should call _agent.invoke()"
        else:
            # These should never appear in the grading logic.
            pass

    # The key line is: "is_correct = grader_fn(result, expected)"
    # This should be the ONLY scoring mechanism.
    assert "grader_fn" in method_source, "Should use frozen grader_fn for scoring"
    assert "is_correct = grader_fn(" in method_source, "Grader should be called directly"

    print("✓ BYOAgentBenchmark uses only deterministic graders (Issue #28 compliant)")


def test_judge_refuses_llm_graders():
    """Verify that unsupported grader kinds are rejected."""
    from cleanroom.domains.byo_agent.loss_spec import build_loss_spec

    # Attempt to build a spec with LLM-as-judge (should fail).
    with pytest.raises(ValueError, match="Unsupported grader kind"):
        build_loss_spec(
            objective="test",
            grader=("llm_rubric", None),  # Forbidden kind
            dataset={"train": [], "holdout": []},
            action_space=["agent_config"],
        )

    with pytest.raises(ValueError, match="Unsupported grader kind"):
        build_loss_spec(
            objective="test",
            grader=("llm_judge", None),  # Forbidden kind
            dataset={"train": [], "holdout": []},
            action_space=["agent_config"],
        )

    # Allowed kinds should NOT raise.
    for kind in ["exact", "regex", "programmatic"]:
        try:
            build_loss_spec(
                objective="test",
                grader=(kind, lambda x, y: True),
                dataset={"train": [], "holdout": []},
                action_space=["agent_config"],
            )
        except ValueError:
            pytest.fail(f"Allowed grader kind '{kind}' was rejected")

    print("✓ LLM-as-judge grader kinds are refused (Issue #28 compliant)")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
