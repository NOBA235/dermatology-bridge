# YouCam Skin AI S2S v2.0 API Contract

> **For clinician review — not a diagnosis.**
>
> This file is the canonical source of truth for the YouCam Skin Analysis S2S v2.0 API integration in Dermatology Bridge. Any delta observed in the Perfect Corp API Playground must be recorded here before modifying application code.

## Base URL & Authentication

- **Base URL**: `YOUCAM_BASE_URL` (default `https://yce-api-01.perfectcorp.com`)
- **Authentication**: `Authorization: Bearer <YOUCAM_API_KEY>`
- **Budget Gate**: Live calls are strictly gated behind `ALLOW_LIVE_CALLS=true`. Every task creation call logs `len(dst_actions)` units to `logs/unit_budget.csv` against the hard 1,000-unit budget.

---

## Frozen Concern List (`ANALYSIS_VERSION = 1`)

The `dst_actions` array sent to YouCam is frozen at 12 actions and persisted per visit as `visits.analysis_version = 1`:

| # | Action (`dst_actions`) | Clinical Label | Direction of Good (`CONCERN_DIRECTION`) | Interpretation |
|---|------------------------|----------------|-----------------------------------------|----------------|
| 1 | `acne` | Acne & Blemishes | `lower_is_better` | Rising score = worsening; falling score = improving |
| 2 | `wrinkle` | Wrinkles & Fine Lines | `lower_is_better` | Rising score = worsening; falling score = improving |
| 3 | `pores` | Visible Pores | `lower_is_better` | Rising score = worsening; falling score = improving |
| 4 | `texture` | Skin Texture Roughness | `lower_is_better` | Rising score = worsening; falling score = improving |
| 5 | `redness` | Erythema / Redness | `lower_is_better` | Rising score = worsening; falling score = improving |
| 6 | `oiliness` | Sebum / Oiliness | `lower_is_better` | Rising score = worsening; falling score = improving |
| 7 | `moisture` | Skin Moisture | `higher_is_better` | Rising score = improving; falling score = worsening |
| 8 | `radiance` | Skin Radiance | `higher_is_better` | Rising score = improving; falling score = worsening |
| 9 | `firmness` | Skin Firmness | `higher_is_better` | Rising score = improving; falling score = worsening |
| 10 | `dark_circle_v2` | Periorbital Dark Circles | `lower_is_better` | Rising score = worsening; falling score = improving |
| 11 | `dark_spot` | Hyperpigmentation / Spots | `lower_is_better` | Rising score = worsening; falling score = improving |
| 12 | `skin_tone` | Skin Tone Evenness | `higher_is_better` | Rising score = improving; falling score = worsening |

---

## Endpoint Specifications

### 1. Upload Source Image — `POST /s2s/v2.0/file`

Uploads or initializes a patient selfie in YouCam temporary storage and returns `result.file_id`.

**Request (`application/json` or `multipart/form-data`)**:
```json
{
  "files": [
    {
      "content_type": "image/jpeg",
      "file_name": "visit_capture.jpg",
      "file_size": 184320
    }
  ]
}
```
*(Note: When `requests[0].url` presigned PUT URL is returned by S2S v2.0 two-step upload, the client immediately PUTs the image binary to the presigned target before returning `file_id`. Single-step multipart upload also returns `result.file_id`.)*

**Verified Response (`200 OK`)**:
```json
{
  "status": 200,
  "result": {
    "file_id": "yc_file_9f8a7b6c5d4e3f2a1b0c",
    "requests": []
  }
}
```

---

### 2. Create Skin Analysis Task — `POST /s2s/v2.0/task/skin-analysis`

Starts an asynchronous skin analysis job for the 12 frozen `dst_actions`. Consumes `len(dst_actions)` = 12 API units.

**Request (`application/json`)**:
```json
{
  "src_file_id": "yc_file_9f8a7b6c5d4e3f2a1b0c",
  "dst_actions": [
    "acne",
    "wrinkle",
    "pores",
    "texture",
    "redness",
    "oiliness",
    "moisture",
    "radiance",
    "firmness",
    "dark_circle_v2",
    "dark_spot",
    "skin_tone"
  ],
  "prerender": true,
  "format": "json"
}
```

**Verified Response (`200 OK`)**:
```json
{
  "status": 200,
  "result": {
    "task_id": "yc_task_4e3d2c1b0a9f8e7d6c5b"
  }
}
```

---

### 3. Poll Skin Analysis Task — `GET /s2s/v2.0/task/skin-analysis/{task_id}`

Polls task execution with exponential backoff (`2s` initial delay → `30s` cap, `90s` total timeout). Polling does not consume units.

**Verified Response (`200 OK` — Completed)**:
```json
{
  "status": 200,
  "result": {
    "task_id": "yc_task_4e3d2c1b0a9f8e7d6c5b",
    "task_status": "success",
    "analysis_version": 1,
    "results": [
      {
        "concern": "acne",
        "score": 42.5,
        "ui_score": 42.5,
        "raw_score": 0.425,
        "mask_url": "https://storage.youcam.local/ephemeral/masks/yc_task_4e3d2c1b0a9f8e7d6c5b/acne.png"
      }
    ]
  }
}
```

**Task Status Values (`result.task_status`)**:
- `"running"` / `"pending"` / `"polling"` — task is still in progress; continue polling with exponential backoff.
- `"success"` — task completed; `result.results[]` contains one entry per requested `dst_actions` item (`concern`, `score` in `[0, 100]`, `mask_url`).
- `"error"` / `"failed"` — task failed (e.g., face occlusion, poor lighting, invalid image); `result.error_code` and `result.error_message` provide failure reason.

---

## Verified Deltas & Normalization Notes

1. **Envelope field (`result` vs `data`)**: Some S2S v2.0 Playground examples wrap responses in `result` (`result.file_id`, `result.task_id`, `result.task_status`, `result.results[]`), while certain SDK wrappers alias `result` as `data`. The client normalizer reads `payload.get("result") or payload.get("data")` while storing the untouched original JSON in `visits.raw_result`.
2. **Score field (`score` vs `ui_score`)**: Individual items in `result.results[]` may provide `score` or `ui_score` on a `0..100` scale and `concern` or `type` for the action key. Both keys are present in `fixtures/skin_analysis_sample.json` and accepted by the parser.
3. **Ephemeral `mask_url`**: Mask URLs returned in `result.results[].mask_url` are short-lived presigned URLs. At visit-creation time (`POST /api/visits`), each `mask_url` is fetched/cached into private storage and recorded in `concern_scores.mask_storage_key` alongside `concern_scores.mask_url`. Image or mask URLs are never written to application logs.
