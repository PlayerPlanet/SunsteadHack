# Plugin System (Phase-1 Stub)

This directory contains plugin infrastructure for the SunsteadHack control plane.

## Status

**Phase 0**: Control plane core (Story D) does not integrate plugins. This directory is a stub for Phase 1.

## Phase-1 Plan

When activated, plugins will provide:
- Custom proposers (candidate generators)
- Custom pores (risk evaluators)
- Custom benchmarks (performance measurement)
- Custom log clients (result storage)

## Files

- `__init__.py`: Plugin loader (stub)
- `manifest.json`: Plugin registry (stub)

See `cleanroom/control/` for the actual Phase-0 implementation.
