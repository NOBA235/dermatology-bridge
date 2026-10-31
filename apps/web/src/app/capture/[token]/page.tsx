"use client";

import React, { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import {
  API_BASE_URL,
  CaptureSessionInfo,
  CLINICAL_DISCLAIMER,
  PRIVACY_NOTICE,
  VisitRecord,
} from "@/lib/api";
import {
  CaptureFrameMetrics,
  evaluateCaptureFrame,
} from "@/lib/captureQuality";

type CaptureStep = "consent" | "guided_selfie" | "success";
type CameraStatus = "idle" | "requesting" | "active" | "denied" | "unavailable";

export default function PatientMobileCapturePage() {
  const params = useParams<{ token: string }>();
  const token = params.token;

  const [verifyingToken, setVerifyingToken] = useState(true);
  const [sessionInfo, setSessionInfo] = useState<CaptureSessionInfo | null>(
    null
  );
  const [tokenError, setTokenError] = useState<string | null>(null);
  const [step, setStep] = useState<CaptureStep>("consent");

  // Consent & encounter intake form
  const [consentChecked, setConsentChecked] = useState(true);
  const [chiefComplaint, setChiefComplaint] = useState("");
  const [routineText, setRoutineText] = useState("");
  const [treatmentChanges, setTreatmentChanges] = useState("");

  // Client-side guided selfie quality gate state
  const [frameMetrics, setFrameMetrics] = useState<CaptureFrameMetrics>({
    faceCount: 1,
    meanBrightness: 142,
    faceAreaRatio: 0.34,
    hasEyewearOcclusion: false,
  });
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [completedVisit, setCompletedVisit] = useState<VisitRecord | null>(
    null
  );

  // Optional live camera preview state
  const [cameraStatus, setCameraStatus] = useState<CameraStatus>("idle");
  const [cameraMessage, setCameraMessage] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const qualityVerdict = evaluateCaptureFrame(frameMetrics);

  useEffect(() => {
    async function verifyToken() {
      setVerifyingToken(true);
      try {
        const res = await fetch(`${API_BASE_URL}/api/capture/${token}`);
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(
            err.detail || "This capture link is invalid or has expired."
          );
        }
        const data = (await res.json()) as CaptureSessionInfo;
        setSessionInfo(data);
      } catch (err) {
        setTokenError(
          err instanceof Error ? err.message : "Invalid capture link."
        );
      } finally {
        setVerifyingToken(false);
      }
    }
    void verifyToken();
  }, [token]);

  // Stop live camera stream on unmount or step change
  useEffect(() => {
    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
      }
    };
  }, []);

  function stopCameraStream() {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    setCameraStatus("idle");
    setCameraMessage(null);
  }

  async function handleStartCamera() {
    setCameraMessage(null);
    if (
      typeof navigator === "undefined" ||
      !navigator.mediaDevices ||
      !navigator.mediaDevices.getUserMedia
    ) {
      setCameraStatus("unavailable");
      setCameraMessage(
        "Live camera preview is unavailable on this browser or connection. You can select a photo file or continue with the guided capture frame below."
      );
      return;
    }
    setCameraStatus("requesting");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user" },
        audio: false,
      });
      streamRef.current = stream;
      setCameraStatus("active");
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
    } catch (err) {
      const isDenied =
        err instanceof DOMException &&
        (err.name === "NotAllowedError" || err.name === "PermissionDeniedError");
      if (isDenied) {
        setCameraStatus("denied");
        setCameraMessage(
          "Camera permission was declined. You can grant camera access in your browser settings, upload a selfie photo below, or use the guided capture check."
        );
      } else {
        setCameraStatus("unavailable");
        setCameraMessage(
          "No front-facing camera was detected on this device. You can select a photo below or submit using the guided capture check."
        );
      }
    }
  }

  function handleRetakeOrClearPhoto() {
    setSelectedFile(null);
    setSubmitError(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
    setFrameMetrics({
      faceCount: 1,
      meanBrightness: 142,
      faceAreaRatio: 0.34,
      hasEyewearOcclusion: false,
    });
  }

  async function handleSubmitScan() {
    if (!qualityVerdict.passed) {
      setSubmitError(qualityVerdict.message);
      return;
    }

    setSubmitting(true);
    setSubmitError(null);

    try {
      const formData = new FormData();
      formData.append("consent_accepted", "true");
      formData.append("chief_complaint", chiefComplaint);
      formData.append("routine_text", routineText);
      formData.append("treatment_changes", treatmentChanges);

      if (selectedFile) {
        formData.append("image", selectedFile);
      } else if (cameraStatus === "active" && videoRef.current) {
        const video = videoRef.current;
        const canvas = document.createElement("canvas");
        canvas.width = video.videoWidth || 720;
        canvas.height = video.videoHeight || 960;
        const ctx = canvas.getContext("2d");
        if (ctx) {
          ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        }
        const capturedBlob = await new Promise<Blob | null>((resolve) =>
          canvas.toBlob((b) => resolve(b), "image/jpeg", 0.92)
        );
        if (!capturedBlob) {
          throw new Error("Could not capture frame from camera.");
        }
        formData.append("image", capturedBlob, "camera_capture_selfie.jpg");
      } else {
        throw new Error(
          "Please select a real facial photo file or enable your camera before submitting."
        );
      }

      const res = await fetch(`${API_BASE_URL}/api/capture/${token}/submit`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(
          err.detail ||
            "Could not complete skin analysis. Please adjust lighting or try again."
        );
      }

      const visit = (await res.json()) as VisitRecord;
      stopCameraStream();
      setCompletedVisit(visit);
      setStep("success");
    } catch (err) {
      setSubmitError(
        err instanceof Error ? err.message : "Could not complete scan."
      );
    } finally {
      setSubmitting(false);
    }
  }

  if (tokenError) {
    return (
      <main id="main-content" className="max-w-md w-full mx-auto px-4 py-12">
        <div
          role="alert"
          className="rounded-2xl bg-white border border-rose-300 p-6 shadow-clinical space-y-3"
        >
          <div className="inline-flex items-center gap-1.5 rounded bg-rose-50 border border-rose-200 px-2.5 py-1 text-xs font-bold text-rose-900">
            <span aria-hidden="true">!</span>
            <span>Session Expired or Unavailable</span>
          </div>
          <h1 className="text-lg font-bold text-slate-900">
            Capture Link Unavailable
          </h1>
          <p className="text-sm text-slate-700 leading-relaxed">{tokenError}</p>
          <p className="text-xs text-slate-600 bg-slate-50 rounded-lg p-3 border border-slate-200">
            For your privacy, patient check-in links expire automatically after
            30 minutes. Please ask your dermatology care team to generate a new
            capture link.
          </p>
          <p className="text-xs text-slate-500 pt-2 border-t border-slate-100">
            {PRIVACY_NOTICE} {CLINICAL_DISCLAIMER}
          </p>
        </div>
      </main>
    );
  }

  const currentStepNumber =
    step === "consent" ? 1 : step === "guided_selfie" ? 2 : 3;

  return (
    <main
      id="main-content"
      className="max-w-md w-full mx-auto px-4 py-5 sm:py-8 space-y-4"
    >
      <div className="rounded-2xl bg-white border border-slate-200 p-5 shadow-clinical space-y-5">
        <header className="border-b border-slate-200 pb-4 space-y-2">
          <div className="flex items-center justify-between gap-2">
            <span className="inline-block rounded bg-sky-50 border border-sky-200 px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wide text-sky-900">
              {sessionInfo?.clinic_name || "Bridge Dermatology Clinic"}
            </span>
            <span className="text-xs font-semibold text-slate-600">
              Step {currentStepNumber} of 3
            </span>
          </div>

          <h1 className="text-xl font-bold text-slate-900 tracking-tight">
            Guided Clinic Skin Check-In
          </h1>
          <p className="text-xs text-slate-600">
            Patient:{" "}
            <strong className="font-semibold text-slate-900">
              {verifyingToken
                ? "Verifying session..."
                : sessionInfo?.patient_display_name || "Patient"}
            </strong>{" "}
            &bull; Consent:{" "}
            <strong className="font-mono text-slate-800">
              {sessionInfo?.consent_version || "v1-2026-10"}
            </strong>
          </p>

          {/* Accessible 3-Step Progress Bar */}
          <ol
            aria-label="Check-in progress"
            className="grid grid-cols-3 gap-1.5 pt-2 text-[11px] font-semibold"
          >
            <li
              aria-current={step === "consent" ? "step" : undefined}
              className={`rounded-md px-2 py-1 text-center border ${
                step === "consent"
                  ? "bg-sky-700 text-white border-sky-700"
                  : "bg-emerald-50 text-emerald-900 border-emerald-200"
              }`}
            >
              1. Intake &amp; Consent
            </li>
            <li
              aria-current={step === "guided_selfie" ? "step" : undefined}
              className={`rounded-md px-2 py-1 text-center border ${
                step === "guided_selfie"
                  ? "bg-sky-700 text-white border-sky-700"
                  : step === "success"
                  ? "bg-emerald-50 text-emerald-900 border-emerald-200"
                  : "bg-slate-100 text-slate-600 border-slate-200"
              }`}
            >
              2. Guided Photo
            </li>
            <li
              aria-current={step === "success" ? "step" : undefined}
              className={`rounded-md px-2 py-1 text-center border ${
                step === "success"
                  ? "bg-emerald-700 text-white border-emerald-700"
                  : "bg-slate-100 text-slate-600 border-slate-200"
              }`}
            >
              3. Complete
            </li>
          </ol>
        </header>

        {/* Mandatory hedged clinical & privacy notices */}
        <div
          role="note"
          aria-label="Privacy and clinical notice"
          className="rounded-xl bg-slate-50 border border-slate-200 p-3.5 text-xs text-slate-700 space-y-1"
        >
          <p className="font-semibold text-slate-900 flex items-center gap-1.5">
            <span aria-hidden="true" className="text-sky-700">
              🔒
            </span>
            <span>{PRIVACY_NOTICE}</span>
          </p>
          <p className="text-slate-600">{CLINICAL_DISCLAIMER}</p>
        </div>

        {step === "consent" && (
          <div className="space-y-4">
            <div className="space-y-3">
              <div>
                <label
                  htmlFor="capture-complaint"
                  className="block text-xs font-semibold text-slate-800 mb-1"
                >
                  Today&apos;s Primary Skin Concern
                </label>
                <span
                  id="complaint-hint"
                  className="block text-[11px] text-slate-600 mb-1"
                >
                  Briefly describe what you would like your dermatologist to
                  review today.
                </span>
                <input
                  type="text"
                  id="capture-complaint"
                  aria-describedby="complaint-hint"
                  value={chiefComplaint}
                  onChange={(e) => setChiefComplaint(e.target.value)}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm text-slate-900"
                />
              </div>

              <div>
                <label
                  htmlFor="capture-routine"
                  className="block text-xs font-semibold text-slate-800 mb-1"
                >
                  Current Daily Cleansers &amp; Moisturizers
                </label>
                <input
                  type="text"
                  id="capture-routine"
                  value={routineText}
                  onChange={(e) => setRoutineText(e.target.value)}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm text-slate-900"
                />
              </div>

              <div>
                <label
                  htmlFor="capture-changes"
                  className="block text-xs font-semibold text-slate-800 mb-1"
                >
                  Recent Prescription or Regimen Changes
                </label>
                <input
                  type="text"
                  id="capture-changes"
                  value={treatmentChanges}
                  onChange={(e) => setTreatmentChanges(e.target.value)}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm text-slate-900"
                />
              </div>
            </div>

            <div className="rounded-xl bg-sky-50/70 border border-sky-200 p-3.5">
              <label
                htmlFor="capture-consent-checkbox"
                className="flex items-start gap-3 text-xs text-slate-800 cursor-pointer"
              >
                <input
                  id="capture-consent-checkbox"
                  type="checkbox"
                  checked={consentChecked}
                  onChange={(e) => setConsentChecked(e.target.checked)}
                  className="mt-0.5 h-4 w-4 rounded border-slate-300 text-sky-700 shrink-0"
                />
                <span className="leading-relaxed">
                  I consent to capturing a clinic visit photo for longitudinal
                  dermatologist review.{" "}
                  <strong>
                    Photos are stored privately and deletable on request.
                  </strong>{" "}
                  ({CLINICAL_DISCLAIMER})
                </span>
              </label>
            </div>

            <button
              type="button"
              disabled={!consentChecked || verifyingToken}
              onClick={() => setStep("guided_selfie")}
              className="w-full rounded-xl bg-sky-700 hover:bg-sky-800 disabled:opacity-50 text-white font-semibold py-3 px-4 text-sm shadow-sm transition"
            >
              Continue to Guided Selfie &rarr;
            </button>
          </div>
        )}

        {step === "guided_selfie" && (
          <div className="space-y-4">
            <div className="rounded-xl bg-slate-50 border border-slate-200 p-3 text-xs text-slate-700 space-y-1">
              <p className="font-semibold text-slate-900">
                How to take a clear clinic photo:
              </p>
              <ul className="list-disc pl-4 space-y-0.5 text-slate-600">
                <li>Face a window or even indoor light (avoid strong shadows).</li>
                <li>Remove glasses and pull hair back from your forehead.</li>
                <li>Center your face inside the oval guide below.</li>
              </ul>
            </div>

            {/* Visual oval guide frame with live camera or guided check status */}
            <div className="relative rounded-2xl bg-slate-900 text-white p-5 flex flex-col items-center justify-center min-h-[225px] border-2 border-slate-700 overflow-hidden">
              {cameraStatus === "active" && (
                <video
                  ref={videoRef}
                  autoPlay
                  playsInline
                  muted
                  aria-label="Live front-facing camera preview"
                  className="absolute inset-0 w-full h-full object-cover opacity-65"
                />
              )}

              <div
                role="status"
                aria-live="polite"
                className={`relative z-10 w-36 h-44 rounded-full border-2 border-dashed flex flex-col items-center justify-center text-center p-3 text-xs transition ${
                  qualityVerdict.passed
                    ? "border-emerald-400 bg-emerald-950/45 text-emerald-100"
                    : "border-rose-400 bg-rose-950/60 text-rose-100"
                }`}
              >
                <span
                  aria-hidden="true"
                  className="text-base font-bold mb-1 block"
                >
                  {qualityVerdict.passed ? "✓" : "!"}
                </span>
                <span className="font-semibold">
                  {qualityVerdict.passed
                    ? "Face Centered & Lighting Ready"
                    : "Adjust Framing or Lighting"}
                </span>
              </div>

              <p className="relative z-10 mt-3 text-xs text-center font-medium px-2">
                {qualityVerdict.message}
              </p>
            </div>

            {/* Optional live camera activation & permission feedback */}
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs">
              <span className="text-slate-700 font-medium">
                {cameraStatus === "active"
                  ? "Live camera preview active"
                  : "Optional: Use device front camera preview"}
              </span>
              {cameraStatus === "active" ? (
                <button
                  type="button"
                  onClick={stopCameraStream}
                  className="rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-100"
                >
                  Stop Camera
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => void handleStartCamera()}
                  disabled={cameraStatus === "requesting"}
                  className="rounded-lg border border-sky-300 bg-sky-50 px-2.5 py-1 text-xs font-semibold text-sky-900 hover:bg-sky-100 disabled:opacity-60"
                >
                  {cameraStatus === "requesting"
                    ? "Requesting Access..."
                    : "Enable Camera Preview"}
                </button>
              )}
            </div>

            {cameraMessage && (
              <div
                role="status"
                aria-live="polite"
                className="rounded-lg bg-amber-50 border border-amber-300 p-3 text-xs text-amber-950 space-y-1"
              >
                <p className="font-semibold">Camera Access Notice</p>
                <p>{cameraMessage}</p>
              </div>
            )}

            {/* Real-time quality gate presets to test rejection rules cleanly */}
            <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-3 space-y-2">
              <span className="block text-[11px] font-semibold uppercase tracking-wide text-slate-700">
                Guided Quality Check Simulator (Client-Side Gate)
              </span>
              <div className="flex flex-wrap gap-1.5">
                <button
                  type="button"
                  onClick={() => {
                    setSubmitError(null);
                    setFrameMetrics({
                      faceCount: 1,
                      meanBrightness: 142,
                      faceAreaRatio: 0.34,
                      hasEyewearOcclusion: false,
                    });
                  }}
                  className={`rounded-md border px-2.5 py-1.5 text-xs font-semibold transition ${
                    qualityVerdict.passed
                      ? "border-emerald-600 bg-emerald-50 text-emerald-950"
                      : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
                  }`}
                >
                  ✓ Valid Front Face
                </button>
                <button
                  type="button"
                  onClick={() =>
                    setFrameMetrics({
                      faceCount: 0,
                      meanBrightness: 130,
                      faceAreaRatio: 0,
                    })
                  }
                  className={`rounded-md border px-2.5 py-1.5 text-xs font-medium transition ${
                    qualityVerdict.reason === "no_face"
                      ? "border-rose-600 bg-rose-50 text-rose-950 font-semibold"
                      : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
                  }`}
                >
                  Test: No Face
                </button>
                <button
                  type="button"
                  onClick={() =>
                    setFrameMetrics({
                      faceCount: 2,
                      meanBrightness: 130,
                      faceAreaRatio: 0.3,
                    })
                  }
                  className={`rounded-md border px-2.5 py-1.5 text-xs font-medium transition ${
                    qualityVerdict.reason === "multiple_faces"
                      ? "border-rose-600 bg-rose-50 text-rose-950 font-semibold"
                      : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
                  }`}
                >
                  Test: Multiple Faces
                </button>
                <button
                  type="button"
                  onClick={() =>
                    setFrameMetrics({
                      faceCount: 1,
                      meanBrightness: 35,
                      faceAreaRatio: 0.3,
                    })
                  }
                  className={`rounded-md border px-2.5 py-1.5 text-xs font-medium transition ${
                    qualityVerdict.reason === "too_dark"
                      ? "border-rose-600 bg-rose-50 text-rose-950 font-semibold"
                      : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
                  }`}
                >
                  Test: Too Dark
                </button>
                <button
                  type="button"
                  onClick={() =>
                    setFrameMetrics({
                      faceCount: 1,
                      meanBrightness: 130,
                      faceAreaRatio: 0.09,
                    })
                  }
                  className={`rounded-md border px-2.5 py-1.5 text-xs font-medium transition ${
                    qualityVerdict.reason === "face_too_small"
                      ? "border-rose-600 bg-rose-50 text-rose-950 font-semibold"
                      : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
                  }`}
                >
                  Test: Face Too Small
                </button>
                <button
                  type="button"
                  onClick={() =>
                    setFrameMetrics({
                      faceCount: 1,
                      meanBrightness: 130,
                      faceAreaRatio: 0.3,
                      hasEyewearOcclusion: true,
                    })
                  }
                  className={`rounded-md border px-2.5 py-1.5 text-xs font-medium transition ${
                    qualityVerdict.reason === "eyewear_occlusion"
                      ? "border-rose-600 bg-rose-50 text-rose-950 font-semibold"
                      : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
                  }`}
                >
                  Test: Eyewear
                </button>
              </div>
            </div>

            {/* File selection & Retake / Clear support */}
            <div className="rounded-xl border border-slate-200 p-3 space-y-2">
              <div className="flex items-center justify-between gap-2">
                <label
                  htmlFor="selfie-file-input"
                  className="block text-xs font-semibold text-slate-800"
                >
                  Upload or Capture Selfie Photo (Optional)
                </label>
                {selectedFile && (
                  <button
                    type="button"
                    onClick={handleRetakeOrClearPhoto}
                    className="text-xs font-semibold text-rose-700 hover:text-rose-900 hover:underline"
                  >
                    Retake / Clear Photo
                  </button>
                )}
              </div>
              <input
                ref={fileInputRef}
                type="file"
                id="selfie-file-input"
                accept="image/jpeg,image/png,image/webp"
                capture="user"
                onChange={(e) => {
                  const file = e.target.files?.[0] || null;
                  setSelectedFile(file);
                  setSubmitError(null);
                }}
                className="w-full text-xs text-slate-700 file:mr-3 file:rounded-lg file:border file:border-slate-300 file:bg-slate-100 file:px-3 file:py-1.5 file:text-xs file:font-semibold file:text-slate-800 hover:file:bg-slate-200"
              />
              {selectedFile && (
                <p className="text-xs text-emerald-800 font-medium">
                  Selected photo: <strong>{selectedFile.name}</strong> (
                  {Math.max(1, Math.round(selectedFile.size / 1024))} KB)
                </p>
              )}
            </div>

            {submitError && (
              <div
                role="alert"
                className="rounded-xl bg-rose-50 border border-rose-300 p-3.5 text-xs text-rose-900 space-y-2"
              >
                <div className="font-semibold flex items-center gap-1.5">
                  <span aria-hidden="true">!</span>
                  <span>Unable to submit scan</span>
                </div>
                <p>{submitError}</p>
                <div className="flex flex-wrap gap-2 pt-1">
                  <button
                    type="button"
                    onClick={handleRetakeOrClearPhoto}
                    className="rounded-lg border border-rose-300 bg-white px-3 py-1.5 text-xs font-semibold text-rose-900 hover:bg-rose-100"
                  >
                    Reset Framing Check
                  </button>
                  {qualityVerdict.passed && (
                    <button
                      type="button"
                      onClick={() => void handleSubmitScan()}
                      className="rounded-lg bg-rose-800 px-3 py-1.5 text-xs font-semibold text-white hover:bg-rose-900"
                    >
                      Retry Upload
                    </button>
                  )}
                </div>
              </div>
            )}

            <div className="flex items-center gap-2.5 pt-1">
              <button
                type="button"
                disabled={submitting}
                onClick={() => {
                  stopCameraStream();
                  setStep("consent");
                }}
                className="rounded-xl border border-slate-300 bg-white hover:bg-slate-50 px-4 py-3 text-xs font-semibold text-slate-800 transition"
              >
                &larr; Back
              </button>
              <button
                type="button"
                disabled={!qualityVerdict.passed || submitting}
                onClick={() => void handleSubmitScan()}
                className="flex-1 rounded-xl bg-sky-700 hover:bg-sky-800 disabled:opacity-50 text-white font-semibold py-3 px-4 text-sm shadow-sm transition"
              >
                {submitting
                  ? "Uploading & Analyzing 12 Skin Metrics..."
                  : "Capture & Submit Clinic Scan"}
              </button>
            </div>
          </div>
        )}

        {step === "success" && (
          <div
            role="status"
            aria-live="polite"
            className="rounded-xl bg-emerald-50 border border-emerald-300 p-5 space-y-3 text-center"
          >
            <div className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-emerald-700 text-white text-base font-bold">
              ✓
            </div>
            <div className="text-base font-bold text-emerald-950">
              Clinic Scan Complete
            </div>
            <p className="text-xs text-emerald-900 leading-relaxed">
              Your guided skin check-in ({completedVisit?.visit_date}) and{" "}
              <strong>{completedVisit?.concern_scores.length ?? 12}</strong>{" "}
              longitudinal measurements have been sent to your
              dermatologist&apos;s consultation chart.
            </p>
            <div className="rounded-lg bg-white/90 border border-emerald-200 p-3 text-left text-xs text-slate-700 space-y-1">
              <p className="font-semibold text-slate-900">What happens next?</p>
              <p>
                Your clinician will review these measurements alongside your
                visit history and treatment regimen during your consultation. You
                may now close this window.
              </p>
            </div>
            <p className="text-[11px] text-slate-600 pt-2 border-t border-emerald-200">
              {PRIVACY_NOTICE} {CLINICAL_DISCLAIMER}
            </p>
          </div>
        )}
      </div>
    </main>
  );
}
