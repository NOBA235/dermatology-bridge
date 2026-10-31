"""YouCam S2S v2.0 live API client with exponential backoff polling (2s -> 30s cap, 90s timeout).

Never logs image URLs or mask URLs.
"""

import asyncio
from collections.abc import Callable, Coroutine
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import io
import json
from pathlib import Path
import time
from typing import Any, Protocol
import zipfile

import httpx

from app.config import REPO_ROOT
from app.domain.concerns import (
    ANALYSIS_VERSION,
    CONCERN_DIRECTION,
    CONCERN_LIST,
    score_to_severity,
)

UNIT_BUDGET_LIMIT = 1000
DEFAULT_UNIT_BUDGET_CSV = REPO_ROOT / "logs" / "unit_budget.csv"

INITIAL_POLL_INTERVAL_SECONDS = 2.0
MAX_POLL_INTERVAL_SECONDS = 30.0
POLL_TIMEOUT_SECONDS = 90.0

# Mapping between frozen internal concern keys and Perfect Corp S2S v2.0 SD action names
_INTERNAL_TO_YOUCAM_ACTION: dict[str, str] = {
    "pores": "pore",
    "dark_spot": "age_spot",
    "skin_tone": "eye_bag",
}
_YOUCAM_TO_INTERNAL_ACTION: dict[str, str] = {
    v: k for k, v in _INTERNAL_TO_YOUCAM_ACTION.items()
}


class YouCamError(Exception):
    """Base exception for YouCam S2S API errors."""


class YouCamTaskFailedError(YouCamError):
    """Raised when a YouCam skin-analysis task transitions to 'error' or 'failed'."""

    def __init__(
        self,
        message: str,
        *,
        task_id: str | None = None,
        raw_result: dict[str, Any] | None = None,
    ) -> None:
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


def _normalize_live_score_info(
    score_info: dict[str, Any],
    masks_list: list[Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Normalize Perfect Corp score_info.json dictionary into internal concern keys."""
    by_concern: dict[str, dict[str, Any]] = {}
    mask_by_concern = {
        m.get("concern"): m.get("mask_url")
        for m in (masks_list or [])
        if isinstance(m, dict) and isinstance(m.get("concern"), str)
    }

    source_map = score_info.get("concerns")
    if not isinstance(source_map, dict):
        source_map = score_info

    for raw_key, c_val in source_map.items():
        if not isinstance(c_val, dict):
            continue
        internal_key = _YOUCAM_TO_INTERNAL_ACTION.get(raw_key, raw_key)
        if internal_key not in CONCERN_DIRECTION:
            continue

        raw_val = c_val.get("score")
        if raw_val is None:
            raw_val = c_val.get("ui_score")
        if raw_val is None:
            raw_val = c_val.get("raw_score")
        if raw_val is None:
            continue

        num_val = float(raw_val)
        # Live YouCam score_info.json reports 0..100 health scores (100 = clearest skin)
        # with 'output_mask_name' or 'raw_score' > 1. Convert to symptom burden for lower_is_better.
        is_live_health_scale = (
            "output_mask_name" in c_val
            or "ui_score" in c_val
            and "concern" not in c_val
            and "type" not in c_val
        )
        if (
            is_live_health_scale
            and CONCERN_DIRECTION[internal_key] == "lower_is_better"
        ):
            num_val = max(0.0, min(100.0, 100.0 - num_val))

        by_concern[internal_key] = {
            "concern": internal_key,
            "score": round(num_val, 2),
            "mask_url": c_val.get("mask_url") or mask_by_concern.get(internal_key),
        }

    return by_concern


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
                internal_key = _YOUCAM_TO_INTERNAL_ACTION.get(concern_key, concern_key)
                by_concern[internal_key] = item
    elif isinstance(results_node, dict):
        score_info = (
            envelope.get("score_info")
            or results_node.get("score_info")
            or results_node
        )
        masks_list = results_node.get("masks", [])
        if isinstance(score_info, dict):
            by_concern.update(_normalize_live_score_info(score_info, masks_list))

    if not by_concern and isinstance(envelope.get("score_info"), dict):
        by_concern.update(_normalize_live_score_info(envelope["score_info"]))

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
        """POST /s2s/v2.0/file -> returns file_id and uploads binary to presigned S3 URL."""
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

            # Support Perfect Corp S2S v2.0 nested data.files[0] structure
            files_list = result.get("files")
            if isinstance(files_list, list) and files_list and isinstance(files_list[0], dict):
                first_file = files_list[0]
                if not file_id:
                    file_id = first_file.get("file_id")
                if not requests_list:
                    requests_list = first_file.get("requests") or []

            if not file_id and requests_list and isinstance(requests_list[0], dict):
                file_id = requests_list[0].get("file_id")

            # If S2S v2.0 returns a presigned upload target in requests[0].url, PUT the bytes
            if requests_list and isinstance(requests_list[0], dict):
                put_url = requests_list[0].get("url")
                raw_put_headers = requests_list[0].get("headers") or {
                    "Content-Type": content_type
                }
                put_headers = {str(k): str(v) for k, v in raw_put_headers.items()}
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
        """POST /s2s/v2.0/task/skin-analysis -> returns task_id and logs unit cost."""
        live_actions = [_INTERNAL_TO_YOUCAM_ACTION.get(a, a) for a in dst_actions]
        request_body: dict[str, Any] = {
            "src_file_id": src_file_id,
            "dst_actions": live_actions,
            "format": "json",
        }
        if prerender:
            request_body["miniserver_args"] = {"enable_mask_overlay": True}

        async with self._client_context() as client:
            resp = await client.post(
                f"{self.base_url}/s2s/v2.0/task/skin-analysis",
                headers=self._headers(),
                json=request_body,
            )
            if resp.status_code >= 400:
                detail = resp.text[:300]
                raise YouCamError(
                    f"YouCam create_task failed with HTTP {resp.status_code}: {detail}"
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
                    results_node = result.get("results")
                    if isinstance(results_node, dict) and isinstance(
                        results_node.get("url"), str
                    ):
                        bundle_url = results_node["url"]
                        await self._hydrate_results_bundle(client, result, bundle_url)
                    return raw_payload

                if task_status in ("error", "failed"):
                    err_msg = (
                        result.get("error_message")
                        or result.get("error")
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

    async def _hydrate_results_bundle(
        self,
        client: httpx.AsyncClient,
        result_envelope: dict[str, Any],
        bundle_url: str,
    ) -> None:
        """Download and unpack YouCam presigned ZIP or JSON result bundle into score_info."""
        bundle_resp = await client.get(bundle_url)
        if bundle_resp.status_code >= 400:
            raise YouCamError(
                f"Failed to download YouCam result bundle (HTTP {bundle_resp.status_code})"
            )
        content = bundle_resp.content
        if content.startswith(b"PK\x03\x04"):
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                for name in zf.namelist():
                    if name.endswith("score_info.json") or name.endswith(".json"):
                        raw_json = json.loads(zf.read(name).decode("utf-8"))
                        if isinstance(raw_json, dict):
                            result_envelope["score_info"] = raw_json
                            break
        else:
            raw_json = bundle_resp.json()
            if isinstance(raw_json, dict):
                result_envelope["score_info"] = raw_json

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
        transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0")
        return httpx.AsyncClient(transport=transport, timeout=30.0)


class _BorrowedAsyncClient:
    """Context manager wrapper that does not close an injected AsyncClient."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def __aenter__(self) -> httpx.AsyncClient:
        return self.client

    async def __aexit__(self, *_args: Any) -> None:
        return None
