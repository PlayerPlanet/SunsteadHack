"""Plugin system stub for Phase 1.

Phase 0: No plugins are loaded. This module is a placeholder.

When Phase 1 activates, this will provide:
  - load_proposer(plugin_name) -> proposer instance
  - load_pore(plugin_name) -> pore instance
  - load_benchmark(plugin_name) -> benchmark instance
  - load_logclient(plugin_name) -> logclient instance
"""


def load_proposer(plugin_name: str):
    """Load a proposer plugin. Phase-1 stub."""
    raise NotImplementedError("Plugins not available in Phase 0")


def load_pore(plugin_name: str):
    """Load a pore plugin. Phase-1 stub."""
    raise NotImplementedError("Plugins not available in Phase 0")


def load_benchmark(plugin_name: str):
    """Load a benchmark plugin. Phase-1 stub."""
    raise NotImplementedError("Plugins not available in Phase 0")


def load_logclient(plugin_name: str):
    """Load a logclient plugin. Phase-1 stub."""
    raise NotImplementedError("Plugins not available in Phase 0")
