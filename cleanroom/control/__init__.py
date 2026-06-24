"""Control plane (Story D Phase 0) — async task dispatch and run management.

This module coordinates:
  1. Task registration (with governance via pore)
  2. Fire-and-return run dispatch (background thread)
  3. Real-time progress tracking via a progress tap
  4. Run cancellation via event flags
  5. Escalation escalation handling
  6. Result aggregation

All methods are thread-safe via the SwappableRunStore's locking.
"""

from cleanroom.control.ops import Operator, OperatorContext

__all__ = ["Operator", "OperatorContext"]
