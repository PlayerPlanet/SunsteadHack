"""Seed synthetic experiment log for Phase-0 testing.

Story C (GitHub issue #4) owns this implementation.

Fills experiment/crossing/judgment records across drift_level 0→high AND a
cumulative-volume timeline; builds both curves against this before A's real
log exists.
"""


def main():
    """Generate synthetic seed data for the experiment log.

    This function should populate the database with experiment records
    across a range of drift levels and time windows to support boundary
    analysis and model axis experiments.

    Raises:
        NotImplementedError: Story C owns this implementation.
    """
    raise NotImplementedError("main — owned by Story C, GitHub issue #4")


if __name__ == "__main__":
    main()
