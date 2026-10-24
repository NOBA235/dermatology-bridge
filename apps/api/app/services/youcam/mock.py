"""Mock YouCam S2S v2.0 client returning fixture JSON from fixtures/skin_analysis_sample.json."""

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from app.config import REPO_ROOT
from app.domain.concerns import CONCERN_LIST
from app.services.youcam.client import (
    UnitBudgetLogger,
    YouCamAnalysisOutcome,
    YouCamTaskFailedError,
    parse_youcam_raw_result,
)

DEFAULT_FIXTURE_PATH = REPO_ROOT / "fixtures" / "skin_analysis_sample.json"


class MockYouCamClient:
    """Deterministic mock YouCam client returning verified fixture JSON."""

    def __init__(
        self,
        *,
        fixture_path: Path | None = None,
        budget_logger: UnitBudgetLogger | None = None,
        simulate_failure: bool = False,
    ) -> None:
        self.fixture_path = fixture_path or DEFAULT_FIXTURE_PATH
        self.budget_logger = budget_logger or UnitBudgetLogger()
        self.simulate_failure = simulate_failure
        self._task_state: dict[str, dict[str, Any]] = {}

    def _load_fixture(self) -> dict[str, Any]:
        with self.fixture_path.open("r", encoding="utf-8") as fh:
            data: dict[str, Any] = json.load(fh)
        return copy.deepcopy(data)

    async def upload_file(
        self,
        image_bytes: bytes,
        *,
        filename: str = "selfie.jpg",
        content_type: str = "image/jpeg",
    ) -> str:
        """Simulate POST /s2s/v2.0/file and return a deterministic file_id."""
        _ = content_type
        digest = hashlib.sha256(image_bytes).hexdigest()[:16]
        is_fail = (
            self.simulate_failure
            or filename.lower().startswith("fail_")
            or b"SIMULATE_YOUCAM_FAILURE" in image_bytes
        )
        prefix = "yc_file_fail_" if is_fail else "yc_file_mock_"
        return f"{prefix}{digest}"

    async def create_task(
        self,
        src_file_id: str,
        *,
        dst_actions: tuple[str, ...] = CONCERN_LIST,
        prerender: bool = True,
    ) -> str:
        """Simulate POST /s2s/v2.0/task/skin-analysis and record unit cost to CSV."""
        suffix = src_file_id.removeprefix("yc_file_mock_").removeprefix("yc_file_fail_")
        is_fail = self.simulate_failure or src_file_id.startswith("yc_file_fail_")
        task_id = f"yc_task_{'fail' if is_fail else 'mock'}_{suffix}"

        self._task_state[task_id] = {
            "src_file_id": src_file_id,
            "dst_actions": list(dst_actions),
            "prerender": prerender,
            "failed": is_fail,
        }

        self.budget_logger.log_call(
            dst_actions=dst_actions,
            task_id=task_id,
            mode="mock",
        )
        return task_id

    async def poll_task(self, task_id: str) -> dict[str, Any]:
        """Simulate GET /s2s/v2.0/task/skin-analysis/{task_id} returning fixture JSON or raising on failure."""
        state = self._task_state.get(task_id, {})
        if self.simulate_failure or state.get("failed") or task_id.startswith("yc_task_fail_"):
            failed_payload: dict[str, Any] = {
                "status": 200,
                "result": {
                    "task_id": task_id,
                    "src_file_id": state.get("src_file_id"),
                    "task_status": "error",
                    "error_code": "ERR_FACE_QUALITY_INSUFFICIENT",
                    "error_message": "Unable to complete skin analysis: insufficient lighting or face occlusion.",
                },
            }
            raise YouCamTaskFailedError(
                "Unable to complete skin analysis: insufficient lighting or face occlusion.",
                task_id=task_id,
                raw_result=failed_payload,
            )

        payload = self._load_fixture()
        result_node = payload.setdefault("result", {})
        result_node["task_id"] = task_id
        if "src_file_id" in state:
            result_node["src_file_id"] = state["src_file_id"]
        result_node["task_status"] = "success"
        return payload

    async def analyze_image(
        self,
        image_bytes: bytes,
        *,
        filename: str = "selfie.jpg",
        content_type: str = "image/jpeg",
    ) -> YouCamAnalysisOutcome:
        """Run full mock pipeline: upload_file -> create_task -> poll_task -> parse 12 concerns."""
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
