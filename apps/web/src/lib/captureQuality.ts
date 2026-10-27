/**
 * Client-side guided selfie quality gate for /capture/[token].
 *
 * Rejects frames with:
 * - no_face (faceCount === 0)
 * - multiple_faces (faceCount > 1)
 * - too_dark (meanBrightness < MIN_BRIGHTNESS)
 * - face_too_small (faceAreaRatio < MIN_FACE_AREA_RATIO)
 * - eyewear_occlusion (hasEyewearOcclusion === true)
 *
 * For clinician review — not a diagnosis.
 */

export type CaptureRejectionReason =
  | "no_face"
  | "multiple_faces"
  | "too_dark"
  | "face_too_small"
  | "eyewear_occlusion";

export interface CaptureFrameMetrics {
  faceCount: number;
  meanBrightness: number; // 0..255 luminance
  faceAreaRatio: number; // 0.0..1.0 fraction of frame area
  hasEyewearOcclusion?: boolean;
}

export interface CaptureQualityVerdict {
  passed: boolean;
  reason: CaptureRejectionReason | null;
  message: string;
}

export const MIN_BRIGHTNESS = 65;
export const MIN_FACE_AREA_RATIO = 0.18;

export function evaluateCaptureFrame(
  metrics: CaptureFrameMetrics
): CaptureQualityVerdict {
  if (metrics.faceCount <= 0) {
    return {
      passed: false,
      reason: "no_face",
      message: "No face detected. Center your face inside the oval guide.",
    };
  }

  if (metrics.faceCount > 1) {
    return {
      passed: false,
      reason: "multiple_faces",
      message:
        "Multiple faces detected. Ensure only the patient is visible in the frame.",
    };
  }

  if (metrics.meanBrightness < MIN_BRIGHTNESS) {
    return {
      passed: false,
      reason: "too_dark",
      message:
        "Lighting is too dark. Move toward even front-facing lighting before capturing.",
    };
  }

  if (metrics.faceAreaRatio < MIN_FACE_AREA_RATIO) {
    return {
      passed: false,
      reason: "face_too_small",
      message:
        "Face is too small in frame. Hold the camera closer so your face fills the guide.",
    };
  }

  if (metrics.hasEyewearOcclusion) {
    return {
      passed: false,
      reason: "eyewear_occlusion",
      message:
        "Eyewear occlusion detected. Please remove glasses and clear hair from the forehead.",
    };
  }

  return {
    passed: true,
    reason: null,
    message:
      "Front-facing face, adequate brightness, and clear framing verified.",
  };
}

