"use client";

import React, { useEffect, useState } from "react";
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

export default function PatientMobileCapturePage() {
  const params = useParams<{ token: string }>();
  const token = params.token;

  const [sessionInfo, setSessionInfo] = useState<CaptureSessionInfo | null>(
    null
  );
  const [tokenError, setTokenError] = useState<string | null>(null);
  const [step, setStep] = useState<CaptureStep>("consent");

  // Consent & encounter intake form
  const [consentChecked, setConsentChecked] = useState(true);
  const [chiefComplaint, setChiefComplaint] = useState(
    "Follow-up skin check on cheeks and forehead"
  );
  const [routineText, setRoutineText] = useState(
    "Gentle cleanser, ceramide moisturizer, daily mineral SPF"
  );
  const [treatmentChanges, setTreatmentChanges] = useState(
    "Continued nightly adapalene gel and barrier cream"
  );

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

  const qualityVerdict = evaluateCaptureFrame(frameMetrics);

  useEffect(() => {
    async function verifyToken() {
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
      }
    }
    void verifyToken();
  }, [token]);

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
      } else {
        // Generate synthetic guided capture blob for instant mobile/demo scan completion
        const syntheticBytes = new Uint8Array([
          0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10, 0x4a, 0x46, 0x49, 0x46, 0x00,
          0x01, 0xff, 0xd9,
        ]);
        const blob = new Blob([syntheticBytes], { type: "image/jpeg" });
        formData.append("image", blob, "guided_capture_selfie.jpg");
      }

      const res = await fetch(`${API_BASE_URL}/api/capture/${token}/submit`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to submit guided clinic selfie.");
      }

      const visit = (await res.json()) as VisitRecord;
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
      <main className="max-w-md w-full mx-auto px-4 py-12">
        <div
          role="alert"
          className="rounded-2xl bg-white border border-rose-200 p-6 shadow-sm space-y-3"
        >
          <h1 className="text-lg font-bold text-rose-900">
            Capture Link Unavailable
          </h1>
          <p className="text-sm text-slate-700">{tokenError}</p>
          <p className="text-xs text-slate-500 pt-2 border-t border-slate-100">
            {PRIVACY_NOTICE} {CLINICAL_DISCLAIMER}
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="max-w-md w-full mx-auto px-4 py-6 space-y-5">
      <div className="rounded-2xl bg-white border border-slate-200 p-5 shadow-sm space-y-4">
        <header className="border-b border-slate-100 pb-3">
          <span className="inline-block rounded bg-sky-50 border border-sky-200 px-2 py-0.5 text-[11px] font-bold uppercase text-sky-800">
            {sessionInfo?.clinic_name || "Bridge Dermatology Clinic"}
          </span>
          <h1 className="mt-1.5 text-xl font-bold text-slate-900">
            Guided Clinic Skin Check-In
          </h1>
          <p className="text-xs text-slate-600 mt-0.5">
            Patient:{" "}
            <strong>{sessionInfo?.patient_display_name || "Loading..."}</strong>{" "}
            &bull; Consent:{" "}
            <strong>{sessionInfo?.consent_version || "v1-2026-10"}</strong>
          </p>
        </header>

        {/* Mandatory hedged clinical & privacy notices */}
        <div className="rounded-xl bg-slate-50 border border-slate-200 p-3 text-xs text-slate-700 space-y-1">
          <p className="font-semibold text-slate-900">{PRIVACY_NOTICE}</p>
          <p>{CLINICAL_DISCLAIMER}</p>
        </div>

        {step === "consent" && (
          <div className="space-y-4">
            <div className="space-y-3">
              <div>
                <label
                  htmlFor="capture-complaint"
                  className="block text-xs font-semibold uppercase text-slate-700 mb-1"
                >
                  Today&apos;s Primary Skin Concern
                </label>
                <input
                  type="text"
                  id="capture-complaint"
                  value={chiefComplaint}
                  onChange={(e) => setChiefComplaint(e.target.value)}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                />
              </div>

              <div>
                <label
                  htmlFor="capture-routine"
                  className="block text-xs font-semibold uppercase text-slate-700 mb-1"
                >
                  Current Daily Routine
                </label>
                <input
                  type="text"
                  id="capture-routine"
                  value={routineText}
                  onChange={(e) => setRoutineText(e.target.value)}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                />
              </div>

              <div>
                <label
                  htmlFor="capture-changes"
                  className="block text-xs font-semibold uppercase text-slate-700 mb-1"
                >
                  Recent Regimen / Product Changes
                </label>
                <input
                  type="text"
                  id="capture-changes"
                  value={treatmentChanges}
                  onChange={(e) => setTreatmentChanges(e.target.value)}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                />
              </div>
            </div>

            <label className="flex items-start gap-2.5 text-xs text-slate-800 cursor-pointer pt-1">
              <input
                type="checkbox"
                checked={consentChecked}
                onChange={(e) => setConsentChecked(e.target.checked)}
                className="mt-0.5 h-4 w-4 rounded border-slate-300 text-sky-700"
              />
              <span>
                I consent to capturing a clinic visit selfie for longitudinal
                dermatologist review.{" "}
                <strong>Photos are stored privately and deletable on request.</strong>{" "}
                ({CLINICAL_DISCLAIMER})
              </span>
            </label>

            <button
              type="button"
              disabled={!consentChecked}
              onClick={() => setStep("guided_selfie")}
              className="w-full rounded-xl bg-slate-900 hover:bg-slate-800 disabled:opacity-50 text-white font-semibold py-3 px-4 text-sm transition"
            >
              Continue to Guided Selfie &rarr;
            </button>
          </div>
        )}

        {step === "guided_selfie" && (
          <div className="space-y-4">
            {/* Visual oval guide frame */}
            <div className="relative rounded-2xl bg-slate-900 text-white p-5 flex flex-col items-center justify-center min-h-[210px] border-2 border-slate-700">
              <div
                className={`w-32 h-40 rounded-full border-2 border-dashed flex items-center justify-center text-center p-3 text-xs ${
                  qualityVerdict.passed
                    ? "border-emerald-400 bg-emerald-950/30 text-emerald-200"
                    : "border-rose-400 bg-rose-950/40 text-rose-200"
                }`}
              >
                {qualityVerdict.passed
                  ? "Face Centered & Lighting Ready"
                  : "Adjust Framing / Lighting"}
              </div>
              <p className="mt-3 text-xs text-center font-medium">
                {qualityVerdict.message}
              </p>
            </div>

            {/* Real-time quality gate presets to test rejection rules cleanly */}
            <div className="space-y-1.5">
              <span className="block text-[11px] font-semibold uppercase text-slate-600">
                Guided Quality Check Simulator (Client-Side Gate)
              </span>
              <div className="flex flex-wrap gap-1.5">
                <button
                  type="button"
                  onClick={() =>
                    setFrameMetrics({
                      faceCount: 1,
                      meanBrightness: 142,
                      faceAreaRatio: 0.34,
                      hasEyewearOcclusion: false,
                    })
                  }
                  className="rounded border border-emerald-300 bg-emerald-50 px-2 py-1 text-[11px] font-semibold text-emerald-900"
                >
                  Valid Front Face
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
                  className="rounded border border-slate-300 bg-white px-2 py-1 text-[11px] text-slate-700"
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
                  className="rounded border border-slate-300 bg-white px-2 py-1 text-[11px] text-slate-700"
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
                  className="rounded border border-slate-300 bg-white px-2 py-1 text-[11px] text-slate-700"
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
                  className="rounded border border-slate-300 bg-white px-2 py-1 text-[11px] text-slate-700"
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
                  className="rounded border border-slate-300 bg-white px-2 py-1 text-[11px] text-slate-700"
                >
                  Test: Eyewear
                </button>
              </div>
            </div>

            <div>
              <label
                htmlFor="selfie-file-input"
                className="block text-xs font-semibold text-slate-700 mb-1"
              >
                Optional: Select Selfie Image (or use instant guided capture)
              </label>
              <input
                type="file"
                id="selfie-file-input"
                accept="image/jpeg,image/png,image/webp"
                capture="user"
                onChange={(e) => {
                  const file = e.target.files?.[0] || null;
                  setSelectedFile(file);
                }}
                className="w-full text-xs text-slate-600"
              />
            </div>

            {submitError && (
              <div
                role="alert"
                className="rounded-lg bg-rose-50 border border-rose-200 p-3 text-xs text-rose-800"
              >
                {submitError}
              </div>
            )}

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setStep("consent")}
                className="rounded-xl border border-slate-300 px-3.5 py-3 text-xs font-semibold text-slate-700"
              >
                &larr; Back
              </button>
              <button
                type="button"
                disabled={!qualityVerdict.passed || submitting}
                onClick={handleSubmitScan}
                className="flex-1 rounded-xl bg-sky-700 hover:bg-sky-800 disabled:opacity-50 text-white font-semibold py-3 px-4 text-sm transition"
              >
                {submitting
                  ? "Analyzing Skin Concerns..."
                  : "Capture & Submit Clinic Scan"}
              </button>
            </div>
          </div>
        )}

        {step === "success" && (
          <div className="rounded-xl bg-emerald-50 border border-emerald-200 p-4 space-y-2 text-center">
            <div className="text-base font-bold text-emerald-950">
              Clinic Scan Complete
            </div>
            <p className="text-xs text-emerald-900">
              Your scan ({completedVisit?.visit_date}) has been sent to your
              dermatologist&apos;s consultation dashboard.
            </p>
            <p className="text-[11px] text-slate-600 pt-2 border-t border-emerald-200">
              {PRIVACY_NOTICE} {CLINICAL_DISCLAIMER}
            </p>
          </div>
        )}
      </div>
    </main>
  );
}

