"""Infra-free checks for the JOB-complex runner's proposer + workload (no DB)."""

from scripts.run_job_curve import JobProposer, _JOB_QUERY


def test_job_proposer_sequence_includes_indexes_and_statistics():
    p = JobProposer()
    seq = [p.propose({}, []) for _ in range(4)]
    kinds = [(c.type, c.params["table"], tuple(c.params["columns"])) for c in seq]
    assert kinds == [
        ("index", "cast_info", ("movie_id",)),
        ("index", "movie_keyword", ("movie_id",)),
        ("statistics", "title", ("production_year", "kind_id")),
        ("index", "movie_keyword", ("keyword_id",)),
    ]
    # the statistics remedy must satisfy the action's >=2-column rule
    stats = seq[2]
    assert stats.type == "statistics" and len(stats.params["columns"]) >= 2
    assert all(c.reversible for c in seq)  # all reversible -> frozen pore allows them


def test_workload_query_is_a_five_table_join():
    assert _JOB_QUERY.count(" JOIN ") == 4  # 5 tables -> 4 joins
    assert "production_year" in _JOB_QUERY and "kt.kind = 'movie'" in _JOB_QUERY
