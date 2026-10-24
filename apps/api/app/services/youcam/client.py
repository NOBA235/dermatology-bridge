"""YouCam S2S v2.0 live API client with exponential backoff polling (2s -> 30s cap, 90s timeout).

Never logs image URLs or mask URLs.
"""

import asyncio
from collections.abc import Callable, Coroutine
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import time
from typing import Any, Protocol

import httpx

from app.config import REPO_ROOT
from app.domain.concerns import ANALYSIS_VERSION, CONCERN_LIST, score_to_severity

UNIT_BUDGET_LIMIT = 1000
DEFAULT_UNIT_BUDGET_CSV = REPO_ROOT / "logs" / "unit_budget.csv"

INITIAL_POLL_INTERVAL_SECONDS = 2.0
MAX_POLL_INTERVAL_SECONDS = 30.0
POLL_TIMEOUT_SECONDS = 90.0


class YouCamError(Exception):
    """Base exception for YouCam S2S API errors."""


class YouCamTaskFailedError(YouCamError):
    """Raised when a YouCam skin-analysis task transitions to 'error' or 'failed'."""

    def __init__(self, message: str, *, task_id: str | None = None, raw_result: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.task_id = task_id
        self.raw_result = raw_result


class YouCamTimeoutError(YouCamError):
    """Raised when polling exceeds the 90-second timeout."""

    def __init__(self, message: str, *, task_id: str | None = None) -> None:
        super().__init__(message)
        self.task_id = task_id


@dataclass(frozen=True)
class ParsedConcernScore:
    """Normalized concern score extracted from a YouCam raw_result payload."""

    concern: str
    score: Decimal
    severity: str
    mask_url: str | None


@dataclass(frozen=True)
class YouCamAnalysisOutcome:
    """Full result of upload -> create_task -> poll_task."""

    file_id: str
    task_id: str
    raw_result: dict[str, Any]
    concern_scores: list[ParsedConcernScore]


class UnitBudgetLogger:
    """Tracks YouCam dst_actions unit consumption in logs/unit_budget.csv."""

    CSV_HEADERS = (
        "timestamp",
        "mode",
        "task_id",
        "actions_count",
        "cumulative_units",
        "remaining_budget",
    )

    def __init__(
        self,
        csv_path: Path | None = None,
        budget_limit: int = UNIT_BUDGET_LIMIT,
    ) -> None:
        self.csv_path = csv_path or DEFAULT_UNIT_BUDGET_CSV
        self.budget_limit = budget_limit

    def log_call(
        self,
        *,
        dst_actions: tuple[str, ...] | list[str],
        task_id: str,
        mode: str,
    ) -> dict[str, int | str]:
        """Count len(dst_actions) and append arithmetic row to logs/unit_budget.csv."""
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        actions_count = len(dst_actions)
        previous_cumulative = self._read_cumulative_units()
        cumulative_units = previous_cumulative + actions_count
        remaining_budget = self.budget_limit - cumulative_units

        file_exists = self.csv_path.exists() and self.csv_path.stat().st_size > 0
        timestamp = datetime.now(timezone.utc).isoformat()

        with self.csv_path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            if not file_exists:
                writer.writerow(self.CSV_HEADERS)
            writer.writerow(
                [
                    timestamp,
                    mode,
                    task_id,
                    actions_count,
                    cumulative_units,
                    remaining_budget,
                ]
            )

        return {
            "timestamp": timestamp,
            "mode": mode,
            "task_id": task_id,
            "actions_count": actions_count,
            "cumulative_units": cumulative_units,
            "remaining_budget": remaining_budget,
        }

    def _read_cumulative_units(self) -> int:
        if not self.csv_path.exists() or self.csv_path.stat().st_size == 0:
            return 0
        with self.csv_path.open("r", newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            last_cumulative = 0
            for row in reader:
                try:
                    last_cumulative = int(row.get("cumulative_units", 0))
                except (TypeError, ValueError):
                    continue
            return last_cumulative


def compute_backoff_delay(
    attempt: int,
    *,
    initial_delay: float = INITIAL_POLL_INTERVAL_SECONDS,
    max_delay: float = MAX_POLL_INTERVAL_SECONDS,
) -> float:
    """Compute exponential backoff delay: 2s -> 4s -> 8s -> 16s -> 30s cap."""
    raw_delay = initial_delay * (2 ** max(0, attempt))
    return min(raw_delay, max_delay)


def parse_youcam_raw_result(raw_result: dict[str, Any]) -> list[ParsedConcernScore]:
    """Extract and validate all 12 frozen concerns from a YouCam S2S v2.0 raw payload."""
    envelope = raw_result.get("result") or raw_result.get("data") or {}
    results_node = envelope.get("results")

    by_concern: dict[str, dict[str, Any]] = {}

    if isinstance(results_node, list):
        for item in results_node:
            if not isinstance(item, dict):
                continue
            concern_key = item.get("concern") or item.get("type")
            if isinstance(concern_key, str):
                by_concern[concern_key] = item
    elif isinstance(results_node, dict):
        # Support alternative score_info.concerns + masks shape documented in contract
        score_info = results_node.get("score_info", {})
        concerns_map = score_info.get("concerns", {})
        masks_list = results_node.get("masks", [])
        mask_by_concern = {
            m.get("concern"): m.get("mask_url")
            for m in masks_list
            if isinstance(m, dict) and isinstance(m.get("concern"), str)
        }
        if isinstance(concerns_map, dict):
            for c_key, c_val in concerns_map.items():
                if isinstance(c_val, dict):
                    by_concern[c_key] = {
                        "concern": c_key,
                        "score": c_val.get("score") or c_val.get("ui_score"),
                        "mask_url": c_val.get("mask_url") or mask_by_concern.get(c_key),
                    }

    parsed: list[ParsedConcernScore] = []
    missing: list[str] = []

    for concern in CONCERN_LIST:
        entry = by_concern.get(concern)
        if entry is None:
            missing.append(concern)
            continue
        raw_score = entry.get("score", entry.get("ui_score"))
        if raw_score is None:
            missing.append(concern)
            continue
        score_dec = Decimal(str(raw_score)).quantize(Decimal("0.01"))
        severity = score_to_severity(concern, score_dec)
        mask_url = entry.get("mask_url")
        parsed.append(
            ParsedConcernScore(
                concern=concern,
                score=score_dec,
                severity=severity,
                mask_url=str(mask_url) if mask_url else None,
            )
        )

    if missing:
        raise YouCamError(
            f"YouCam payload missing required frozen concerns: {', '.join(missing)}"
        )

    return parsed


class YouCamClientProtocol(Protocol):
    """Protocol implemented by both LiveYouCamClient and MockYouCamClient."""

    async def upload_file(
        self,
        image_bytes: bytes,
        *,
        filename: str = "selfie.jpg",
        content_type: str = "image/jpeg",
    ) -> str:
        """Upload source selfie and return file_id."""

    async def create_task(
        self,
        src_file_id: str,
        *,
        dst_actions: tuple[str, ...] = CONCERN_LIST,
        prerender: bool = True,
    ) -> str:
        """Create skin-analysis task for dst_actions and return task_id."""

    async def poll_task(self, task_id: str) -> dict[str, Any]:
        """Poll task until success, failure, or timeout, returning untouched raw_result JSON."""

    async def analyze_image(
        self,
        image_bytes: bytes,
        *,
        filename: str = "selfie.jpg",
        content_type: str = "image/jpeg",
    ) -> YouCamAnalysisOutcome:
        """Execute upload -> create_task -> poll_task -> parse all 12 concerns."""


class LiveYouCamClient:
    """Live YouCam S2S v2.0 HTTP client (only instantiated when ALLOW_LIVE_CALLS=true)."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        budget_logger: UnitBudgetLogger | None = None,
        http_client: httpx.AsyncClient | None = None,
        sleep_fn: Callable[[float], Coroutine[Any, Any, None]] = asyncio.sleep,
        clock_fn: Callable[[], float] = time.monotonic,
        poll_timeout_seconds: float = POLL_TIMEOUT_SECONDS,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("LiveYouCamClient requires a non-empty YouCam API key.")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.budget_logger = budget_logger or UnitBudgetLogger()
        self._http_client = http_client
        self._sleep_fn = sleep_fn
        self._clock_fn = clock_fn
        self.poll_timeout_seconds = poll_timeout_seconds

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }

    async def upload_file(
        self,
        image_bytes: bytes,
        *,
        filename: str = "selfie.jpg",
        content_type: str = "image/jpeg",
    ) -> str:
        """POST /s2s/v2.0/file -> returns result.file_id."""
        payload = {
            "files": [
                {
                    "content_type": content_type,
                    "file_name": filename,
                    "file_size": len(image_bytes),
                }
            ]
        }
        async with self._client_context() as client:
            resp = await client.post(
                f"{self.base_url}/s2s/v2.0/file",
                headers=self._headers(),
                json=payload,
            )
            if resp.status_code >= 400:
                raise YouCamError(
                    f"YouCam file upload failed with HTTP {resp.status_code}"
                )
            body = resp.json()
            result = body.get("result") or body.get("data") or {}
            file_id = result.get("file_id")
            requests_list = result.get("requests") or []
            if not file_id and requests_list and isinstance(requests_list[0], dict):
                file_id = requests_list[0].get("file_id")

            # If S2S v2.0 returns a presigned upload target in requests[0].url, PUT the bytes
            if requests_list and isinstance(requests_list[0], dict):
                put_url = requests_list[0].get("url")
                put_headers = requests_list[0].get("headers") or {"Content-Type": content_type}
                if put_url:
                    put_resp = await client.put(
                        put_url, content=image_bytes, headers=put_headers
                    )
                    if put_resp.status_code >= 400:
                        raise YouCamError(
                            f"YouCam presigned binary upload failed with HTTP {put_resp.status_code}"
                        )

            if not file_id:
                raise YouCamError("YouCam /s2s/v2.0/file response missing result.file_id")
            return str(file_id)

    async def create_task(
        self,
        src_file_id: str,
        *,
        dst_actions: tuple[str, ...] = CONCERN_LIST,
        prerender: bool = True,
    ) -> str:
        """POST /s2s/v2.0/task/skin-analysis -> returns result.task_id and logs unit cost."""
        request_body = {
            "src_file_id": src_file_id,
            "dst_actions": list(dst_actions),
            "prerender": prerender,
            "analysis_version": ANALYSIS_VERSION,
            "format": "json",
        }
        async with self._client_context() as client:
            resp = await client.post(
                f"{self.base_url}/s2s/v2.0/task/skin-analysis",
                headers=self._headers(),
                json=request_body,
            )
            if resp.status_code >= 400:
                raise YouCamError(
                    f"YouCam create_task failed with HTTP {resp.status_code}"
                )
            body = resp.json()
            result = body.get("result") or body.get("data") or {}
            task_id = result.get("task_id")
            if not task_id:
                raise YouCamError(
                    "YouCam /s2s/v2.0/task/skin-analysis response missing result.task_id"
                )
            task_id_str = str(task_id)
            self.budget_logger.log_call(
                dst_actions=dst_actions,
                task_id=task_id_str,
                mode="live",
            )
            return task_id_str

    async def poll_task(self, task_id: str) -> dict[str, Any]:
        """GET /s2s/v2.0/task/skin-analysis/{task_id} with 2s -> 30s backoff and 90s timeout."""
        start_time = self._clock_fn()
        attempt = 0

        async with self._client_context() as client:
            while True:
                resp = await client.get(
                    f"{self.base_url}/s2s/v2.0/task/skin-analysis/{task_id}",
                    headers=self._headers(),
                )
                if resp.status_code >= 400:
                    raise YouCamError(
                        f"YouCam poll_task HTTP error {resp.status_code} for task {task_id}"
                    )

                raw_payload: dict[str, Any] = resp.json()
                result = raw_payload.get("result") or raw_payload.get("data") or {}
                task_status = str(
                    result.get("task_status") or raw_payload.get("task_status") or ""
                ).lower()

                if task_status == "success":
                    return raw_payload

                if task_status in ("error", "failed"):
                    err_msg = (
                        result.get("error_message")
                        or result.get("error_code")
                        or "YouCam skin-analysis task failed."
                    )
                    raise YouCamTaskFailedError(
                        str(err_msg),
                        task_id=task_id,
                        raw_result=raw_payload,
                    )

                elapsed = self._clock_fn() - start_time
                delay = compute_backoff_delay(attempt)
                if elapsed + delay > self.poll_timeout_seconds:
                    raise YouCamTimeoutError(
                        f"YouCam task {task_id} timed out after {elapsed:.1f}s (limit {self.poll_timeout_seconds}s)",
                        task_id=task_id,
                    )

                await self._sleep_fn(delay)
                attempt += 1

    async def analyze_image(
        self,
        image_bytes: bytes,
        *,
        filename: str = "selfie.jpg",
        content_type: str = "image/jpeg",
    ) -> YouCamAnalysisOutcome:
        """Run full pipeline: upload_file -> create_task -> poll_task -> parse 12 concerns."""
        file_id = await self.upload_file(
            image_bytes, filename=filename, content_type=content_type
        )
        task_id = await self.create_task(file_id, dst_actions=CONCERN_LIST, prerender=True)
        raw_result = await self.poll_task(task_id)
        concern_scores = parse_youcam_raw_result(raw_result)
        return YouCamAnalysisOutcome(
            file_id=file_id,
            task_id=task_id,
            raw_result=raw_result,
            concern_scores=concern_scores,
        )

    def _client_context(self) -> Any:
        if self._http_client is not None:
            return _BorrowedAsyncClient(self._http_client)
        return httpx.AsyncClient(timeout=30.0)


class _BorrowedAsyncClient:
    """Context manager wrapper that does not close an injected AsyncClient."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def __aenter__(self) -> httpx.AsyncClient:
        return self.client

    async def __aexit__(self, *_args: Any) -> None:
        return None
