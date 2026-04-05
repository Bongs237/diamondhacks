"""Planning agents."""

try:
    from .browser_runner import run_activity_discovery, run_reservation_assist
    from .browser_schemas import (
        ActivityDiscoveryResult,
        ActivityIdea,
        ReservationAttemptResult,
    )

    __all__ = [
        "ActivityDiscoveryResult",
        "ActivityIdea",
        "ReservationAttemptResult",
        "run_activity_discovery",
        "run_reservation_assist",
    ]
except ImportError:
    # browser-use not installed — browser agents unavailable
    __all__ = []
