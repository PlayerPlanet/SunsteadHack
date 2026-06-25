"""Code actions — apply and rollback source edits to candidate_agent.py.

The candidate is a Candidate with type="source_edit" and params carrying the
new source text or a THRESHOLD value. Apply reads the current source, pushes
it to a stack, writes the edit, and reloads the module. Rollback pops and
restores the exact source text + reloads.

NOTE (future hardening): An alternative design would isolate each iteration
in a git worktree, but that proved flaky on this machine (EBUSY on OneDrive).
This snapshot-reload mechanism is stable and fast. If needed, switch to:
  - git worktree create --detach per-iteration
  - Run loop in the worktree
  - Merge back on accept, discard on reject
For now, this single-process stack is the implementation.
"""

import importlib
import importlib.util
import os
import pathlib
from cleanroom.types import Candidate


_MODULE_NAME = "cleanroom.domains.agent.candidate_agent"


def _get_candidate_agent_path() -> pathlib.Path:
    """Return absolute path to candidate_agent.py."""
    return pathlib.Path(__file__).parent / "candidate_agent.py"


def _reload_candidate_agent():
    """Reload candidate_agent so the new source is used — recompiling from source.

    importlib.reload() trusts a cached .pyc when its stored source mtime matches the
    file's mtime. Two source rewrites within a single filesystem mtime tick (which
    happens routinely here — apply() edits the file in well under a millisecond) share
    that mtime, so reload() would skip recompilation and load STALE bytecode. We defeat
    that by invalidating finder caches and deleting the cached .pyc before reload, which
    forces a fresh compile from the current source text every time.
    """
    try:
        import sys

        importlib.invalidate_caches()
        path = _get_candidate_agent_path()
        try:
            cache = importlib.util.cache_from_source(str(path))
            if os.path.exists(cache):
                os.remove(cache)
        except OSError:
            pass

        if _MODULE_NAME in sys.modules:
            importlib.reload(sys.modules[_MODULE_NAME])
        else:
            importlib.import_module(_MODULE_NAME)
    except Exception as e:
        raise RuntimeError(f"Failed to reload candidate_agent after edit: {e}")


class CodeActions:
    """Manages source edits to candidate_agent.py via a stack.

    Each apply() pushes the current source to a stack, writes the edited
    source (either from params["source_text"] or by changing THRESHOLD),
    and reloads the module. Each rollback() pops and restores, guaranteeing
    exact round-trip.

    Uses instance state (_source_stack) to isolate stack state across
    multiple CodeActions instances (no cross-test/run pollution).
    """

    def __init__(self):
        """Initialize with an empty source stack."""
        self._source_stack = []

    def apply(self, env: dict, candidate: Candidate) -> None:
        """Apply a source edit to candidate_agent.py.

        Args:
            env: Domain environment (unused; actions work on filesystem).
            candidate: Proposed candidate with type="source_edit" and params:
                - source_text (str, optional): Full new source. If missing,
                  assumes params["threshold"] is provided.
                - threshold (float, optional): New THRESHOLD value. Ignored if
                  source_text is provided.

        Raises:
            ValueError: If candidate type is not "source_edit".
            RuntimeError: If reload fails.
        """
        if candidate.type != "source_edit":
            raise ValueError(
                f"CodeActions.apply: expected type='source_edit', got '{candidate.type}'"
            )

        path = _get_candidate_agent_path()
        current_source = path.read_text()

        # Push current source to stack (for exact rollback symmetry).
        self._source_stack.append((str(path), current_source))

        # Determine new source.
        new_source = candidate.params.get("source_text")
        if new_source is None:
            # Edit mode: change THRESHOLD only.
            threshold = candidate.params.get("threshold")
            if threshold is None:
                raise ValueError(
                    "CodeActions.apply: either source_text or threshold required"
                )
            # Replace ONLY the module-level THRESHOLD assignment (anchored to line
            # start, single occurrence). An unanchored replace-all would also rewrite
            # docstring/comment mentions of "THRESHOLD = ...", which silently corrupted
            # state and caused regression edits to be dropped as false no-ops.
            import re
            new_source, n = re.subn(
                r'^THRESHOLD\s*=\s*[\d.]+',
                f'THRESHOLD = {threshold}',
                current_source,
                count=1,
                flags=re.MULTILINE,
            )
            if n == 0:
                raise ValueError(
                    "CodeActions.apply: no module-level 'THRESHOLD = ...' assignment "
                    "found in candidate_agent.py"
                )
            # Genuine no-op (threshold already at target): stack already pushed for
            # rollback symmetry, so just return without rewriting/reloading.
            if new_source == current_source:
                return

        # Write the new source.
        path.write_text(new_source)

        # Reload the module so the loop picks up the new behavior.
        _reload_candidate_agent()

    def rollback(self, env: dict, candidate: Candidate) -> None:
        """Rollback the last apply() by restoring prior source from stack.

        Pops the stack, restores the source text exactly, and reloads.

        Args:
            env: Domain environment (unused).
            candidate: The candidate that was applied (unused, for symmetry).
        """
        if not self._source_stack:
            raise RuntimeError("CodeActions.rollback: stack is empty")

        path_str, prior_source = self._source_stack.pop()
        path = pathlib.Path(path_str)
        path.write_text(prior_source)

        # Reload to restore the prior behavior.
        _reload_candidate_agent()
