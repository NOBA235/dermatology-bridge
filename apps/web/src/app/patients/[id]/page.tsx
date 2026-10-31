"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  API_BASE_URL,
  apiFetch,
  CaptureTokenResponse,
  CLINICAL_DISCLAIMER,
  ConcernTrend,
  createPatientMedication,
  deletePatientMedication,
  getStoredToken,
  MedicationCorrelation,
  PatientFlagsResponse,
  PatientMedication,
  PatientMedicationCorrelationsResponse,
  PatientMedicationsResponse,
  PatientRecord,
  PatientTrendsResponse,
  PRIVACY_NOTICE,
  VisitRecord,
} from "@/lib/api";
import {
  DirectionBadge,
  MED_CATEGORY_STYLES,
  MED_RESPONSE_CONFIG,
  ProvenanceBadge,
  SeverityBadge,
  VerdictBadge,
} from "@/components/ClinicalBadges";
import {
  ClinicalInlineNotice,
  ClinicianWorkspaceHeader,
} from "@/components/ClinicalShell";
import { SparklineSvg } from "@/components/SparklineSvg";

interface PatientVisitsPayload {
  patient_id: string;
  visit_count: number;
  visits: VisitRecord[];
  disclaimer: string;
}

function formatSignedDelta(delta: string | null | undefined): string {
  if (delta === null || delta === undefined) return "—";
  const num = Number(delta);
  if (Number.isNaN(num)) return String(delta);
  return num > 0 ? `+${delta}` : String(delta);
}

export default function PatientDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const patientId = params.id;

  const [patient, setPatient] = useState<PatientRecord | null>(null);
  const [visits, setVisits] = useState<VisitRecord[]>([]);
  const [trends, setTrends] = useState<PatientTrendsResponse | null>(null);
  const [flagsData, setFlagsData] = useState<PatientFlagsResponse | null>(null);
  const [medications, setMedications] = useState<PatientMedication[]>([]);
  const [correlations, setCorrelations] = useState<MedicationCorrelation[]>([]);
  const [captureLink, setCaptureLink] = useState<CaptureTokenResponse | null>(
    null
  );

  const [loading, setLoading] = useState(true);
  const [creatingCaptureLink, setCreatingCaptureLink] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionFeedback, setActionFeedback] = useState<string | null>(null);
  const [copiedNotice, setCopiedNotice] = useState(false);

  // Add Prescription modal state
  const addMedDialogRef = useRef<HTMLDialogElement>(null);
  const [medFormName, setMedFormName] = useState("");
  const [medFormCategory, setMedFormCategory] = useState("topical_retinoid");
  const [medFormDose, setMedFormDose] = useState("");
  const [medFormStartDate, setMedFormStartDate] = useState(
    new Date().toISOString().split("T")[0]
  );
  const [medFormNotes, setMedFormNotes] = useState("");
  const [savingMed, setSavingMed] = useState(false);
  const [medDialogError, setMedDialogError] = useState<string | null>(null);

  // Destructive-action confirmation modal state (replaces native window.confirm)
  const deleteMedDialogRef = useRef<HTMLDialogElement>(null);
  const [pendingDeleteMed, setPendingDeleteMed] = useState<{
    id: string;
    name: string;
    dose: string | null;
  } | null>(null);
  const [deletingMed, setDeletingMed] = useState(false);

  // Direct Clinician Visit Photo Upload modal state
  const uploadVisitDialogRef = useRef<HTMLDialogElement>(null);
  const [visitDateInput, setVisitDateInput] = useState(
    new Date().toISOString().split("T")[0]
  );
  const [visitChiefComplaint, setVisitChiefComplaint] = useState("");
  const [visitRoutineText, setVisitRoutineText] = useState("");
  const [visitTreatmentChanges, setVisitTreatmentChanges] = useState("");
  const [visitImageFile, setVisitImageFile] = useState<File | null>(null);
  const [uploadingVisit, setUploadingVisit] = useState(false);
  const [uploadVisitError, setUploadVisitError] = useState<string | null>(null);

  const fetchAllData = useCallback(
    async (silent = false) => {
      if (!getStoredToken()) {
        router.replace("/login");
        return;
      }
      if (!silent) setLoading(true);
      try {
        const [ptRes, visRes, trRes, flRes, medRes, corrRes] =
          await Promise.all([
            apiFetch<PatientRecord>(`/api/patients/${patientId}`),
            apiFetch<PatientVisitsPayload>(`/api/patients/${patientId}/visits`),
            apiFetch<PatientTrendsResponse>(`/api/patients/${patientId}/trends`),
            apiFetch<PatientFlagsResponse>(`/api/patients/${patientId}/flags`),
            apiFetch<PatientMedicationsResponse>(
              `/api/patients/${patientId}/medications`
            ),
            apiFetch<PatientMedicationCorrelationsResponse>(
              `/api/patients/${patientId}/medication-correlations`
            ),
          ]);
        setPatient(ptRes);
        setVisits(visRes.visits);
        setTrends(trRes);
        setFlagsData(flRes);
        setMedications(medRes.medications);
        setCorrelations(corrRes.correlations);
        setError(null);
      } catch (err) {
        if (!silent) {
          setError(
            err instanceof Error
              ? err.message
              : "Failed to load patient longitudinal chart."
          );
        }
      } finally {
        if (!silent) setLoading(false);
      }
    },
    [patientId, router]
  );

  useEffect(() => {
    void fetchAllData(false);
    const intervalId = window.setInterval(() => {
      void fetchAllData(true);
    }, 4000);

    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        void fetchAllData(true);
      }
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      window.clearInterval(intervalId);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [fetchAllData]);

  function showTemporaryFeedback(msg: string) {
    setActionFeedback(msg);
    window.setTimeout(() => {
      setActionFeedback((curr) => (curr === msg ? null : curr));
    }, 4000);
  }

  async function handleGenerateCaptureLink() {
    setCreatingCaptureLink(true);
    setError(null);
    try {
      const tokenOut = await apiFetch<CaptureTokenResponse>(
        `/api/patients/${patientId}/capture-token`,
        { method: "POST" }
      );
      setCaptureLink(tokenOut);
      showTemporaryFeedback("Signed 30-minute patient capture link ready.");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not generate capture link."
      );
    } finally {
      setCreatingCaptureLink(false);
    }
  }

  async function handleRegenerateFlags() {
    setRegenerating(true);
    setError(null);
    try {
      const updated = await apiFetch<PatientFlagsResponse>(
        `/api/patients/${patientId}/flags/regenerate`,
        { method: "POST" }
      );
      setFlagsData(updated);
      await fetchAllData(true);
      showTemporaryFeedback(
        "Longitudinal flags and clinician-review hypotheses recomputed."
      );
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to regenerate flags."
      );
    } finally {
      setRegenerating(false);
    }
  }

  async function handleDownloadReportPdf() {
    const token = getStoredToken();
    if (!token) {
      router.replace("/login");
      return;
    }
    setDownloadingPdf(true);
    setError(null);
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/patients/${patientId}/report.pdf`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      if (!response.ok) {
        throw new Error(`Report generation failed (HTTP ${response.status})`);
      }
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `dermobridge-report-${
        patient?.external_ref || patientId
      }.pdf`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(url);
      showTemporaryFeedback("Downloaded 3-page A4 consultation PDF report.");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not download PDF report."
      );
    } finally {
      setDownloadingPdf(false);
    }
  }

  async function handleAddMedicationSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!medFormName.trim()) {
      setMedDialogError("Medication or regimen product name is required.");
      return;
    }
    setSavingMed(true);
    setMedDialogError(null);
    try {
      await createPatientMedication(patientId, {
        name: medFormName.trim(),
        category: medFormCategory,
        dose: medFormDose.trim() || undefined,
        start_date: medFormStartDate,
        notes: medFormNotes.trim() || undefined,
      });
      addMedDialogRef.current?.close();
      setMedFormName("");
      setMedFormDose("");
      setMedFormNotes("");
      await fetchAllData(true);
      showTemporaryFeedback(
        "Prescription recorded and cross-referenced against visit timeline."
      );
    } catch (err) {
      setMedDialogError(
        err instanceof Error ? err.message : "Failed to record medication."
      );
    } finally {
      setSavingMed(false);
    }
  }

  function requestDeleteMedication(med: {
    id: string;
    name: string;
    dose: string | null;
  }) {
    setPendingDeleteMed(med);
    deleteMedDialogRef.current?.showModal();
  }

  async function confirmDeleteMedication() {
    if (!pendingDeleteMed) return;
    setDeletingMed(true);
    try {
      await deletePatientMedication(patientId, pendingDeleteMed.id);
      deleteMedDialogRef.current?.close();
      setPendingDeleteMed(null);
      await fetchAllData(true);
      showTemporaryFeedback("Medication record removed from chart.");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to delete medication."
      );
      deleteMedDialogRef.current?.close();
    } finally {
      setDeletingMed(false);
    }
  }

  async function handleUploadVisitSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!visitImageFile) {
      setUploadVisitError(
        "Please select a real facial photo (JPEG, PNG, or WebP)."
      );
      return;
    }
    const token = getStoredToken();
    if (!token) {
      router.replace("/login");
      return;
    }
    setUploadingVisit(true);
    setUploadVisitError(null);
    try {
      const formData = new FormData();
      formData.append("patient_id", patientId);
      if (visitDateInput) formData.append("visit_date", visitDateInput);
      if (visitChiefComplaint.trim()) {
        formData.append("chief_complaint", visitChiefComplaint.trim());
      }
      if (visitRoutineText.trim()) {
        formData.append("routine_text", visitRoutineText.trim());
      }
      if (visitTreatmentChanges.trim()) {
        formData.append("treatment_changes", visitTreatmentChanges.trim());
      }
      formData.append("image", visitImageFile);

      const res = await fetch(`${API_BASE_URL}/api/visits`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });
      if (!res.ok) {
        const errBody = await res.json().catch(() => ({}));
        throw new Error(
          errBody.detail || `Skin analysis failed (HTTP ${res.status})`
        );
      }
      uploadVisitDialogRef.current?.close();
      setVisitChiefComplaint("");
      setVisitRoutineText("");
      setVisitTreatmentChanges("");
      setVisitImageFile(null);
      await fetchAllData(false);
      showTemporaryFeedback(
        "Live YouCam skin analysis completed and persisted to patient chart."
      );
    } catch (err) {
      setUploadVisitError(
        err instanceof Error
          ? err.message
          : "Failed to upload and analyze visit photo."
      );
    } finally {
      setUploadingVisit(false);
    }
  }

  const concernsByKey: Record<string, ConcernTrend> = {};
  for (const c of trends?.concerns || []) {
    concernsByKey[c.concern] = c;
  }

  const topConcernsList = (flagsData?.top_concerns || [])
    .map((key) => concernsByKey[key])
    .filter(Boolean);

  const visitCount = trends?.visit_count ?? visits.length;
  const baselineDate = trends?.baseline_date || null;
  const latestDate = trends?.latest_date || null;
  const daysBetween = trends?.days_between ?? null;

  return (
    <>
      <ClinicianWorkspaceHeader
        currentPatientName={patient?.full_name}
        currentPatientRef={patient?.external_ref}
      />

      <main
        id="main-content"
        className="max-w-7xl w-full mx-auto px-4 sm:px-6 py-6 sm:py-8 space-y-7"
      >
        {/* Patient Identity & Grouped Clinical Actions Header */}
        <section
          aria-label="Patient chart summary and actions"
          className="bg-white border border-slate-200 rounded-xl p-5 shadow-clinical space-y-4"
        >
          <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-200 pb-4">
            <div className="space-y-1">
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <Link
                  href="/patients"
                  className="font-semibold text-sky-800 hover:text-sky-950 hover:underline"
                >
                  &larr; Back to Patient Directory
                </Link>
                <span aria-hidden="true" className="text-slate-300">
                  &bull;
                </span>
                <span className="font-mono text-slate-600">
                  Chart Ref:{" "}
                  <strong className="text-slate-900">
                    {patient?.external_ref || "Unassigned"}
                  </strong>
                </span>
              </div>

              <h1 className="text-xl sm:text-2xl font-bold text-slate-900 tracking-tight">
                {patient ? patient.full_name : "Loading Patient Chart..."}
              </h1>

              {patient?.notes && (
                <p className="text-xs text-slate-600 max-w-3xl">
                  <strong className="font-semibold text-slate-800">
                    Standing Clinical Context:
                  </strong>{" "}
                  {patient.notes}
                </p>
              )}
            </div>

            {/* Grouped Actions: Secondary clinical tools vs Primary outputs */}
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => {
                  setMedDialogError(null);
                  addMedDialogRef.current?.showModal();
                }}
                className="rounded-lg border border-slate-300 bg-white hover:bg-slate-50 text-slate-800 text-xs font-semibold px-3.5 py-2 transition"
              >
                + Add Prescription / Regimen
              </button>

              <button
                type="button"
                onClick={() => void handleRegenerateFlags()}
                disabled={regenerating}
                className="rounded-lg border border-slate-300 bg-white hover:bg-slate-50 disabled:opacity-60 text-slate-800 text-xs font-semibold px-3.5 py-2 transition"
              >
                {regenerating ? "Recomputing..." : "Regenerate Flags"}
              </button>

              <button
                type="button"
                onClick={() => {
                  setUploadVisitError(null);
                  uploadVisitDialogRef.current?.showModal();
                }}
                className="rounded-lg bg-emerald-700 hover:bg-emerald-800 text-white text-xs font-semibold px-3.5 py-2 shadow-sm transition"
              >
                + Upload Real Visit Photo
              </button>

              <button
                type="button"
                disabled={creatingCaptureLink}
                onClick={() => void handleGenerateCaptureLink()}
                className="rounded-lg bg-sky-700 hover:bg-sky-800 disabled:opacity-60 text-white text-xs font-semibold px-3.5 py-2 shadow-sm transition"
              >
                {creatingCaptureLink
                  ? "Generating Link..."
                  : "Create Patient Capture Link"}
              </button>

              <button
                type="button"
                onClick={() => void handleDownloadReportPdf()}
                disabled={downloadingPdf}
                className="rounded-lg bg-slate-900 hover:bg-slate-800 disabled:opacity-60 text-white text-xs font-semibold px-3.5 py-2 shadow-sm transition"
              >
                {downloadingPdf
                  ? "Building 3-Page PDF..."
                  : "Download 3-Page Report (PDF)"}
              </button>
            </div>
          </div>

          {/* Structured Patient & Observation Window Metadata Strip */}
          <dl className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 text-xs">
            <div className="rounded-lg bg-slate-50 border border-slate-200/80 px-3 py-2">
              <dt className="text-[11px] font-medium text-slate-500">
                Date of Birth
              </dt>
              <dd className="font-mono font-semibold text-slate-900 mt-0.5">
                {patient?.dob || "Not recorded"}
              </dd>
            </div>

            <div className="rounded-lg bg-slate-50 border border-slate-200/80 px-3 py-2">
              <dt className="text-[11px] font-medium text-slate-500">
                Baseline Scan Date
              </dt>
              <dd className="font-mono font-semibold text-slate-900 mt-0.5">
                {baselineDate || "No baseline yet"}
              </dd>
            </div>

            <div className="rounded-lg bg-slate-50 border border-slate-200/80 px-3 py-2">
              <dt className="text-[11px] font-medium text-slate-500">
                Latest Follow-Up Scan
              </dt>
              <dd className="font-mono font-semibold text-slate-900 mt-0.5">
                {latestDate ||
                  (visitCount === 1 ? "Awaiting follow-up" : "No scans yet")}
              </dd>
            </div>

            <div className="rounded-lg bg-slate-50 border border-slate-200/80 px-3 py-2">
              <dt className="text-[11px] font-medium text-slate-500">
                Observation Window
              </dt>
              <dd className="font-semibold text-slate-900 mt-0.5">
                {visitCount >= 2 && daysBetween !== null
                  ? `${daysBetween} days (${visitCount} scans)`
                  : `${visitCount} ${
                      visitCount === 1 ? "scan" : "scans"
                    } (<2 for delta)`}
              </dd>
            </div>

            <div className="rounded-lg bg-slate-50 border border-slate-200/80 px-3 py-2">
              <dt className="text-[11px] font-medium text-slate-500">
                Active Regimen Items
              </dt>
              <dd className="font-semibold text-slate-900 mt-0.5">
                {medications.filter((m) => m.is_active).length} active /{" "}
                {medications.length} recorded
              </dd>
            </div>

            <div className="rounded-lg bg-slate-50 border border-slate-200/80 px-3 py-2">
              <dt className="text-[11px] font-medium text-slate-500">
                Consent &amp; Analysis Schema
              </dt>
              <dd className="font-mono font-semibold text-slate-900 mt-0.5">
                {patient?.consent_version || "v1-2026-10"} &bull; v
                {trends?.analysis_version ?? 1}
              </dd>
            </div>
          </dl>
        </section>

        {/* Persistent Clinical Notice */}
        <ClinicalInlineNotice>
          Observed scores (0–100 scale) and minimal detectable change (MDC)
          thresholds are separated below from generated hypotheses and temporal
          medication correlations. Live auto-refresh polls every 4s.
        </ClinicalInlineNotice>

        {/* Status Toast / Feedback Banner */}
        {actionFeedback && (
          <div
            role="status"
            aria-live="polite"
            className="rounded-xl bg-emerald-50 border border-emerald-300 px-4 py-3 text-xs font-semibold text-emerald-950 flex items-center justify-between gap-2"
          >
            <span className="flex items-center gap-2">
              <span aria-hidden="true">✓</span>
              <span>{actionFeedback}</span>
            </span>
            <button
              type="button"
              onClick={() => setActionFeedback(null)}
              className="text-emerald-800 hover:text-emerald-950 underline"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Generated Patient Capture Link Panel */}
        {captureLink && (
          <section
            aria-label="Generated patient capture link"
            className="rounded-xl bg-white border-2 border-sky-700 p-4 shadow-clinical space-y-2.5"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="inline-flex h-2 w-2 rounded-full bg-sky-700" />
                <h2 className="text-sm font-bold text-slate-900">
                  Signed Mobile Capture Link Ready (Valid for{" "}
                  {Math.round(captureLink.expires_in_seconds / 60)} Minutes)
                </h2>
              </div>
              <span className="text-xs text-slate-600">{PRIVACY_NOTICE}</span>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <code className="flex-1 min-w-[240px] rounded-lg bg-slate-100 border border-slate-200 px-3 py-2 text-xs text-slate-900 font-mono break-all">
                {typeof window !== "undefined"
                  ? `${window.location.origin}${captureLink.capture_path}`
                  : captureLink.capture_path}
              </code>
              <button
                type="button"
                onClick={() => {
                  const fullUrl =
                    typeof window !== "undefined"
                      ? `${window.location.origin}${captureLink.capture_path}`
                      : captureLink.capture_path;
                  void navigator.clipboard?.writeText(fullUrl);
                  setCopiedNotice(true);
                  window.setTimeout(() => setCopiedNotice(false), 2500);
                }}
                className="rounded-lg border border-slate-300 bg-white hover:bg-slate-50 px-3.5 py-2 text-xs font-semibold text-slate-800 transition"
              >
                {copiedNotice ? "✓ Copied!" : "Copy Link"}
              </button>
              <Link
                href={captureLink.capture_path}
                target="_blank"
                className="rounded-lg bg-sky-700 hover:bg-sky-800 text-white px-3.5 py-2 text-xs font-semibold shadow-sm transition"
              >
                Open Patient Capture Screen &nearr;
              </Link>
            </div>
          </section>
        )}

        {/* Error Alert with Retry */}
        {error && (
          <div
            role="alert"
            className="rounded-xl bg-rose-50 border border-rose-300 p-4 text-sm text-rose-900 flex flex-wrap items-center justify-between gap-3"
          >
            <div>
              <p className="font-semibold">Chart operation issue</p>
              <p className="text-xs text-rose-800 mt-0.5">{error}</p>
            </div>
            <button
              type="button"
              onClick={() => void fetchAllData(false)}
              className="rounded-lg border border-rose-300 bg-white hover:bg-rose-100 px-3 py-1.5 text-xs font-semibold text-rose-900"
            >
              Reload Chart
            </button>
          </div>
        )}

        {loading ? (
          <div
            role="status"
            aria-live="polite"
            className="rounded-xl bg-white border border-slate-200 py-14 px-4 text-center text-sm text-slate-600 shadow-clinical"
          >
            Loading longitudinal trajectories, medications, and concern
            scores&hellip;
          </div>
        ) : (
          <>
            {/* Insufficient Data Banner when fewer than 2 scans exist */}
            {visitCount < 2 && (
              <div
                role="status"
                className="rounded-xl bg-amber-50/90 border border-amber-300 p-4 flex flex-wrap items-center justify-between gap-3 text-xs text-amber-950"
              >
                <div className="space-y-0.5">
                  <p className="font-bold text-sm">
                    {visitCount === 0
                      ? "No baseline scan recorded yet"
                      : "Single baseline scan recorded — awaiting follow-up scan"}
                  </p>
                  <p className="text-amber-900">
                    Longitudinal delta (&Delta;) and trajectory verdicts require
                    at least 2 completed scans. Create a patient capture link to
                    record the next encounter.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => void handleGenerateCaptureLink()}
                  className="rounded-lg bg-amber-900 hover:bg-amber-950 text-white font-semibold px-3.5 py-2 text-xs shrink-0"
                >
                  Create Patient Capture Link
                </button>
              </div>
            )}

            {/* 1. TOP-3 PRIORITY CONCERNS & GROUNDED NARRATIVE SUMMARY */}
            <section
              aria-labelledby="priority-concerns-heading"
              className="space-y-4"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h2
                    id="priority-concerns-heading"
                    className="text-lg font-bold text-slate-900"
                  >
                    Top-3 Priority Concerns &amp; Grounded Narrative Summary
                  </h2>
                  <p className="text-xs text-slate-600">
                    Ranked by |&Delta;| &times; chief complaint relevance across{" "}
                    {visitCount} {visitCount === 1 ? "scan" : "scans"} &bull;{" "}
                    {CLINICAL_DISCLAIMER}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <ProvenanceBadge kind="measured" />
                  <ProvenanceBadge kind="hypothesis" />
                </div>
              </div>

              {flagsData?.summary && (
                <div className="rounded-xl bg-white border border-slate-200 border-l-4 border-l-sky-700 p-4 shadow-clinical space-y-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-xs font-bold uppercase tracking-wide text-sky-900">
                      Grounded Longitudinal Summary (Clinician Review)
                    </span>
                    <span className="text-[11px] text-slate-500">
                      {CLINICAL_DISCLAIMER}
                    </span>
                  </div>
                  <p className="text-sm text-slate-800 leading-relaxed">
                    {flagsData.summary}
                  </p>
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {topConcernsList.map((item, idx) => (
                  <article
                    key={item.concern}
                    aria-label={`Priority ${idx + 1}: ${item.label}`}
                    className="rounded-xl bg-white border border-slate-200 p-4 shadow-clinical flex flex-col justify-between space-y-3.5"
                  >
                    <div className="space-y-2">
                      <div className="flex items-start justify-between gap-2">
                        <span className="inline-flex items-center rounded bg-slate-900 px-2 py-0.5 text-[11px] font-bold text-white">
                          Priority #{idx + 1}
                        </span>
                        <VerdictBadge
                          verdict={item.verdict}
                          delta={item.delta}
                        />
                      </div>

                      <div>
                        <h3 className="text-base font-bold text-slate-900">
                          {item.label}
                        </h3>
                        <div className="mt-0.5">
                          <DirectionBadge
                            direction={item.direction}
                            mdc={item.mdc}
                          />
                        </div>
                      </div>
                    </div>

                    <div className="rounded-lg bg-slate-50 p-3 border border-slate-200/80 space-y-2.5">
                      <div className="grid grid-cols-3 gap-2 text-xs">
                        <div>
                          <span className="block text-[11px] text-slate-500">
                            Baseline
                          </span>
                          <strong className="font-mono text-sm text-slate-900">
                            {item.baseline_score ?? "—"}
                          </strong>
                          <span className="block text-[10px] font-mono text-slate-500">
                            {baselineDate || "—"}
                          </span>
                        </div>
                        <div>
                          <span className="block text-[11px] text-slate-500">
                            Latest
                          </span>
                          <strong className="font-mono text-sm text-slate-900">
                            {item.latest_score ?? "—"}
                          </strong>
                          <span className="block text-[10px] font-mono text-slate-500">
                            {latestDate || "—"}
                          </span>
                        </div>
                        <div>
                          <span className="block text-[11px] text-slate-500">
                            &Delta; vs Base
                          </span>
                          <strong className="font-mono text-sm text-slate-900">
                            {formatSignedDelta(item.delta)}
                          </strong>
                          <span className="block text-[10px] font-mono text-slate-500">
                            {item.pct_change !== null
                              ? `${formatSignedDelta(item.pct_change)}%`
                              : `MDC ±${item.mdc}`}
                          </span>
                        </div>
                      </div>

                      <div className="flex items-center justify-between pt-2 border-t border-slate-200/80">
                        <SeverityBadge
                          severity={
                            item.latest_severity ?? item.baseline_severity
                          }
                        />
                        <SparklineSvg
                          points={item.points}
                          verdict={item.verdict}
                          label={item.label}
                        />
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            </section>

            {/* 2. 12-CONCERN LONGITUDINAL SNAPSHOT MATRIX (OBSERVED MEASUREMENTS) */}
            <section
              aria-labelledby="snapshot-matrix-heading"
              className="space-y-3"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h2
                    id="snapshot-matrix-heading"
                    className="text-lg font-bold text-slate-900"
                  >
                    12-Concern Longitudinal Snapshot Matrix
                  </h2>
                  <p className="text-xs text-slate-600">
                    All 12 frozen YouCam S2S v2.0 skin metrics (0–100 scale) with
                    per-concern direction of good and Minimal Detectable Change
                    (MDC) thresholds.
                  </p>
                </div>
                <ProvenanceBadge kind="measured" />
              </div>

              <div
                tabIndex={0}
                role="region"
                aria-labelledby="snapshot-matrix-heading"
                className="table-wrapper rounded-xl border border-slate-200 bg-white shadow-clinical"
              >
                <table
                  className="responsive-data-table text-left text-xs text-slate-800"
                  style={
                    {
                      "--label-2": '"Direction & MDC"',
                      "--label-3": '"Baseline (0-100)"',
                      "--label-4": '"Latest (0-100)"',
                      "--label-5": '"Delta vs Base"',
                      "--label-6": '"Severity"',
                      "--label-7": '"Verdict"',
                      "--label-8": '"Trajectory"',
                    } as React.CSSProperties
                  }
                >
                  <thead className="bg-slate-100 text-slate-700 font-semibold text-[11px] uppercase tracking-wider border-b border-slate-200">
                    <tr>
                      <th
                        scope="col"
                        className="py-3 px-3.5 border-b border-slate-200"
                      >
                        Skin Concern Metric
                      </th>
                      <th
                        scope="col"
                        className="py-3 px-3.5 border-b border-slate-200"
                      >
                        Direction &amp; MDC
                      </th>
                      <th
                        scope="col"
                        className="py-3 px-3.5 border-b border-slate-200"
                      >
                        Baseline {baselineDate ? `(${baselineDate})` : ""}
                      </th>
                      <th
                        scope="col"
                        className="py-3 px-3.5 border-b border-slate-200"
                      >
                        Latest {latestDate ? `(${latestDate})` : ""}
                      </th>
                      <th
                        scope="col"
                        className="py-3 px-3.5 border-b border-slate-200"
                      >
                        &Delta; vs Baseline
                      </th>
                      <th
                        scope="col"
                        className="py-3 px-3.5 border-b border-slate-200"
                      >
                        Severity Bucket
                      </th>
                      <th
                        scope="col"
                        className="py-3 px-3.5 border-b border-slate-200"
                      >
                        Trajectory Verdict
                      </th>
                      <th
                        scope="col"
                        className="py-3 px-3.5 border-b border-slate-200"
                      >
                        Sparkline ({visitCount}{" "}
                        {visitCount === 1 ? "scan" : "scans"})
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    {(trends?.concerns || []).map((c) => {
                      const sev = c.latest_severity ?? c.baseline_severity;
                      return (
                        <tr
                          key={c.concern}
                          className="hover:bg-slate-50/90 transition"
                        >
                          <th
                            scope="row"
                            className="py-3 px-3.5 font-semibold text-slate-900"
                          >
                            <div>{c.label}</div>
                            <div className="font-mono text-[11px] font-normal text-slate-500">
                              {c.concern}
                            </div>
                          </th>
                          <td className="py-3 px-3.5">
                            <DirectionBadge
                              direction={c.direction}
                              mdc={c.mdc}
                              compact
                            />
                          </td>
                          <td className="py-3 px-3.5 font-mono text-xs text-slate-900">
                            {c.baseline_score !== null ? (
                              <span>
                                <strong>{c.baseline_score}</strong>
                                <span className="text-slate-400">/100</span>
                              </span>
                            ) : (
                              <span className="text-slate-400">&mdash;</span>
                            )}
                          </td>
                          <td className="py-3 px-3.5 font-mono text-xs text-slate-900">
                            {c.latest_score !== null ? (
                              <span>
                                <strong>{c.latest_score}</strong>
                                <span className="text-slate-400">/100</span>
                              </span>
                            ) : (
                              <span className="text-slate-500 italic font-sans">
                                Pending follow-up
                              </span>
                            )}
                          </td>
                          <td className="py-3 px-3.5 font-mono text-xs font-semibold text-slate-900">
                            {c.delta !== null ? (
                              <span>
                                {formatSignedDelta(c.delta)}
                                {c.pct_change !== null && (
                                  <span className="ml-1 font-normal text-[11px] text-slate-500">
                                    ({formatSignedDelta(c.pct_change)}%)
                                  </span>
                                )}
                              </span>
                            ) : (
                              <span className="text-slate-400">&mdash;</span>
                            )}
                          </td>
                          <td className="py-3 px-3.5">
                            <SeverityBadge severity={sev} />
                          </td>
                          <td className="py-3 px-3.5">
                            <VerdictBadge verdict={c.verdict} />
                          </td>
                          <td className="py-3 px-3.5">
                            <SparklineSvg
                              points={c.points}
                              verdict={c.verdict}
                              label={c.label}
                            />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>

            {/* 3. PRESCRIPTION CROSS-REFERENCING & TEMPORAL CORRELATIONS */}
            <section
              aria-labelledby="prescription-correlations-heading"
              className="space-y-4"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h2
                    id="prescription-correlations-heading"
                    className="text-lg font-bold text-slate-900"
                  >
                    Prescription Cross-Referencing &amp; Treatment Response
                    Trajectories
                  </h2>
                  <p className="text-xs text-slate-600 mt-0.5">
                    Temporal alignment of recorded medication start/end dates
                    with YouCam concern score movements relative to MDC.
                    Co-movement is presented for clinician review and does not
                    establish causal efficacy.
                  </p>
                </div>
                <div className="flex items-center gap-2.5">
                  <ProvenanceBadge kind="correlation" />
                  <button
                    type="button"
                    onClick={() => {
                      setMedDialogError(null);
                      addMedDialogRef.current?.showModal();
                    }}
                    className="rounded-lg border border-sky-300 bg-sky-50 hover:bg-sky-100 px-3 py-1.5 text-xs font-semibold text-sky-900 transition"
                  >
                    + Record Prescription
                  </button>
                </div>
              </div>

              {correlations.length === 0 ? (
                <div className="rounded-xl border border-dashed border-slate-300 p-6 text-center text-sm text-slate-600 bg-white space-y-2">
                  <p className="font-semibold text-slate-800">
                    No active or past medications recorded for this patient.
                  </p>
                  <p className="text-xs text-slate-600 max-w-lg mx-auto">
                    Record topicals, systemic prescriptions, or barrier repair
                    regimens to compare their initiation dates against skin
                    concern trajectories.
                  </p>
                  <div className="pt-1">
                    <button
                      type="button"
                      onClick={() => {
                        setMedDialogError(null);
                        addMedDialogRef.current?.showModal();
                      }}
                      className="rounded-lg bg-sky-700 hover:bg-sky-800 px-3.5 py-2 text-xs font-semibold text-white"
                    >
                      + Add Prescription / Regimen
                    </button>
                  </div>
                </div>
              ) : (
                <div className="space-y-3">
                  {correlations.map((c) => {
                    const statusBadge = MED_RESPONSE_CONFIG[
                      c.response_status
                    ] || {
                      symbol: "•",
                      label: c.response_status,
                      classes: "bg-slate-100 text-slate-700 border-slate-300",
                    };
                    const catStyle =
                      MED_CATEGORY_STYLES[c.category] ||
                      "bg-slate-100 text-slate-800 border-slate-300";

                    return (
                      <article
                        key={c.medication_id}
                        aria-label={`Medication correlation: ${c.medication_name}`}
                        className="rounded-xl bg-white border border-slate-200 p-4 shadow-clinical space-y-3.5"
                      >
                        <div className="flex flex-wrap items-start justify-between gap-2 border-b border-slate-200 pb-3">
                          <div className="space-y-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <h3 className="text-base font-bold text-slate-900">
                                {c.medication_name}
                              </h3>
                              <span
                                className={`rounded border px-2 py-0.5 text-xs font-semibold ${catStyle}`}
                              >
                                {c.category_label}
                              </span>
                              <span
                                className={`inline-flex items-center gap-1 rounded border px-2.5 py-0.5 text-xs font-semibold ${statusBadge.classes}`}
                              >
                                <span aria-hidden="true">
                                  {statusBadge.symbol}
                                </span>
                                <span>{statusBadge.label}</span>
                              </span>
                            </div>
                            <div className="text-xs text-slate-600 flex flex-wrap items-center gap-x-3 gap-y-1">
                              <span>
                                <strong className="text-slate-800">
                                  Dosage:
                                </strong>{" "}
                                {c.dose || "Standard regimen"}
                              </span>
                              <span aria-hidden="true">&bull;</span>
                              <span>
                                <strong className="text-slate-800">
                                  Started:
                                </strong>{" "}
                                <span className="font-mono">{c.start_date}</span>{" "}
                                ({c.days_on_therapy} days on therapy)
                              </span>
                              {c.baseline_visit_date && (
                                <>
                                  <span aria-hidden="true">&bull;</span>
                                  <span>
                                    <strong className="text-slate-800">
                                      Comparison Window:
                                    </strong>{" "}
                                    <span className="font-mono">
                                      {c.baseline_visit_date} &rarr;{" "}
                                      {c.latest_visit_date || "Awaiting follow-up"}
                                    </span>
                                  </span>
                                </>
                              )}
                              {c.end_date && (
                                <>
                                  <span aria-hidden="true">&bull;</span>
                                  <span>
                                    <strong className="text-slate-800">
                                      Ended:
                                    </strong>{" "}
                                    <span className="font-mono">
                                      {c.end_date}
                                    </span>
                                  </span>
                                </>
                              )}
                            </div>
                          </div>

                          <button
                            type="button"
                            onClick={() =>
                              requestDeleteMedication({
                                id: c.medication_id,
                                name: c.medication_name,
                                dose: c.dose,
                              })
                            }
                            className="rounded-lg border border-rose-200 bg-rose-50/60 hover:bg-rose-100 text-xs text-rose-800 font-semibold px-2.5 py-1 transition"
                          >
                            Remove
                          </button>
                        </div>

                        {/* Clinical correlation note framed for clinician review */}
                        <div className="rounded-lg bg-slate-50 p-3 border border-slate-200/80 text-xs space-y-1 text-slate-800">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <p className="font-semibold text-slate-900">
                              {c.headline}
                            </p>
                            <span className="text-[11px] font-medium text-slate-500">
                              Temporal Correlation &bull; {CLINICAL_DISCLAIMER}
                            </span>
                          </div>
                          <p className="text-slate-600 leading-relaxed">
                            {c.clinical_note}
                          </p>
                        </div>

                        {/* Correlated metric movements breakdown */}
                        {c.concern_responses.length > 0 && (
                          <div className="pt-0.5">
                            <h4 className="text-xs font-semibold text-slate-700 mb-2">
                              Co-Moving Target &amp; Watch Metrics (Baseline vs
                              Latest Follow-Up)
                            </h4>
                            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-2.5">
                              {c.concern_responses.map((cr) => (
                                <div
                                  key={cr.concern}
                                  className="rounded-lg border border-slate-200 bg-white p-2.5 text-xs space-y-1"
                                >
                                  <div className="flex items-center justify-between gap-1">
                                    <span className="font-semibold text-slate-900">
                                      {cr.label}
                                    </span>
                                    <span
                                      className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded border font-mono text-[11px] font-semibold ${
                                        cr.is_improved
                                          ? "bg-emerald-50 text-emerald-900 border-emerald-300"
                                          : cr.is_worsened
                                          ? "bg-rose-50 text-rose-900 border-rose-300"
                                          : "bg-slate-100 text-slate-700 border-slate-300"
                                      }`}
                                    >
                                      <span aria-hidden="true">
                                        {cr.is_improved
                                          ? "↗"
                                          : cr.is_worsened
                                          ? "↘"
                                          : "→"}
                                      </span>
                                      <span>
                                        &Delta; {formatSignedDelta(cr.delta)}
                                      </span>
                                    </span>
                                  </div>
                                  <div className="font-mono text-[11px] text-slate-600">
                                    {cr.baseline_score} &rarr; {cr.latest_score}{" "}
                                    <span className="text-slate-500">
                                      (MDC &plusmn;{cr.mdc})
                                    </span>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </article>
                    );
                  })}
                </div>
              )}
            </section>

            {/* 4. MATERIALIZED TREATMENT FLAGS & GROUNDED ATTRIBUTION HYPOTHESES */}
            <section
              aria-labelledby="hypotheses-heading"
              className="space-y-3"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h2
                    id="hypotheses-heading"
                    className="text-lg font-bold text-slate-900"
                  >
                    Materialized Treatment Flags &amp; Grounded Attribution
                    Hypotheses
                  </h2>
                  <p className="text-xs text-slate-600">
                    Non-diagnostic hypotheses generated from structured visit
                    deltas and patient-reported regimen notes.{" "}
                    <strong className="font-semibold text-slate-800">
                      {CLINICAL_DISCLAIMER}
                    </strong>
                  </p>
                </div>
                <ProvenanceBadge kind="hypothesis" />
              </div>

              {(flagsData?.flags || []).length === 0 ? (
                <div className="rounded-xl border border-dashed border-slate-300 bg-white p-6 text-center text-xs text-slate-600">
                  No materialized treatment flags generated yet. Record at least
                  one visit scan and click &ldquo;Regenerate Flags&rdquo;.
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {(flagsData?.flags || []).map((flag) => (
                    <article
                      key={flag.id}
                      className="rounded-xl bg-white border border-slate-200 p-3.5 shadow-clinical space-y-2"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="text-sm font-bold text-slate-900">
                          {concernsByKey[flag.concern]?.label || flag.concern}
                        </span>
                        <VerdictBadge
                          verdict={flag.verdict}
                          delta={flag.delta}
                        />
                      </div>
                      <p className="text-xs text-slate-700 leading-relaxed">
                        {flag.hypothesis}
                      </p>
                    </article>
                  ))}
                </div>
              )}
            </section>

            {/* 5. LONGITUDINAL VISITS TIMELINE WITH EXPANDABLE PER-VISIT SCORES */}
            <section
              aria-labelledby="visits-timeline-heading"
              className="space-y-3"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h2
                    id="visits-timeline-heading"
                    className="text-lg font-bold text-slate-900"
                  >
                    Longitudinal Visits Timeline ({visits.length}{" "}
                    {visits.length === 1 ? "Encounter" : "Encounters"})
                  </h2>
                  <p className="text-xs text-slate-600">
                    Chronological encounter intake notes and stored YouCam S2S
                    v2.0 concern measurements.
                  </p>
                </div>
                <ProvenanceBadge kind="measured" />
              </div>

              {visits.length === 0 ? (
                <div className="rounded-xl border border-dashed border-slate-300 bg-white p-6 text-center text-sm text-slate-600">
                  No clinic visit encounters recorded for this patient yet.
                </div>
              ) : (
                <div className="space-y-3">
                  {visits.map((v, idx) => {
                    const isBaseline = idx === 0;
                    const isLatest = idx === visits.length - 1 && visits.length > 1;
                    return (
                      <article
                        key={v.id}
                        aria-label={`Visit ${idx + 1} on ${v.visit_date}`}
                        className="rounded-xl bg-white border border-slate-200 p-4 shadow-clinical space-y-3"
                      >
                        <div className="flex flex-wrap items-start justify-between gap-4">
                          <div className="space-y-1.5 max-w-3xl">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="rounded bg-slate-900 text-white text-xs font-bold px-2.5 py-0.5">
                                Visit #{idx + 1}
                              </span>
                              {isBaseline && (
                                <span className="rounded border border-slate-300 bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-800">
                                  Baseline Reference
                                </span>
                              )}
                              {isLatest && (
                                <span className="rounded border border-sky-300 bg-sky-50 px-2 py-0.5 text-[11px] font-semibold text-sky-900">
                                  Latest Follow-Up
                                </span>
                              )}
                              <span className="text-sm font-bold font-mono text-slate-900">
                                {v.visit_date}
                              </span>
                              <span
                                className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 text-[11px] font-semibold uppercase ${
                                  v.youcam_status === "success"
                                    ? "bg-emerald-50 text-emerald-900 border-emerald-300"
                                    : v.youcam_status === "failed"
                                    ? "bg-rose-50 text-rose-900 border-rose-300"
                                    : "bg-amber-50 text-amber-900 border-amber-300"
                                }`}
                              >
                                <span aria-hidden="true">
                                  {v.youcam_status === "success"
                                    ? "✓"
                                    : v.youcam_status === "failed"
                                    ? "!"
                                    : "◷"}
                                </span>
                                <span>{v.youcam_status}</span>
                              </span>
                            </div>

                            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 pt-1 text-xs">
                              <div className="rounded-lg bg-slate-50 border border-slate-200/70 p-2.5">
                                <span className="block text-[11px] font-semibold text-slate-500">
                                  Chief Complaint
                                </span>
                                <span className="text-slate-900 font-medium">
                                  {v.chief_complaint || "None recorded"}
                                </span>
                              </div>
                              <div className="rounded-lg bg-slate-50 border border-slate-200/70 p-2.5">
                                <span className="block text-[11px] font-semibold text-slate-500">
                                  Reported Routine
                                </span>
                                <span className="text-slate-800">
                                  {v.routine_text || "None recorded"}
                                </span>
                              </div>
                              <div className="rounded-lg bg-slate-50 border border-slate-200/70 p-2.5">
                                <span className="block text-[11px] font-semibold text-slate-500">
                                  Treatment Changes
                                </span>
                                <span className="text-slate-800">
                                  {v.treatment_changes || "None recorded"}
                                </span>
                              </div>
                            </div>
                          </div>

                          <div className="text-xs text-slate-600 font-mono shrink-0">
                            Analysis v{v.analysis_version} &bull;{" "}
                            {v.concern_scores.length} concerns scored
                          </div>
                        </div>

                        {v.concern_scores.length > 0 && (
                          <details className="group border-t border-slate-200 pt-2.5">
                            <summary className="cursor-pointer text-xs font-semibold text-sky-800 hover:text-sky-950 select-none inline-flex items-center gap-1.5">
                              <span>
                                Inspect {v.concern_scores.length} recorded visit
                                scores (0–100 scale)
                              </span>
                            </summary>
                            <div className="mt-2.5 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2">
                              {v.concern_scores.map((cs) => (
                                <div
                                  key={cs.id}
                                  className="rounded-lg border border-slate-200 bg-slate-50/70 p-2 text-xs flex flex-col justify-between gap-1"
                                >
                                  <span className="font-semibold text-slate-900">
                                    {concernsByKey[cs.concern]?.label ||
                                      cs.concern}
                                  </span>
                                  <div className="flex items-center justify-between gap-1 pt-0.5">
                                    <span className="font-mono font-bold text-slate-900">
                                      {cs.score}
                                    </span>
                                    <SeverityBadge severity={cs.severity} />
                                  </div>
                                </div>
                              ))}
                            </div>
                          </details>
                        )}
                      </article>
                    );
                  })}
                </div>
              )}
            </section>
          </>
        )}

        {/* Add Medication Dialog Modal (with explicit label htmlFor associations) */}
        <dialog
          ref={addMedDialogRef}
          aria-labelledby="add-med-dialog-title"
          className="rounded-xl border border-slate-300 bg-white p-6 shadow-xl max-w-lg w-full"
        >
          <form onSubmit={handleAddMedicationSubmit} className="space-y-4">
            <div className="flex items-start justify-between gap-3 border-b border-slate-200 pb-3">
              <div>
                <h2
                  id="add-med-dialog-title"
                  className="text-base font-bold text-slate-900"
                >
                  Record New Prescription / Active Regimen
                </h2>
                <p className="text-xs text-slate-600 mt-0.5">
                  Cross-references therapy start date with longitudinal skin
                  concern scores. {CLINICAL_DISCLAIMER}
                </p>
              </div>
              <button
                type="button"
                aria-label="Close record prescription dialog"
                onClick={() => addMedDialogRef.current?.close()}
                className="rounded-lg p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-800"
              >
                <span aria-hidden="true" className="text-lg leading-none">
                  &times;
                </span>
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label
                  htmlFor="med-form-name"
                  className="block font-semibold text-slate-800 mb-1"
                >
                  Medication / Product Name{" "}
                  <span className="text-rose-700">*</span>
                </label>
                <input
                  id="med-form-name"
                  type="text"
                  required
                  autoFocus
                  value={medFormName}
                  onChange={(e) => setMedFormName(e.target.value)}
                  placeholder="e.g., Adapalene 0.1% Gel, Spironolactone"
                  className="clinical-input w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
                />
                <div className="field-error-msg">
                  Please enter a medication or product name.
                </div>
              </div>

              <div>
                <label
                  htmlFor="med-form-category"
                  className="block font-semibold text-slate-800 mb-1"
                >
                  Therapeutic Category <span className="text-rose-700">*</span>
                </label>
                <select
                  id="med-form-category"
                  value={medFormCategory}
                  onChange={(e) => setMedFormCategory(e.target.value)}
                  className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900"
                >
                  <option value="topical_retinoid">Topical Retinoid</option>
                  <option value="oral_retinoid">
                    Oral Retinoid (Isotretinoin)
                  </option>
                  <option value="barrier_repair">
                    Barrier Repair / Ceramide Cream
                  </option>
                  <option value="topical_acid">
                    Exfoliating Acid (AHA / BHA / Azelaic)
                  </option>
                  <option value="anti_androgen">
                    Anti-Androgen (Spironolactone)
                  </option>
                  <option value="oral_antibiotic">
                    Oral Antibiotic (Doxycycline)
                  </option>
                  <option value="topical_antimicrobial">
                    Topical Antimicrobial (Benzoyl Peroxide)
                  </option>
                  <option value="corticosteroid">Topical Corticosteroid</option>
                  <option value="other">Other Regimen Product</option>
                </select>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label
                    htmlFor="med-form-dose"
                    className="block font-semibold text-slate-800 mb-1"
                  >
                    Dosage &amp; Frequency
                  </label>
                  <input
                    id="med-form-dose"
                    type="text"
                    value={medFormDose}
                    onChange={(e) => setMedFormDose(e.target.value)}
                    placeholder="e.g., Pea-sized amount nightly"
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
                  />
                </div>

                <div>
                  <label
                    htmlFor="med-form-start-date"
                    className="block font-semibold text-slate-800 mb-1"
                  >
                    Start Date <span className="text-rose-700">*</span>
                  </label>
                  <input
                    id="med-form-start-date"
                    type="date"
                    required
                    value={medFormStartDate}
                    onChange={(e) => setMedFormStartDate(e.target.value)}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
                  />
                </div>
              </div>

              <div>
                <label
                  htmlFor="med-form-notes"
                  className="block font-semibold text-slate-800 mb-1"
                >
                  Clinical Instructions / Tolerability Notes
                </label>
                <textarea
                  id="med-form-notes"
                  value={medFormNotes}
                  onChange={(e) => setMedFormNotes(e.target.value)}
                  rows={2}
                  placeholder="e.g., Titrated from every other night to nightly."
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
                />
              </div>
            </div>

            {medDialogError && (
              <div
                role="alert"
                className="rounded-lg bg-rose-50 border border-rose-300 px-3 py-2 text-xs font-medium text-rose-900"
              >
                {medDialogError}
              </div>
            )}

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-200">
              <button
                type="button"
                onClick={() => addMedDialogRef.current?.close()}
                className="px-4 py-2 text-xs font-semibold text-slate-700 border border-slate-300 bg-white hover:bg-slate-50 rounded-lg"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={savingMed}
                className="px-4 py-2 text-xs font-semibold text-white bg-sky-700 hover:bg-sky-800 disabled:opacity-60 rounded-lg shadow-sm transition"
              >
                {savingMed ? "Saving..." : "Save & Correlate"}
              </button>
            </div>
          </form>
        </dialog>

        {/* Destructive Action Confirmation Modal (per modern-web-guidance 'dialog' Rule 1: autofocus on safe Cancel action) */}
        <dialog
          ref={deleteMedDialogRef}
          aria-labelledby="delete-med-dialog-title"
          aria-describedby="delete-med-dialog-desc"
          className="rounded-xl border border-slate-300 bg-white p-6 shadow-xl max-w-md w-full"
        >
          <div className="space-y-4">
            <div className="space-y-1.5">
              <span className="inline-flex items-center gap-1 rounded bg-rose-50 border border-rose-200 px-2 py-0.5 text-[11px] font-bold text-rose-900">
                Confirm Removal
              </span>
              <h2
                id="delete-med-dialog-title"
                className="text-base font-bold text-slate-900"
              >
                Remove medication record from chart?
              </h2>
              <p
                id="delete-med-dialog-desc"
                className="text-xs text-slate-600 leading-relaxed"
              >
                You are about to remove{" "}
                <strong className="text-slate-900">
                  {pendingDeleteMed?.name || "this medication"}
                </strong>
                {pendingDeleteMed?.dose ? ` (${pendingDeleteMed.dose})` : ""}{" "}
                from {patient?.full_name || "the patient"}&apos;s longitudinal
                chart. Stored visit scans and concern scores will remain intact.
              </p>
            </div>

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-200">
              <button
                type="button"
                autoFocus
                disabled={deletingMed}
                onClick={() => {
                  deleteMedDialogRef.current?.close();
                  setPendingDeleteMed(null);
                }}
                className="rounded-lg border border-slate-300 bg-white hover:bg-slate-50 px-4 py-2 text-xs font-semibold text-slate-800"
              >
                Keep Record
              </button>
              <button
                type="button"
                disabled={deletingMed}
                onClick={() => void confirmDeleteMedication()}
                className="rounded-lg bg-rose-700 hover:bg-rose-800 disabled:opacity-60 px-4 py-2 text-xs font-semibold text-white shadow-sm"
              >
                {deletingMed ? "Removing..." : "Remove Medication"}
              </button>
            </div>
          </div>
        </dialog>

        {/* Direct Real Visit Photo Upload Modal */}
        <dialog
          ref={uploadVisitDialogRef}
          aria-labelledby="upload-visit-dialog-title"
          className="rounded-xl border border-slate-300 bg-white p-6 shadow-xl max-w-lg w-full"
        >
          <form onSubmit={handleUploadVisitSubmit} className="space-y-4">
            <div className="flex items-start justify-between gap-3 border-b border-slate-200 pb-3">
              <div>
                <h2
                  id="upload-visit-dialog-title"
                  className="text-base font-bold text-slate-900"
                >
                  Upload Real Patient Visit Photo (Live YouCam AI)
                </h2>
                <p className="text-xs text-slate-600 mt-0.5">
                  {PRIVACY_NOTICE} {CLINICAL_DISCLAIMER}
                </p>
              </div>
              <button
                type="button"
                onClick={() => uploadVisitDialogRef.current?.close()}
                aria-label="Close upload visit photo dialog"
                className="rounded-lg p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-800"
              >
                <span aria-hidden="true" className="text-lg leading-none">
                  &times;
                </span>
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label
                  htmlFor="visit-photo-file"
                  className="block font-semibold text-slate-800 mb-1"
                >
                  Facial Selfie Image (JPEG / PNG / WebP){" "}
                  <span className="text-rose-700">*</span>
                </label>
                <input
                  id="visit-photo-file"
                  type="file"
                  required
                  accept="image/jpeg,image/png,image/webp"
                  onChange={(e) =>
                    setVisitImageFile(e.target.files?.[0] || null)
                  }
                  className="w-full rounded-lg border border-slate-300 bg-slate-50 px-3 py-2 text-xs text-slate-900"
                />
              </div>

              <div>
                <label
                  htmlFor="visit-date-input"
                  className="block font-semibold text-slate-800 mb-1"
                >
                  Visit Date <span className="text-rose-700">*</span>
                </label>
                <input
                  id="visit-date-input"
                  type="date"
                  required
                  value={visitDateInput}
                  onChange={(e) => setVisitDateInput(e.target.value)}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
                />
              </div>

              <div>
                <label
                  htmlFor="visit-chief-complaint"
                  className="block font-semibold text-slate-800 mb-1"
                >
                  Chief Complaint
                </label>
                <input
                  id="visit-chief-complaint"
                  type="text"
                  value={visitChiefComplaint}
                  onChange={(e) => setVisitChiefComplaint(e.target.value)}
                  placeholder="e.g., Inflammatory acne on cheeks, redness"
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
                />
              </div>

              <div>
                <label
                  htmlFor="visit-routine-text"
                  className="block font-semibold text-slate-800 mb-1"
                >
                  Current Routine
                </label>
                <input
                  id="visit-routine-text"
                  type="text"
                  value={visitRoutineText}
                  onChange={(e) => setVisitRoutineText(e.target.value)}
                  placeholder="e.g., Gentle cleanser, moisturizer, SPF 50"
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
                />
              </div>

              <div>
                <label
                  htmlFor="visit-treatment-changes"
                  className="block font-semibold text-slate-800 mb-1"
                >
                  Treatment / Regimen Changes
                </label>
                <input
                  id="visit-treatment-changes"
                  type="text"
                  value={visitTreatmentChanges}
                  onChange={(e) => setVisitTreatmentChanges(e.target.value)}
                  placeholder="e.g., Started adapalene 0.1% nightly"
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
                />
              </div>
            </div>

            {uploadVisitError && (
              <div
                role="alert"
                className="rounded-lg bg-rose-50 border border-rose-300 px-3 py-2 text-xs font-medium text-rose-900"
              >
                {uploadVisitError}
              </div>
            )}

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-200">
              <button
                type="button"
                disabled={uploadingVisit}
                onClick={() => uploadVisitDialogRef.current?.close()}
                className="px-4 py-2 text-xs font-semibold text-slate-700 border border-slate-300 bg-white hover:bg-slate-50 rounded-lg"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={uploadingVisit}
                className="px-4 py-2 text-xs font-semibold text-white bg-emerald-700 hover:bg-emerald-800 disabled:opacity-60 rounded-lg shadow-sm transition"
              >
                {uploadingVisit
                  ? "Running Live YouCam Analysis..."
                  : "Analyze & Save Visit"}
              </button>
            </div>
          </form>
        </dialog>
      </main>
    </>
  );
}
