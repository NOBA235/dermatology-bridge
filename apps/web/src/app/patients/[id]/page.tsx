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

interface PatientVisitsPayload {
  patient_id: string;
  visit_count: number;
  visits: VisitRecord[];
  disclaimer: string;
}

const SEVERITY_BADGE_CLASSES: Record<string, string> = {
  clear: "bg-emerald-100 text-emerald-800 border-emerald-300",
  mild: "bg-sky-100 text-sky-800 border-sky-300",
  moderate: "bg-amber-100 text-amber-900 border-amber-300",
  severe: "bg-rose-100 text-rose-900 border-rose-300",
};

const VERDICT_BADGE_CLASSES: Record<string, string> = {
  improving: "bg-emerald-100 text-emerald-800 border-emerald-300",
  stalled: "bg-slate-100 text-slate-700 border-slate-300",
  worsening: "bg-rose-100 text-rose-800 border-rose-300",
  insufficient_data: "bg-slate-50 text-slate-500 border-slate-200",
};

const MED_RESPONSE_BADGES: Record<
  string,
  { label: string; className: string }
> = {
  clinically_responsive: {
    label: "Clinically Responsive",
    className: "bg-emerald-100 text-emerald-900 border-emerald-300",
  },
  early_favorable_trend: {
    label: "Early Response Detected",
    className: "bg-sky-100 text-sky-900 border-sky-300",
  },
  minimal_change: {
    label: "Minimal Change (|Δ| < MDC)",
    className: "bg-slate-100 text-slate-700 border-slate-300",
  },
  potential_adverse_flare: {
    label: "Watch: Potential Barrier Disruption",
    className: "bg-rose-100 text-rose-900 border-rose-300",
  },
  insufficient_followup: {
    label: "Within Onset Window",
    className: "bg-zinc-100 text-zinc-700 border-zinc-300",
  },
};

const MED_CATEGORY_COLORS: Record<string, string> = {
  topical_retinoid: "bg-purple-100 text-purple-900 border-purple-200",
  oral_retinoid: "bg-violet-100 text-violet-900 border-violet-200",
  barrier_repair: "bg-teal-100 text-teal-900 border-teal-200",
  topical_acid: "bg-amber-100 text-amber-900 border-amber-200",
  anti_androgen: "bg-pink-100 text-pink-900 border-pink-200",
  oral_antibiotic: "bg-indigo-100 text-indigo-900 border-indigo-200",
  topical_antimicrobial: "bg-cyan-100 text-cyan-900 border-cyan-200",
  corticosteroid: "bg-orange-100 text-orange-900 border-orange-200",
  other: "bg-slate-100 text-slate-900 border-slate-200",
};

function SparklineSvg({
  points,
  verdict,
}: {
  points: { score: string; visit_date: string }[];
  verdict: string;
}) {
  if (!points || points.length === 0) {
    return <span className="text-xs text-slate-400">No scans</span>;
  }
  const scores = points.map((p) => Number(p.score));
  const minVal = Math.max(0, Math.min(...scores) - 8);
  const maxVal = Math.min(100, Math.max(...scores) + 8);
  const span = Math.max(10, maxVal - minVal);
  const width = 92;
  const height = 26;

  const coords = scores.map((val, idx) => {
    const x =
      scores.length === 1
        ? width / 2
        : 8 + (idx / (scores.length - 1)) * (width - 16);
    const y = height - 4 - ((val - minVal) / span) * (height - 8);
    return { x, y, val };
  });

  const strokeColor =
    verdict === "improving"
      ? "#15803d"
      : verdict === "worsening"
      ? "#be123c"
      : "#475569";

  const polylinePoints = coords.map((c) => `${c.x},${c.y}`).join(" ");

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`Trend sparkline with ${points.length} data points`}
      className="overflow-visible"
    >
      {coords.length > 1 && (
        <polyline
          fill="none"
          stroke={strokeColor}
          strokeWidth="2"
          points={polylinePoints}
        />
      )}
      {coords.map((c, idx) => (
        <circle
          key={idx}
          cx={c.x}
          cy={c.y}
          r="3"
          fill={strokeColor}
          stroke="#ffffff"
          strokeWidth="1"
        />
      ))}
    </svg>
  );
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
  const [regenerating, setRegenerating] = useState(false);
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copiedNotice, setCopiedNotice] = useState(false);

  // New Prescription modal state
  const addMedDialogRef = useRef<HTMLDialogElement>(null);
  const [medFormName, setMedFormName] = useState("");
  const [medFormCategory, setMedFormCategory] = useState("topical_retinoid");
  const [medFormDose, setMedFormDose] = useState("");
  const [medFormStartDate, setMedFormStartDate] = useState(
    new Date().toISOString().split("T")[0]
  );
  const [medFormNotes, setMedFormNotes] = useState("");
  const [savingMed, setSavingMed] = useState(false);

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

  async function handleGenerateCaptureLink() {
    try {
      const tokenOut = await apiFetch<CaptureTokenResponse>(
        `/api/patients/${patientId}/capture-token`,
        { method: "POST" }
      );
      setCaptureLink(tokenOut);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not generate capture link."
      );
    }
  }

  async function handleRegenerateFlags() {
    setRegenerating(true);
    try {
      const updated = await apiFetch<PatientFlagsResponse>(
        `/api/patients/${patientId}/flags/regenerate`,
        { method: "POST" }
      );
      setFlagsData(updated);
      await fetchAllData(true);
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
    if (!medFormName.trim()) return;
    setSavingMed(true);
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
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to record medication."
      );
    } finally {
      setSavingMed(false);
    }
  }

  async function handleDeleteMedication(medId: string) {
    if (!window.confirm("Remove this medication record from the patient chart?")) {
      return;
    }
    try {
      await deletePatientMedication(patientId, medId);
      await fetchAllData(true);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to delete medication."
      );
    }
  }

  const concernsByKey: Record<string, ConcernTrend> = {};
  for (const c of trends?.concerns || []) {
    concernsByKey[c.concern] = c;
  }

  const topConcernsList = (flagsData?.top_concerns || [])
    .map((key) => concernsByKey[key])
    .filter(Boolean);

  return (
    <main className="max-w-7xl w-full mx-auto px-4 sm:px-6 py-8 space-y-8">
      {/* Header bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <Link
            href="/patients"
            className="text-xs font-semibold text-sky-700 hover:underline"
          >
            &larr; Back to Patient Directory
          </Link>
          <h1 className="text-2xl font-bold text-slate-900 mt-1">
            {patient ? patient.full_name : "Loading Patient Chart..."}
          </h1>
          <p className="text-xs text-slate-600 mt-0.5">
            Chart Ref: <strong>{patient?.external_ref || "N/A"}</strong> &bull;
            DOB: <strong>{patient?.dob || "N/A"}</strong> &bull; Consent:{" "}
            <strong>{patient?.consent_version || "v1-2026-10"}</strong> &bull;{" "}
            <span className="font-semibold text-slate-800">
              {CLINICAL_DISCLAIMER}
            </span>
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <button
            type="button"
            onClick={() => addMedDialogRef.current?.showModal()}
            className="rounded-lg border border-slate-300 bg-white hover:bg-slate-50 text-slate-900 text-xs font-semibold px-3.5 py-2.5 transition"
          >
            + Add Prescription / Regimen
          </button>

          <button
            type="button"
            onClick={handleGenerateCaptureLink}
            className="rounded-lg bg-sky-700 hover:bg-sky-800 text-white text-xs font-semibold px-3.5 py-2.5 transition"
          >
            Create Patient Capture Link
          </button>

          <button
            type="button"
            onClick={handleRegenerateFlags}
            disabled={regenerating}
            className="rounded-lg border border-slate-300 bg-white hover:bg-slate-100 disabled:opacity-60 text-slate-800 text-xs font-semibold px-3.5 py-2.5 transition"
          >
            {regenerating ? "Recomputing..." : "Regenerate Flags"}
          </button>

          <button
            type="button"
            onClick={handleDownloadReportPdf}
            disabled={downloadingPdf}
            className="rounded-lg bg-slate-900 hover:bg-slate-800 disabled:opacity-60 text-white text-xs font-semibold px-3.5 py-2.5 transition"
          >
            {downloadingPdf
              ? "Building 3-Page PDF..."
              : "Download 3-Page Report (PDF)"}
          </button>
        </div>
      </div>

      {/* Clinical notice */}
      <div className="rounded-xl bg-sky-50 border border-sky-200 px-4 py-3 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-800">
        <span>
          <strong>Clinical Decision-Support Notice:</strong>{" "}
          {CLINICAL_DISCLAIMER} All longitudinal flags, medication attributions,
          and hypotheses are non-diagnostic decision-support observations.
        </span>
        <span className="text-slate-600">
          Live auto-refresh active (polls every 4s)
        </span>
      </div>

      {captureLink && (
        <section
          aria-label="Generated patient capture link"
          className="rounded-xl bg-white border-2 border-sky-600 p-4 shadow-sm space-y-2"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-bold text-slate-900">
              Signed Mobile Capture Link Ready (Valid for 30 Minutes)
            </h2>
            <span className="text-xs text-slate-600">{PRIVACY_NOTICE}</span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <code className="flex-1 min-w-[240px] rounded bg-slate-100 px-3 py-2 text-xs text-slate-800 break-all">
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
                window.setTimeout(() => setCopiedNotice(false), 2000);
              }}
              className="rounded-lg border border-slate-300 bg-white hover:bg-slate-100 px-3 py-2 text-xs font-semibold text-slate-800"
            >
              {copiedNotice ? "Copied!" : "Copy Link"}
            </button>
            <Link
              href={captureLink.capture_path}
              target="_blank"
              className="rounded-lg bg-sky-700 hover:bg-sky-800 text-white px-3.5 py-2 text-xs font-semibold"
            >
              Open Patient Capture Screen &nearr;
            </Link>
          </div>
        </section>
      )}

      {error && (
        <div
          role="alert"
          className="rounded-lg bg-rose-50 border border-rose-200 p-4 text-sm text-rose-800"
        >
          {error}
        </div>
      )}

      {loading ? (
        <div className="py-12 text-center text-sm text-slate-500">
          Loading longitudinal trajectories, medications, and concern scores...
        </div>
      ) : (
        <>
          {/* Top-3 Prioritized Concerns */}
          <section className="space-y-4">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="text-lg font-bold text-slate-900">
                Top-3 Priority Concerns &amp; Grounded Narrative Summary
              </h2>
              <span className="text-xs text-slate-600">
                Ranked by |&Delta;| &times; chief complaint relevance &bull;{" "}
                {CLINICAL_DISCLAIMER}
              </span>
            </div>

            {flagsData?.summary && (
              <div className="rounded-xl bg-white border border-slate-200 border-l-4 border-l-slate-900 p-4 shadow-sm text-sm text-slate-800 leading-relaxed">
                {flagsData.summary}
              </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {topConcernsList.map((item, idx) => (
                <div
                  key={item.concern}
                  className="rounded-xl bg-white border border-slate-200 p-4 shadow-sm flex flex-col justify-between space-y-3"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <span className="text-xs font-bold uppercase text-sky-700">
                        Priority #{idx + 1}
                      </span>
                      <h3 className="text-base font-bold text-slate-900">
                        {item.label}
                      </h3>
                      <p className="text-xs text-slate-500">
                        {item.direction === "higher_is_better"
                          ? "Higher score = healthier"
                          : "Lower score = healthier"}{" "}
                        (MDC {item.mdc})
                      </p>
                    </div>
                    <span
                      className={`inline-block rounded border px-2 py-0.5 text-xs font-bold uppercase ${
                        VERDICT_BADGE_CLASSES[item.verdict] || ""
                      }`}
                    >
                      {item.verdict}
                    </span>
                  </div>

                  <div className="flex items-center justify-between bg-slate-50 rounded-lg p-3 border border-slate-100">
                    <div className="text-xs space-y-0.5">
                      <div>
                        Baseline:{" "}
                        <strong className="text-slate-900">
                          {item.baseline_score ?? "—"}
                        </strong>
                      </div>
                      <div>
                        Latest:{" "}
                        <strong className="text-slate-900">
                          {item.latest_score ?? "—"}
                        </strong>
                      </div>
                      <div>
                        &Delta; vs Baseline:{" "}
                        <strong className="text-slate-900">
                          {item.delta ?? "—"}
                        </strong>
                      </div>
                    </div>
                    <div>
                      <SparklineSvg points={item.points} verdict={item.verdict} />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* PRESCRIPTION CROSS-REFERENCING & ATTRIBUTION ANALYSIS */}
          <section className="space-y-4">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <div>
                <h2 className="text-lg font-bold text-slate-900">
                  Prescription Cross-Referencing &amp; Treatment Response Trajectories
                </h2>
                <p className="text-xs text-slate-600 mt-0.5">
                  Automated correlation of medication start/stop dates against
                  YouCam skin concern inflection points.
                </p>
              </div>
              <button
                type="button"
                onClick={() => addMedDialogRef.current?.showModal()}
                className="text-xs font-semibold text-sky-700 hover:text-sky-800"
              >
                + Record Prescription
              </button>
            </div>

            {correlations.length === 0 ? (
              <div className="rounded-xl border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500 bg-white">
                No active or past medications recorded for this patient. Click{" "}
                <strong>&ldquo;+ Add Prescription / Regimen&rdquo;</strong> to cross-reference
                therapies with skin analysis trends.
              </div>
            ) : (
              <div className="space-y-3">
                {correlations.map((c) => {
                  const statusBadge =
                    MED_RESPONSE_BADGES[c.response_status] || {
                      label: c.response_status,
                      className: "bg-slate-100 text-slate-700 border-slate-300",
                    };
                  const catColor =
                    MED_CATEGORY_COLORS[c.category] ||
                    "bg-slate-100 text-slate-800 border-slate-200";

                  return (
                    <div
                      key={c.medication_id}
                      className="rounded-xl bg-white border border-slate-200 p-4 shadow-sm space-y-3"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-2 border-b border-slate-100 pb-3">
                        <div className="space-y-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <h3 className="text-base font-bold text-slate-900">
                              {c.medication_name}
                            </h3>
                            <span
                              className={`rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${catColor}`}
                            >
                              {c.category_label}
                            </span>
                            <span
                              className={`rounded border px-2 py-0.5 text-xs font-bold ${statusBadge.className}`}
                            >
                              {statusBadge.label}
                            </span>
                          </div>
                          <div className="text-xs text-slate-600 flex flex-wrap items-center gap-2">
                            <span>
                              <strong>Dosage:</strong> {c.dose || "Standard dose"}
                            </span>
                            &bull;
                            <span>
                              <strong>Started:</strong> {c.start_date} (
                              {c.days_on_therapy} days on therapy)
                            </span>
                            {c.end_date && (
                              <>
                                &bull;
                                <span>
                                  <strong>Ended:</strong> {c.end_date}
                                </span>
                              </>
                            )}
                          </div>
                        </div>

                        <button
                          type="button"
                          onClick={() => handleDeleteMedication(c.medication_id)}
                          className="text-xs text-rose-600 hover:text-rose-800 font-semibold px-2 py-1"
                        >
                          Remove
                        </button>
                      </div>

                      {/* Clinical attribution headline */}
                      <div className="rounded-lg bg-slate-50 p-3 border border-slate-100 text-xs space-y-1 text-slate-800">
                        <p className="font-semibold text-slate-900">
                          {c.headline}
                        </p>
                        <p className="text-slate-600">{c.clinical_note}</p>
                      </div>

                      {/* Concern movements breakdown */}
                      {c.concern_responses.length > 0 && (
                        <div className="pt-1">
                          <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider mb-2">
                            Correlated Metric Trajectories (Baseline vs Latest Follow-up)
                          </h4>
                          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-2">
                            {c.concern_responses.map((cr) => (
                              <div
                                key={cr.concern}
                                className="rounded-lg border border-slate-200 bg-white p-2.5 text-xs space-y-1"
                              >
                                <div className="flex items-center justify-between">
                                  <span className="font-bold text-slate-900">
                                    {cr.label}
                                  </span>
                                  <span
                                    className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                      cr.is_improved
                                        ? "bg-emerald-100 text-emerald-800"
                                        : cr.is_worsened
                                        ? "bg-rose-100 text-rose-800"
                                        : "bg-slate-100 text-slate-600"
                                    }`}
                                  >
                                    &Delta; {cr.delta}
                                  </span>
                                </div>
                                <div className="text-[11px] text-slate-500">
                                  {cr.baseline_score} &rarr; {cr.latest_score} (MDC{" "}
                                  {cr.mdc})
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </section>

          {/* 12-Concern Snapshot Matrix */}
          <section className="space-y-4">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="text-lg font-bold text-slate-900">
                12-Concern Longitudinal Snapshot Matrix
              </h2>
              <span className="text-xs text-slate-600">
                {visits.length} scans recorded &bull; {CLINICAL_DISCLAIMER}
              </span>
            </div>

            <div
              tabIndex={0}
              aria-label="12-concern longitudinal scores and trends"
              className="@container overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
            >
              <table className="w-full text-left text-xs text-slate-800 border-collapse">
                <thead>
                  <tr className="bg-slate-50 text-slate-700 uppercase font-semibold text-[11px] tracking-wider">
                    <th className="py-3 px-3.5 border-b border-slate-200">
                      Skin Metric
                    </th>
                    <th className="py-3 px-3.5 border-b border-slate-200">
                      Direction
                    </th>
                    <th className="py-3 px-3.5 border-b border-slate-200">
                      Baseline
                    </th>
                    <th className="py-3 px-3.5 border-b border-slate-200">
                      Latest
                    </th>
                    <th className="py-3 px-3.5 border-b border-slate-200">
                      &Delta;
                    </th>
                    <th className="py-3 px-3.5 border-b border-slate-200">
                      Severity
                    </th>
                    <th className="py-3 px-3.5 border-b border-slate-200">
                      Verdict
                    </th>
                    <th className="py-3 px-3.5 border-b border-slate-200">
                      Trajectory
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {(trends?.concerns || []).map((c) => {
                    const sev =
                      c.latest_severity || c.baseline_severity || "mild";
                    return (
                      <tr key={c.concern} className="hover:bg-slate-50">
                        <th className="py-3 px-3.5 font-semibold text-slate-900">
                          {c.label}{" "}
                          <span className="text-xs font-normal text-slate-500">
                            ({c.concern})
                          </span>
                        </th>
                        <td className="py-3 px-3.5 text-xs text-slate-600">
                          {c.direction === "higher_is_better"
                            ? "Higher = Better"
                            : "Lower = Better"}
                        </td>
                        <td className="py-3 px-3.5 font-mono">
                          {c.baseline_score ?? "—"}
                        </td>
                        <td className="py-3 px-3.5 font-mono">
                          {c.latest_score ?? "—"}
                        </td>
                        <td className="py-3 px-3.5 font-mono font-semibold">
                          {c.delta ?? "—"}
                        </td>
                        <td className="py-3 px-3.5">
                          <span
                            className={`inline-block rounded border px-2 py-0.5 text-[11px] font-bold uppercase ${
                              SEVERITY_BADGE_CLASSES[sev] || ""
                            }`}
                          >
                            {sev}
                          </span>
                        </td>
                        <td className="py-3 px-3.5">
                          <span
                            className={`inline-block rounded border px-2 py-0.5 text-[11px] font-bold uppercase ${
                              VERDICT_BADGE_CLASSES[c.verdict] || ""
                            }`}
                          >
                            {c.verdict}
                          </span>
                        </td>
                        <td className="py-3 px-3.5">
                          <SparklineSvg points={c.points} verdict={c.verdict} />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>

          {/* Grounded Attribution Hypotheses */}
          <section className="space-y-3">
            <h2 className="text-lg font-bold text-slate-900">
              Materialized Treatment Flags &amp; Grounded Attribution Hypotheses
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {(flagsData?.flags || []).map((flag) => (
                <div
                  key={flag.id}
                  className="rounded-xl bg-white border border-slate-200 p-3.5 shadow-sm space-y-1.5"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-bold text-slate-900">
                      {concernsByKey[flag.concern]?.label || flag.concern}
                    </span>
                    <span
                      className={`inline-block rounded border px-2 py-0.5 text-[11px] font-bold uppercase ${
                        VERDICT_BADGE_CLASSES[flag.verdict] || ""
                      }`}
                    >
                      {flag.verdict} (&Delta; {flag.delta})
                    </span>
                  </div>
                  <p className="text-xs text-slate-700 leading-relaxed">
                    {flag.hypothesis}
                  </p>
                </div>
              ))}
            </div>
          </section>

          {/* Visits Timeline */}
          <section className="space-y-3">
            <h2 className="text-lg font-bold text-slate-900">
              Longitudinal Visits Timeline ({visits.length} Encounters)
            </h2>
            <div className="space-y-3">
              {visits.map((v, idx) => (
                <div
                  key={v.id}
                  className="rounded-xl bg-white border border-slate-200 p-4 shadow-sm flex flex-wrap items-start justify-between gap-4"
                >
                  <div className="space-y-1 max-w-3xl">
                    <div className="flex items-center gap-2">
                      <span className="rounded bg-slate-900 text-white text-xs font-bold px-2 py-0.5">
                        Visit #{idx + 1}
                      </span>
                      <span className="text-sm font-bold text-slate-900">
                        {v.visit_date}
                      </span>
                      <span className="text-xs text-emerald-700 font-semibold uppercase">
                        {v.youcam_status}
                      </span>
                    </div>
                    <p className="text-xs text-slate-800">
                      <strong>Chief Complaint:</strong>{" "}
                      {v.chief_complaint || "None recorded"}
                    </p>
                    <p className="text-xs text-slate-600">
                      <strong>Routine:</strong>{" "}
                      {v.routine_text || "None recorded"}
                    </p>
                    <p className="text-xs text-slate-700">
                      <strong>Treatment Changes:</strong>{" "}
                      {v.treatment_changes || "None recorded"}
                    </p>
                  </div>
                  <div className="text-xs text-slate-500">
                    Analysis v{v.analysis_version} &bull;{" "}
                    {v.concern_scores.length} concerns scored
                  </div>
                </div>
              ))}
            </div>
          </section>
        </>
      )}

      {/* Add Medication Dialog Modal */}
      <dialog
        ref={addMedDialogRef}
        className="rounded-2xl border border-slate-300 bg-white p-6 shadow-2xl max-w-lg w-full backdrop:bg-slate-900/50"
      >
        <form onSubmit={handleAddMedicationSubmit} className="space-y-4">
          <div className="flex items-center justify-between border-b border-slate-200 pb-3">
            <h3 className="text-base font-bold text-slate-900">
              Record New Prescription / Active Regimen
            </h3>
            <button
              type="button"
              onClick={() => addMedDialogRef.current?.close()}
              className="text-slate-400 hover:text-slate-600 text-lg font-bold"
            >
              &times;
            </button>
          </div>

          <div className="space-y-3 text-xs">
            <div>
              <label className="block font-semibold text-slate-700 mb-1">
                Medication / Product Name *
              </label>
              <input
                type="text"
                required
                value={medFormName}
                onChange={(e) => setMedFormName(e.target.value)}
                placeholder="e.g. Adapalene 0.1% Gel, Spironolactone"
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-sky-500"
              />
            </div>

            <div>
              <label className="block font-semibold text-slate-700 mb-1">
                Therapeutic Category *
              </label>
              <select
                value={medFormCategory}
                onChange={(e) => setMedFormCategory(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-sky-500"
              >
                <option value="topical_retinoid">Topical Retinoid</option>
                <option value="oral_retinoid">Oral Retinoid (Isotretinoin)</option>
                <option value="barrier_repair">Barrier Repair / Ceramide Cream</option>
                <option value="topical_acid">Exfoliating Acid (AHA / BHA / Azelaic)</option>
                <option value="anti_androgen">Anti-Androgen (Spironolactone)</option>
                <option value="oral_antibiotic">Oral Antibiotic (Doxycycline)</option>
                <option value="topical_antimicrobial">Topical Antimicrobial (Benzoyl Peroxide)</option>
                <option value="corticosteroid">Topical Corticosteroid</option>
                <option value="other">Other Regimen Product</option>
              </select>
            </div>

            <div>
              <label className="block font-semibold text-slate-700 mb-1">
                Dosage &amp; Frequency
              </label>
              <input
                type="text"
                value={medFormDose}
                onChange={(e) => setMedFormDose(e.target.value)}
                placeholder="e.g. Pea-sized amount nightly to dry skin"
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-sky-500"
              />
            </div>

            <div>
              <label className="block font-semibold text-slate-700 mb-1">
                Start Date *
              </label>
              <input
                type="date"
                required
                value={medFormStartDate}
                onChange={(e) => setMedFormStartDate(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-sky-500"
              />
            </div>

            <div>
              <label className="block font-semibold text-slate-700 mb-1">
                Clinical Instructions / Notes
              </label>
              <textarea
                value={medFormNotes}
                onChange={(e) => setMedFormNotes(e.target.value)}
                rows={2}
                placeholder="e.g. Titrated from every other night to nightly."
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-sky-500"
              />
            </div>
          </div>

          <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-200">
            <button
              type="button"
              onClick={() => addMedDialogRef.current?.close()}
              className="px-3.5 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100 rounded-lg"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={savingMed}
              className="px-4 py-2 text-xs font-semibold text-white bg-sky-700 hover:bg-sky-800 disabled:opacity-60 rounded-lg transition"
            >
              {savingMed ? "Saving..." : "Save & Correlate"}
            </button>
          </div>
        </form>
      </dialog>
    </main>
  );
}
