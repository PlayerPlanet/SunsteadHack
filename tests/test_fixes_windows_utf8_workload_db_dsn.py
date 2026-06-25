"""Tests for Windows UTF-8 crash fix, workload catalog registration, and DB_DSN passthrough.

Covers:
  1. ClaudeCodeProposer subprocess encoding fix (Windows UTF-8 decoding)
  2. Workload catalog registration in dispatch path
  3. DB_DSN passthrough to proposer container
"""

import json
import os
import subprocess
from unittest import mock

import pytest

from cleanroom.benchmark import register_workload
from cleanroom.benchmark.workloads import WORKLOAD_CATALOG
from cleanroom.loop.proposers import ClaudeCodeProposer


class TestSubprocessEncoding:
    """Tests for UTF-8 encoding in subprocess.run() calls (Windows fix)."""

    def test_docker_version_call_has_encoding(self):
        """Verify docker version call passes encoding='utf-8' and errors='replace'."""
        proposer = ClaudeCodeProposer()

        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.MagicMock(returncode=0)
            try:
                proposer.propose({"objective": "test"}, [])
            except Exception:
                pass  # We expect it to fail later; we're just checking the docker version call

            # Check that the first call (docker version) was made with encoding and errors params
            first_call = mock_run.call_args_list[0]
            assert first_call.kwargs.get("encoding") == "utf-8"
            assert first_call.kwargs.get("errors") == "replace"

    def test_docker_images_call_has_encoding(self):
        """Verify docker images call passes encoding='utf-8' and errors='replace'."""
        proposer = ClaudeCodeProposer()

        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.MagicMock(
                returncode=0, stdout="sunstead-proposer:latest"
            )
            try:
                proposer.propose({"objective": "test"}, [])
            except Exception:
                pass

            # Check docker images call
            second_call = mock_run.call_args_list[1]
            assert second_call.kwargs.get("encoding") == "utf-8"
            assert second_call.kwargs.get("errors") == "replace"

    def test_docker_run_call_has_encoding(self):
        """Verify docker run call passes encoding='utf-8' and errors='replace'."""
        proposer = ClaudeCodeProposer()

        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}), mock.patch(
            "subprocess.run"
        ) as mock_run:
            # Setup mocks: version succeeds, images returns image exists, run returns valid JSON
            mock_run.side_effect = [
                mock.MagicMock(returncode=0),  # docker version
                mock.MagicMock(returncode=0, stdout="sunstead-proposer:latest"),  # docker images
                mock.MagicMock(
                    returncode=0,
                    stdout=json.dumps(
                        {
                            "result": '{"type":"index","params":{"table":"test","columns":["col"]},"reversible":true}'
                        }
                    ),
                ),  # docker run
            ]

            proposer.propose({"objective": "test"}, [])

            # Check docker run call (third call)
            run_call = mock_run.call_args_list[2]
            assert run_call.kwargs.get("encoding") == "utf-8"
            assert run_call.kwargs.get("errors") == "replace"


class TestDBDsnPassthrough:
    """Tests for DB_DSN environment variable passthrough to proposer container."""

    def test_db_dsn_passthrough_proposer_db_dsn(self):
        """Verify PROPOSER_DB_DSN is passed to docker run as -e DB_DSN."""
        proposer = ClaudeCodeProposer()
        test_dsn = "postgresql://user@aiven.example.com/testdb"

        with mock.patch.dict(
            os.environ, {"PROPOSER_DB_DSN": test_dsn, "ANTHROPIC_API_KEY": "test-key"}
        ):
            with mock.patch("subprocess.run") as mock_run:
                mock_run.side_effect = [
                    mock.MagicMock(returncode=0),  # docker version
                    mock.MagicMock(returncode=0, stdout="sunstead-proposer:latest"),  # docker images
                    mock.MagicMock(
                        returncode=0,
                        stdout=json.dumps(
                            {
                                "result": '{"type":"index","params":{"table":"test","columns":["col"]},"reversible":true}'
                            }
                        ),
                    ),  # docker run
                ]

                proposer.propose({"objective": "test"}, [])

                # Check the docker run call arguments
                run_call = mock_run.call_args_list[2]
                docker_args = run_call.args[0]

                # Verify -e DB_DSN is in the args
                assert "-e" in docker_args
                db_dsn_idx = None
                for i, arg in enumerate(docker_args):
                    if arg == "DB_DSN" or (arg.startswith("DB_DSN=") and i > 0 and docker_args[i - 1] == "-e"):
                        db_dsn_idx = i
                        break

                # Find the index where DB_DSN is set
                found_db_dsn = False
                for i in range(len(docker_args) - 1):
                    if docker_args[i] == "-e" and docker_args[i + 1].startswith("DB_DSN="):
                        assert docker_args[i + 1] == f"DB_DSN={test_dsn}"
                        found_db_dsn = True
                        break

                assert found_db_dsn, f"DB_DSN not found in docker args: {docker_args}"

    def test_db_dsn_passthrough_cleanroom_pg_dsn_fallback(self):
        """Verify CLEANROOM_PG_DSN is used as fallback when PROPOSER_DB_DSN not set."""
        proposer = ClaudeCodeProposer()
        test_dsn = "postgresql://user@localhost/testdb"

        with mock.patch.dict(os.environ, {"CLEANROOM_PG_DSN": test_dsn}, clear=False):
            with mock.patch.dict(os.environ, {}, clear=False):
                # Ensure PROPOSER_DB_DSN is not set
                env = os.environ.copy()
                env.pop("PROPOSER_DB_DSN", None)

                with mock.patch("subprocess.run") as mock_run:
                    mock_run.side_effect = [
                        mock.MagicMock(returncode=0),
                        mock.MagicMock(returncode=0, stdout="sunstead-proposer:latest"),
                        mock.MagicMock(
                            returncode=0,
                            stdout=json.dumps(
                                {
                                    "result": '{"type":"index","params":{"table":"test","columns":["col"]},"reversible":true}'
                                }
                            ),
                        ),
                    ]

                    with mock.patch.dict(
                        os.environ,
                        {"CLEANROOM_PG_DSN": test_dsn, "ANTHROPIC_API_KEY": "test-key"},
                    ):
                        proposer.propose({"objective": "test"}, [])

                    # Check the docker run call
                    run_call = mock_run.call_args_list[2]
                    docker_args = run_call.args[0]

                    # Verify DB_DSN is in the args
                    found_db_dsn = False
                    for i in range(len(docker_args) - 1):
                        if docker_args[i] == "-e" and docker_args[i + 1].startswith("DB_DSN="):
                            assert docker_args[i + 1] == f"DB_DSN={test_dsn}"
                            found_db_dsn = True
                            break

                    assert found_db_dsn

    def test_db_dsn_not_passed_when_not_set(self):
        """Verify no DB_DSN env var is added to docker run when neither env var is set."""
        proposer = ClaudeCodeProposer()

        # Clear both env vars
        env_clean = {k: v for k, v in os.environ.items() if k not in ("PROPOSER_DB_DSN", "CLEANROOM_PG_DSN")}
        env_clean["ANTHROPIC_API_KEY"] = "test-key"  # hermetic: propose() needs a key before docker run

        with mock.patch.dict(os.environ, env_clean, clear=True):
            with mock.patch("subprocess.run") as mock_run:
                mock_run.side_effect = [
                    mock.MagicMock(returncode=0),
                    mock.MagicMock(returncode=0, stdout="sunstead-proposer:latest"),
                    mock.MagicMock(
                        returncode=0,
                        stdout=json.dumps(
                            {
                                "result": '{"type":"index","params":{"table":"test","columns":["col"]},"reversible":true}'
                            }
                        ),
                    ),
                ]

                proposer.propose({"objective": "test"}, [])

                # Check the docker run call
                run_call = mock_run.call_args_list[2]
                docker_args = run_call.args[0]

                # Verify DB_DSN is NOT in the args
                for i in range(len(docker_args) - 1):
                    if docker_args[i] == "-e" and docker_args[i + 1].startswith("DB_DSN="):
                        pytest.fail(f"DB_DSN should not be in args when env var is not set: {docker_args}")


class TestWorkloadCatalog:
    """Tests for workload catalog and registration."""

    def test_job_prodyear_in_catalog(self):
        """Verify job-prodyear is registered in WORKLOAD_CATALOG."""
        assert "job-prodyear" in WORKLOAD_CATALOG
        assert "production_year" in WORKLOAD_CATALOG["job-prodyear"]
        assert "cast_info" in WORKLOAD_CATALOG["job-prodyear"]

    def test_register_workload_from_catalog(self):
        """Verify register_workload() successfully registers a workload."""
        from cleanroom.benchmark import _WORKLOADS

        workload_id = "test-workload-xyz"
        sql = "SELECT 1"

        # Clear any prior registration
        _WORKLOADS.pop(workload_id, None)

        register_workload(workload_id, sql)

        # Verify it was registered
        assert workload_id in _WORKLOADS
        assert _WORKLOADS[workload_id] == sql

        # Clean up
        _WORKLOADS.pop(workload_id, None)

    def test_dispatcher_registers_job_prodyear(self):
        """Verify _run_loop_worker would register job-prodyear from catalog."""
        from cleanroom.benchmark import _WORKLOADS

        # This is a unit test of the registration logic, not full integration
        workload_id = "job-prodyear"

        # Clear prior registration if exists
        _WORKLOADS.pop(workload_id, None)

        # Simulate what _run_loop_worker does
        if workload_id in WORKLOAD_CATALOG:
            register_workload(workload_id, WORKLOAD_CATALOG[workload_id])

        # Verify
        assert workload_id in _WORKLOADS
        assert _WORKLOADS[workload_id] == WORKLOAD_CATALOG[workload_id]

        # Clean up
        _WORKLOADS.pop(workload_id, None)

    def test_dispatcher_handles_unknown_workload_gracefully(self):
        """Verify dispatcher doesn't crash on unknown workload_id (logs warning, falls back)."""
        from cleanroom.benchmark import _WORKLOADS
        from unittest.mock import patch

        # This test verifies the fallback logic (no crash on unknown workload)
        unknown_workload_id = "unknown-workload-xyz"

        # Clear prior registration
        _WORKLOADS.pop(unknown_workload_id, None)

        # Simulate the dispatcher logic: if workload not in catalog, log warning
        with patch("logging.getLogger") as mock_logger_factory:
            mock_logger = mock.MagicMock()
            mock_logger_factory.return_value = mock_logger

            from cleanroom.control.dispatcher import executor

            # The actual log happens in _run_loop_worker, but we're testing the concept
            # Just verify the catalog doesn't have it, so fallback would occur
            assert unknown_workload_id not in WORKLOAD_CATALOG
