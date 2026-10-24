"""YouCam service factory and exports."""

from pathlib import Path

from app.config import Settings, get_settings
from app.services.youcam.client import (
    DEFAULT_UNIT_BUDGET_CSV,
    INITIAL_POLL_INTERVAL_SECONDS,
    MAX_POLL_INTERVAL_SECONDS,
    POLL_TIMEOUT_SECONDS,
    LiveYouCamClient,
    ParsedConcernScore,
    UnitBudgetLogger,
    YouCamAnalysisOutcome,
    YouCamClientProtocol,
    YouCamError,
    YouCamTaskFailedError,
    YouCamTimeoutError,
    compute_backoff_delay,
    parse_youcam_raw_result,
)
from app.services.youcam.mock import MockYouCamClient


def get_youcam_client(
    *,
    settings: Settings | None = None,
    budget_csv_path: Path | None = None,
) -> YouCamClientProtocol:
    """Factory selecting LiveYouCamClient or MockYouCamClient based on ALLOW_LIVE_CALLS."""
    resolved_settings = settings or get_settings()
    budget_logger = UnitBudgetLogger(csv_path=budget_csv_path or DEFAULT_UNIT_BUDGET_CSV)

    if resolved_settings.ALLOW_LIVE_CALLS:
        return LiveYouCamClient(
            base_url=resolved_settings.YOUCAM_BASE_URL,
            api_key=resolved_settings.YOUCAM_API_KEY,
            budget_logger=budget_logger,
        )
    return MockYouCamClient(budget_logger=budget_logger)


__all__ = [
    "DEFAULT_UNIT_BUDGET_CSV",
    "INITIAL_POLL_INTERVAL_SECONDS",
    "MAX_POLL_INTERVAL_SECONDS",
    "POLL_TIMEOUT_SECONDS",
    "LiveYouCamClient",
    "MockYouCamClient",
    "ParsedConcernScore",
    "UnitBudgetLogger",
    "YouCamAnalysisOutcome",
    "YouCamClientProtocol",
    "YouCamError",
    "YouCamTaskFailedError",
    "YouCamTimeoutError",
    "compute_backoff_delay",
    "get_youcam_client",
    "parse_youcam_raw_result",
]
