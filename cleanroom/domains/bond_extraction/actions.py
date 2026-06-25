"""Bond extraction actions — apply and rollback config deltas.

Actions maintain a stack of prior configs so rollback is exact round-trip.
The config is the ONLY mutable state; all other env keys (_extractor, _eval,
_grader, etc.) are frozen.
"""

from cleanroom.types import Candidate


class BondActions:
    """Manages extractor config state — apply and rollback via stack.

    Each apply() pushes the current config to a stack before updating.
    Each rollback() pops and restores, guaranteeing exact round-trip.
    """

    def apply(self, env: dict, candidate: Candidate) -> None:
        """Apply a config delta by updating env["_cur_config"].

        The delta is merged (shallow) into the current config. The prior config
        is pushed to a stack for exact rollback.

        Args:
            env: Domain environment dict.
            candidate: Proposed candidate with type="extractor_config" and
                params={"config_delta": {...}}.

        Raises:
            ValueError: If candidate type is not "extractor_config".
        """
        if candidate.type != "extractor_config":
            raise ValueError(
                f"BondActions.apply: expected type='extractor_config', got '{candidate.type}'"
            )

        config_delta = candidate.params.get("config_delta", {})
        if not config_delta:
            # No-op delta; still push the current config for symmetry.
            if "_config_stack" not in env:
                env["_config_stack"] = []
            env["_config_stack"].append(dict(env.get("_cur_config", {})))
            return

        # Push current config to stack before mutating.
        if "_config_stack" not in env:
            env["_config_stack"] = []
        env["_config_stack"].append(dict(env.get("_cur_config", {})))

        # Merge delta into current config (shallow merge).
        current_config = env.get("_cur_config", {})
        env["_cur_config"] = {**current_config, **config_delta}

    def rollback(self, env: dict, candidate: Candidate) -> None:
        """Rollback the last apply() by restoring the prior config from stack.

        Pops the stack and restores env["_cur_config"] exactly.

        Args:
            env: Domain environment dict.
            candidate: The candidate that was applied (unused, for symmetry with apply).
        """
        if "_config_stack" not in env or not env["_config_stack"]:
            # Stack empty: no prior config. This shouldn't happen in normal flow.
            return

        prior_config = env["_config_stack"].pop()
        env["_cur_config"] = prior_config
