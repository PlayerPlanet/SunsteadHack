"""Candidate application and rollback.

Story A (GitHub issue #2) owns the apply/rollback implementation.

Task 1 = index discovery. NOTE: hypopg is NOT available on our Aiven plan
(verified 2026-06-24, service sunstead-pg-bench) — so apply/rollback use a real
CREATE INDEX / DROP INDEX on a small dataset (reversible, sub-second build) rather
than a hypothetical-index proxy. See GitHub issue #2 (Gate-1 update).
"""

from cleanroom.types import Candidate


def apply(conn, candidate: Candidate) -> None:
    """Apply the candidate to the database.

    Args:
        conn: A database connection object.
        candidate: The candidate to apply.

    Raises:
        NotImplementedError: Story A owns this implementation.
    """
    raise NotImplementedError("apply — owned by Story A, GitHub issue #2")


def rollback(conn, candidate: Candidate) -> None:
    """Rollback the candidate from the database.

    Args:
        conn: A database connection object.
        candidate: The candidate to rollback.

    Raises:
        NotImplementedError: Story A owns this implementation.
    """
    raise NotImplementedError("rollback — owned by Story A, GitHub issue #2")
