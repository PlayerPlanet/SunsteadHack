"""Frozen workload SQL registry for the benchmark harness.

Maps workload_id -> SQL query. Keeping queries here (rather than scattered through
the loop or benchmark code) ensures they are version-controlled and frozen: every
iteration measures the same thing.

This module is used by dispatch paths (control plane) and direct loop invocations
(substrate driver) to register real workloads at runtime before calling run_benchmark().
"""

# Workload catalog: workload_id -> SQL query
#
# The "__default__" workload is always available (registered in cleanroom/benchmark/__init__.py).
# Other workloads must be registered via register_workload() before use.

WORKLOAD_CATALOG = {
    "job-prodyear": (
        "select t.id, t.title, count(*) "
        "from title t join cast_info ci on ci.movie_id = t.id "
        "where t.production_year between 2000 and 2005 "
        "group by t.id, t.title order by count(*) desc limit 20"
    ),
}
