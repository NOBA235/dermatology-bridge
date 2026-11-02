"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  API_BASE_URL,
  apiFetch,
  CLINICAL_DISCLAIMER,
  getStoredToken,
  PatientRecord,
  PRIVACY_NOTICE,
} from "@/lib/api";
import {
  ClinicalInlineNotice,
  ClinicianWorkspaceHeader,
  DermBridgeCrestIcon,
} from "@/components/ClinicalShell";

interface PatientListPayload {
  patients: PatientRecord[];
  total: number;
  disclaimer: string;
}

export default function PatientsDirectoryPage() {
  const router = useRouter();
  const [patients, setPatients] = useState<PatientRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  // New Patient Modal state
  const createDialogRef = useRef<HTMLDialogElement>(null);
  const [creating, setCreating] = useState(false);
  const [dialogError, setDialogError] = useState<string | null>(null);
  const [newPatientName, setNewPatientName] = useState("");
  const [newPatientRef, setNewPatientRef] = useState("");
  const [newPatientDob, setNewPatientDob] = useState("");
  const [newPatientNotes, setNewPatientNotes] = useState("");

  // Delete Patient Confirmation Modal state
  const deleteDialogRef = useRef<HTMLDialogElement>(null);
  const [pendingDeletePatient, setPendingDeletePatient] =
    useState<PatientRecord | null>(null);
  const [deletingPatient, setDeletingPatient] = useState(false);
  const [actionFeedback, setActionFeedback] = useState<string | null>(null);

  const loadPatients = useCallback(
    async (query = "") => {
      if (!getStoredToken()) {
        router.replace("/login");
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const qs = query.trim()
          ? `?q=${encodeURIComponent(query.trim())}`
          : "";
        const data = await apiFetch<PatientListPayload>(`/api/patients${qs}`);
        setPatients(data.patients);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Failed to load patient directory."
        );
      } finally {
        setLoading(false);
      }
    },
    [router]
  );

  useEffect(() => {
    void loadPatients("");
  }, [loadPatients]);

  function handleSearchSubmit(e: React.FormEvent) {
    e.preventDefault();
    void loadPatients(searchQuery);
  }

  async function handleCreatePatientSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!newPatientName.trim()) {
      setDialogError("Patient full name is required.");
      return;
    }
    setCreating(true);
    setDialogError(null);
    try {
      const created = await apiFetch<PatientRecord>("/api/patients", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          full_name: newPatientName.trim(),
          external_ref: newPatientRef.trim() || null,
          dob: newPatientDob || null,
          consent_version: "v1-2026-10",
          notes: newPatientNotes.trim() || null,
        }),
      });
      createDialogRef.current?.close();
      setNewPatientName("");
      setNewPatientRef("");
      setNewPatientDob("");
      setNewPatientNotes("");
      router.push(`/patients/${created.id}`);
    } catch (err) {
      setDialogError(
        err instanceof Error ? err.message : "Could not create patient record."
      );
    } finally {
      setCreating(false);
    }
  }

  function requestDeletePatient(pt: PatientRecord) {
    setPendingDeletePatient(pt);
    deleteDialogRef.current?.showModal();
  }

  async function confirmDeletePatient() {
    if (!pendingDeletePatient) return;
    const token = getStoredToken();
    if (!token) {
      router.replace("/login");
      return;
    }
    setDeletingPatient(true);
    try {
      const res = await fetch(
        `${API_BASE_URL}/api/patients/${pendingDeletePatient.id}`,
        {
          method: "DELETE",
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      if (!res.ok) {
        throw new Error(`Could not delete patient chart (HTTP ${res.status})`);
      }
      const deletedName = pendingDeletePatient.full_name;
      deleteDialogRef.current?.close();
      setPendingDeletePatient(null);
      await loadPatients(searchQuery);
      setActionFeedback(
        `Removed patient chart "${deletedName}" and associated scans.`
      );
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to delete patient chart."
      );
      deleteDialogRef.current?.close();
    } finally {
      setDeletingPatient(false);
    }
  }

  const totalCompletedVisits = patients.reduce(
    (sum, pt) => sum + (pt.visit_count || 0),
    0
  );
  const primaryPatientId = patients[0]?.id;

  return (
    <>
      <ClinicianWorkspaceHeader
        searchValue={searchQuery}
        onSearchChange={(val) => setSearchQuery(val)}
        onSearchSubmit={(val) => void loadPatients(val)}
        rightActions={
          <button
            type="button"
            onClick={() => {
              setDialogError(null);
              createDialogRef.current?.showModal();
            }}
            className="inline-flex items-center gap-2 rounded-full bg-[#0b2c44] hover:bg-[#071f31] text-white px-4 py-2 text-xs font-bold uppercase tracking-wider shadow-sm border border-white/15 transition"
          >
            <span>+ ENROLL PATIENT</span>
            <span aria-hidden="true">&rarr;</span>
          </button>
        }
      />

      {/* DERMNET-STYLE WHITE HERO & CLINICAL KPI STAT STRIP */}
      <section
        aria-label="Clinical platform overview"
        className="bg-white border-b border-[#cbdce9]"
      >
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-7 sm:py-9">
          <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-6">
            <div className="space-y-2.5 max-w-xl">
              <h1 className="text-2xl sm:text-3xl font-extrabold text-[#0f1e2e] tracking-tight leading-tight">
                The clinician&apos;s longitudinal dermatology decision-support
                workstation
              </h1>
              <div>
                <a
                  href="#patient-directory-section"
                  className="inline-flex items-center gap-1.5 text-sm font-semibold text-[#0072ab] hover:text-[#004e78] hover:underline"
                >
                  <span>
                    Read more about DermBridge &amp; YouCam S2S v2.0 Skin AI
                  </span>
                  <span aria-hidden="true">&rarr;</span>
                </a>
              </div>
            </div>

            {/* DermNet-style 3-column numerical KPI counter strip */}
            <dl className="grid grid-cols-3 gap-6 sm:gap-10 text-center lg:text-center shrink-0">
              <div>
                <dd className="text-xl sm:text-2xl font-extrabold text-[#0f1e2e] tracking-tight">
                  12 S2S
                </dd>
                <dt className="text-xs sm:text-sm font-medium text-[#0072ab] mt-0.5">
                  Skin concern topics
                </dt>
              </div>
              <div>
                <dd className="text-xl sm:text-2xl font-extrabold text-[#0f1e2e] tracking-tight">
                  {totalCompletedVisits > 0
                    ? `${totalCompletedVisits}+`
                    : "90-Day"}
                </dd>
                <dt className="text-xs sm:text-sm font-medium text-[#0072ab] mt-0.5">
                  Clinical scan series
                </dt>
              </div>
              <div>
                <dd className="text-xl sm:text-2xl font-extrabold text-[#0f1e2e] tracking-tight">
                  {patients.length}
                </dd>
                <dt className="text-xs sm:text-sm font-medium text-[#0072ab] mt-0.5">
                  Enrolled charts
                </dt>
              </div>
            </dl>
          </div>

          {/* DERMNET-STYLE ASYMMETRIC CLINICAL ATLAS FEATURE GRID */}
          <div
            id="clinical-atlas"
            className="mt-7 grid grid-cols-1 lg:grid-cols-12 gap-5"
          >
            {/* Left Large Spotlight Card (7 columns on desktop, spans 2 rows) */}
            <Link
              href={
                primaryPatientId
                  ? `/patients/${primaryPatientId}`
                  : "#patient-directory-section"
              }
              className="dermnet-atlas-card relative lg:col-span-7 lg:row-span-2 min-h-[300px] sm:min-h-[370px] flex flex-col justify-between p-6 sm:p-8 text-white group bg-[#1f0d09]"
            >
              {/* Free Open Clinical Photography (Wikimedia Commons - Acne vulgaris) */}
              <img
                src="/images/atlas/acne-erythema.jpg"
                alt="Clinical presentation of inflammatory acne vulgaris and facial erythema"
                width={903}
                height={1657}
                fetchPriority="high"
                decoding="async"
                className="absolute inset-0 h-full w-full object-cover object-[center_35%] opacity-45 group-hover:opacity-55 group-hover:scale-105 transition-all duration-500 ease-out"
              />
              {/* High-contrast clinical scrim overlay ensuring WCAG AAA typography */}
              <div
                aria-hidden="true"
                className="pointer-events-none absolute inset-0 bg-gradient-to-t from-[#1f0d09]/95 via-[#35140d]/75 to-[#1a0a07]/60"
              />
              {/* Subtle clinical contour circles mimicking erythema zones */}
              <div
                aria-hidden="true"
                className="pointer-events-none absolute inset-0 opacity-25"
                style={{
                  backgroundImage:
                    "radial-gradient(circle at 35% 65%, rgba(255,195,175,0.45) 0%, transparent 45%), radial-gradient(circle at 72% 48%, rgba(255,180,160,0.4) 0%, transparent 42%)",
                }}
              />

              <div className="relative z-10 space-y-2 max-w-lg">
                <span className="inline-block rounded bg-black/40 backdrop-blur-sm border border-white/20 px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wider text-amber-100">
                  Featured Longitudinal Cohort &bull; YouCam S2S v2.0
                </span>
                <h2 className="text-2xl sm:text-4xl font-extrabold tracking-tight text-white drop-shadow-sm">
                  Inflammatory erythema &amp; acne vulgaris
                </h2>
                <span
                  aria-hidden="true"
                  className="inline-block text-xl font-bold text-white/90 group-hover:translate-x-1.5 transition-transform"
                >
                  &rarr;
                </span>
              </div>

              <div className="relative z-10 flex flex-wrap items-end justify-between gap-4 pt-8">
                <div className="flex items-center gap-2.5 opacity-90">
                  <DermBridgeCrestIcon className="h-12 w-12 text-white/80" />
                  <div className="text-[11px] leading-tight text-white/90">
                    <div className="font-bold">DermBridge&reg; Clinical</div>
                    <div className="text-white/75">
                      acne (MDC &plusmn;5.0) &bull; redness (MDC &plusmn;4.0)
                    </div>
                  </div>
                </div>

                <span className="rounded-full bg-[#0b2c44]/90 border border-white/25 px-3.5 py-1.5 text-xs font-bold text-white shadow-sm">
                  {primaryPatientId
                    ? "Open Longitudinal Case Chart \u2192"
                    : "Inspect Cohort Directory \u2192"}
                </span>
              </div>
            </Link>

            {/* Top-Right Clinical Feature Card (5 columns on desktop) */}
            <Link
              href={
                primaryPatientId
                  ? `/patients/${primaryPatientId}#snapshot-matrix-heading`
                  : "#patient-directory-section"
              }
              className="dermnet-atlas-card relative lg:col-span-5 min-h-[175px] flex flex-col justify-between p-5 sm:p-6 text-white group bg-[#1b1009]"
            >
              {/* Free Open Clinical Photography (Wikimedia Commons - Solar lentigo / age spot) */}
              <img
                src="/images/atlas/hyperpigmentation-age-spots.jpg"
                alt="Clinical cutaneous hyperpigmentation and solar lentigo lesion"
                width={960}
                height={720}
                loading="eager"
                decoding="async"
                className="absolute inset-0 h-full w-full object-cover object-center opacity-40 group-hover:opacity-50 group-hover:scale-105 transition-all duration-500 ease-out"
              />
              <div
                aria-hidden="true"
                className="pointer-events-none absolute inset-0 bg-gradient-to-t from-[#1b1009]/95 via-[#2b1810]/75 to-[#1c0f08]/60"
              />

              <div className="relative z-10 space-y-1">
                <h2 className="text-lg sm:text-xl font-extrabold tracking-tight text-white leading-snug">
                  Cutaneous hyperpigmentation &amp; UV age spots
                </h2>
                <span
                  aria-hidden="true"
                  className="inline-block text-base font-bold text-white/90 group-hover:translate-x-1 transition-transform"
                >
                  &rarr;
                </span>
              </div>

              <div className="relative z-10 flex items-end justify-between gap-2 pt-3">
                <div className="flex items-center gap-2 opacity-90">
                  <DermBridgeCrestIcon className="h-8 w-8 text-white/80" />
                  <span className="text-[11px] font-semibold text-white/85">
                    age_spot (MDC &plusmn;3.5) &bull; radiance &bull; texture
                  </span>
                </div>
              </div>
            </Link>

            {/* Bottom-Right Clinical Feature Card (5 columns on desktop) */}
            <Link
              href={
                primaryPatientId
                  ? `/patients/${primaryPatientId}#prescription-correlations-heading`
                  : "#patient-directory-section"
              }
              className="dermnet-atlas-card relative lg:col-span-5 min-h-[175px] flex flex-col justify-between p-5 sm:p-6 text-white group bg-[#140e0c]"
            >
              {/* Free Open Clinical Photography (Wikimedia Commons - Barrier moisturizer cream) */}
              <img
                src="/images/atlas/barrier-moisturizer.jpg"
                alt="Topical emollient barrier formulation for epidermal moisture support"
                width={960}
                height={640}
                loading="eager"
                decoding="async"
                className="absolute inset-0 h-full w-full object-cover object-center opacity-40 group-hover:opacity-50 group-hover:scale-105 transition-all duration-500 ease-out"
              />
              <div
                aria-hidden="true"
                className="pointer-events-none absolute inset-0 bg-gradient-to-t from-[#140e0c]/95 via-[#211815]/75 to-[#150d0a]/60"
              />

              <div className="relative z-10 space-y-1">
                <h2 className="text-lg sm:text-xl font-extrabold tracking-tight text-white leading-snug">
                  Epidermal barrier moisture &amp; Rx cross-referencing
                </h2>
                <span
                  aria-hidden="true"
                  className="inline-block text-base font-bold text-white/90 group-hover:translate-x-1 transition-transform"
                >
                  &rarr;
                </span>
              </div>

              <div className="relative z-10 flex items-end justify-between gap-2 pt-3">
                <div className="flex items-center gap-2 opacity-90">
                  <DermBridgeCrestIcon className="h-8 w-8 text-white/80" />
                  <span className="text-[11px] font-semibold text-white/85">
                    Adapalene &bull; Spironolactone &bull; Ceramide Barrier
                  </span>
                </div>
              </div>
            </Link>
          </div>
        </div>
      </section>

      <main
        id="main-content"
        className="mx-auto w-full max-w-7xl px-4 py-7 sm:px-6 sm:py-9 space-y-6"
      >
        {/* Directory Title & Inline Clinical Notice */}
        <section
          id="patient-directory-section"
          aria-labelledby="directory-heading"
          className="space-y-4"
        >
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div className="space-y-1">
              <span className="inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-[#006599]">
                <span>Bridge Dermatology Clinic</span>
                <span aria-hidden="true">&bull;</span>
                <span>Longitudinal Cohort Registry</span>
              </span>
              <h2
                id="directory-heading"
                className="text-xl sm:text-2xl font-extrabold tracking-tight text-ink-primary"
              >
                Patient Longitudinal Directory
              </h2>
              <p className="text-sm text-ink-secondary">
                Find an enrolled patient chart by name, chart reference, or
                standing clinical note, or enroll a new patient for guided
                YouCam S2S v2.0 skin tracking.
              </p>
            </div>

            <button
              type="button"
              onClick={() => {
                setDialogError(null);
                createDialogRef.current?.showModal();
              }}
              className="clinical-button clinical-button-primary"
            >
              <span>+ Enroll New Patient</span>
              <span aria-hidden="true">&rarr;</span>
            </button>
          </div>

          <ClinicalInlineNotice />
        </section>

        {/* Search & Filter Controls */}
        <section
          aria-label="Search patient directory"
          className="clinical-card p-4 sm:p-5"
        >
          <form
            role="search"
            onSubmit={handleSearchSubmit}
            className="flex flex-col sm:flex-row items-stretch sm:items-end gap-3"
          >
            <div className="flex-1">
              <label
                htmlFor="patient-directory-search"
                className="block text-xs font-bold uppercase tracking-wider text-[#006599] mb-1.5"
              >
                Find Patient Chart
              </label>
              <input
                id="patient-directory-search"
                type="search"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search by patient name, chart reference (e.g. PT-1001), or clinical note..."
                className="clinical-input w-full px-3.5 py-2 text-sm"
              />
            </div>
            <div className="flex items-center gap-2">
              <button
                type="submit"
                className="clinical-button clinical-button-primary"
              >
                Search Directory
              </button>
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => {
                    setSearchQuery("");
                    void loadPatients("");
                  }}
                  className="clinical-button clinical-button-secondary"
                >
                  Clear Filter
                </button>
              )}
            </div>
          </form>
        </section>

        {/* Action Feedback Toast */}
        {actionFeedback && (
          <div
            role="status"
            aria-live="polite"
            className="rounded-xl bg-emerald-50 border border-emerald-300 px-4 py-3 text-xs font-semibold text-emerald-950 flex items-center justify-between gap-2"
          >
            <span>✓ {actionFeedback}</span>
            <button
              type="button"
              onClick={() => setActionFeedback(null)}
              className="underline text-emerald-900 hover:text-emerald-950"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Error Alert with Retry */}
        {error && (
          <div
            role="alert"
            className="rounded-xl border border-[#e3b5b0] bg-[#fbeae8] p-4 text-sm text-[#6e1f18] flex flex-wrap items-center justify-between gap-3"
          >
            <div>
              <p className="font-semibold">Unable to load patient directory</p>
              <p className="text-xs mt-0.5">{error}</p>
            </div>
            <button
              type="button"
              onClick={() => void loadPatients(searchQuery)}
              className="clinical-button clinical-button-secondary"
            >
              Retry
            </button>
          </div>
        )}

        {/* Responsive Patient Directory Table */}
        <section aria-labelledby="directory-table-caption">
          <div
            tabIndex={0}
            role="region"
            aria-labelledby="directory-table-caption"
            className="table-wrapper clinical-card overflow-hidden"
          >
            <table
              className="responsive-data-table text-left text-sm text-ink-primary"
              style={
                {
                  "--label-2": '"Chart Ref"',
                  "--label-3": '"Date of Birth"',
                  "--label-4": '"Completed Visits"',
                  "--label-5": '"Latest Scan"',
                  "--label-6": '"Consent"',
                  "--label-7": '"Action"',
                } as React.CSSProperties
              }
            >
              <caption
                id="directory-table-caption"
                className="sr-only sm:not-sr-only text-left px-5 py-3 text-xs font-bold uppercase tracking-wider text-[#006599] bg-[#edf4f9] border-b border-[#cbdce9]"
              >
                Clinic patients enrolled in longitudinal skin tracking (
                {patients.length}{" "}
                {patients.length === 1 ? "record" : "records"})
              </caption>
              <thead className="bg-[#006599] text-white text-xs font-semibold uppercase tracking-wider border-b border-[#004e78]">
                <tr>
                  <th scope="col" className="py-3.5 px-5">
                    Patient Identity &amp; Standing Notes
                  </th>
                  <th scope="col" className="py-3.5 px-4">
                    Chart Ref
                  </th>
                  <th scope="col" className="py-3.5 px-4">
                    Date of Birth
                  </th>
                  <th scope="col" className="py-3.5 px-4">
                    Completed Visits
                  </th>
                  <th scope="col" className="py-3.5 px-4">
                    Latest Scan Date
                  </th>
                  <th scope="col" className="py-3.5 px-4">
                    Consent
                  </th>
                  <th scope="col" className="py-3.5 px-5 text-right">
                    Chart Action
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#dde8f0]">
                {loading ? (
                  <tr>
                    <td
                      colSpan={7}
                      role="status"
                      aria-live="polite"
                      className="py-12 px-4 text-center text-sm text-ink-secondary"
                    >
                      Loading enrolled patient charts&hellip;
                    </td>
                  </tr>
                ) : patients.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="py-12 px-6 text-center">
                      <div className="max-w-md mx-auto space-y-3">
                        <p className="text-sm font-semibold text-ink-primary">
                          {searchQuery
                            ? `No patient charts matched "${searchQuery}".`
                            : "No patients enrolled in this clinic directory yet."}
                        </p>
                        <p className="text-xs text-ink-secondary">
                          {searchQuery
                            ? "Try clearing the search filter or searching by chart reference."
                            : "Enroll a patient to begin recording guided skin scans, medications, and longitudinal trajectory reports."}
                        </p>
                        <div className="pt-1 flex justify-center gap-2">
                          {searchQuery ? (
                            <button
                              type="button"
                              onClick={() => {
                                setSearchQuery("");
                                void loadPatients("");
                              }}
                              className="clinical-button clinical-button-secondary"
                            >
                              Show All Patients
                            </button>
                          ) : (
                            <button
                              type="button"
                              onClick={() => {
                                setDialogError(null);
                                createDialogRef.current?.showModal();
                              }}
                              className="clinical-button clinical-button-primary"
                            >
                              + Enroll First Patient
                            </button>
                          )}
                        </div>
                      </div>
                    </td>
                  </tr>
                ) : (
                  patients.map((pt) => (
                    <tr
                      key={pt.id}
                      className="hover:bg-[#f0f7fc] transition-colors"
                    >
                      <th
                        scope="row"
                        className="py-4 px-5 font-bold text-ink-primary"
                      >
                        <Link
                          href={`/patients/${pt.id}`}
                          className="text-[#006599] hover:text-[#004e78] hover:underline text-base"
                        >
                          {pt.full_name}
                        </Link>
                        {pt.notes && (
                          <p className="text-xs font-normal text-ink-secondary mt-0.5 max-w-md">
                            {pt.notes}
                          </p>
                        )}
                      </th>
                      <td className="py-4 px-4 font-mono text-xs font-semibold text-ink-secondary">
                        {pt.external_ref || "—"}
                      </td>
                      <td className="py-4 px-4 font-mono text-xs text-ink-secondary">
                        {pt.dob || "—"}
                      </td>
                      <td className="py-4 px-4">
                        <span
                          className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-semibold border ${
                            pt.visit_count >= 2
                              ? "bg-[#e3f1fa] text-[#00507a] border-[#b3d7ed]"
                              : pt.visit_count === 1
                              ? "bg-[#f8efe0] text-[#694815] border-[#dec59b]"
                              : "bg-slate-100 text-slate-600 border-slate-300"
                          }`}
                        >
                          <span aria-hidden="true">
                            {pt.visit_count >= 2
                              ? "●"
                              : pt.visit_count === 1
                              ? "◐"
                              : "○"}
                          </span>
                          <span>
                            {pt.visit_count}{" "}
                            {pt.visit_count === 1 ? "visit" : "visits"}
                          </span>
                        </span>
                      </td>
                      <td className="py-4 px-4 font-mono text-xs text-ink-secondary">
                        {pt.latest_visit_date || "No scans yet"}
                      </td>
                      <td className="py-4 px-4">
                        <span className="inline-flex items-center gap-1 rounded border border-[#b8d8ed] bg-[#edf4f9] px-2 py-0.5 text-xs font-mono text-[#0f1e2e]">
                          <span
                            aria-hidden="true"
                            className="text-[#006599] font-bold"
                          >
                            ✓
                          </span>
                          <span>{pt.consent_version}</span>
                        </span>
                      </td>
                      <td className="py-4 px-5 text-right">
                        <div className="inline-flex items-center justify-end gap-2">
                          <Link
                            href={`/patients/${pt.id}`}
                            className="clinical-button clinical-button-primary text-xs"
                          >
                            <span>Open Chart</span>
                            <span aria-hidden="true">&rarr;</span>
                          </Link>
                          <button
                            type="button"
                            onClick={() => requestDeletePatient(pt)}
                            className="clinical-button clinical-button-danger text-xs px-2.5"
                            aria-label={`Remove patient chart for ${pt.full_name}`}
                          >
                            Remove
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>

        {/* Enroll New Patient Modal Dialog */}
        <dialog
          ref={createDialogRef}
          aria-labelledby="enroll-patient-dialog-title"
          className="clinical-card p-6 max-w-lg w-full"
        >
          <form onSubmit={handleCreatePatientSubmit} className="space-y-4">
            <div className="flex items-start justify-between gap-3 border-b border-[#cbdce9] pb-3">
              <div>
                <h2
                  id="enroll-patient-dialog-title"
                  className="text-base font-bold text-ink-primary"
                >
                  Enroll Patient in Longitudinal Skin Tracking
                </h2>
                <p className="text-xs text-ink-secondary mt-0.5">
                  {PRIVACY_NOTICE} {CLINICAL_DISCLAIMER}
                </p>
              </div>
              <button
                type="button"
                onClick={() => createDialogRef.current?.close()}
                aria-label="Close enroll patient dialog"
                className="rounded-lg p-1.5 text-ink-muted hover:bg-[#edf4f9] hover:text-ink-primary"
              >
                <span aria-hidden="true" className="text-lg leading-none">
                  &times;
                </span>
              </button>
            </div>

            <div className="space-y-3.5 text-xs">
              <div>
                <label
                  htmlFor="new-patient-name"
                  className="block font-semibold text-ink-primary mb-1"
                >
                  Patient Full Name <span className="text-[#a63429]">*</span>
                </label>
                <input
                  id="new-patient-name"
                  type="text"
                  required
                  autoFocus
                  value={newPatientName}
                  onChange={(e) => setNewPatientName(e.target.value)}
                  placeholder="e.g., Jordan Vance"
                  className="clinical-input w-full px-3 py-2 text-sm"
                />
                <div className="field-error-msg">
                  Please enter the patient&apos;s full name.
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label
                    htmlFor="new-patient-ref"
                    className="block font-semibold text-ink-primary mb-1"
                  >
                    Clinic Chart Reference
                  </label>
                  <input
                    id="new-patient-ref"
                    type="text"
                    value={newPatientRef}
                    onChange={(e) => setNewPatientRef(e.target.value)}
                    placeholder="e.g., PT-1042"
                    className="clinical-input w-full px-3 py-2 text-sm font-mono"
                  />
                </div>

                <div>
                  <label
                    htmlFor="new-patient-dob"
                    className="block font-semibold text-ink-primary mb-1"
                  >
                    Date of Birth
                  </label>
                  <input
                    id="new-patient-dob"
                    type="date"
                    value={newPatientDob}
                    onChange={(e) => setNewPatientDob(e.target.value)}
                    className="clinical-input w-full px-3 py-2 text-sm font-mono"
                  />
                </div>
              </div>

              <div>
                <label
                  htmlFor="new-patient-notes"
                  className="block font-semibold text-ink-primary mb-1"
                >
                  Standing Clinical Context / Intake Notes
                </label>
                <textarea
                  id="new-patient-notes"
                  rows={2}
                  value={newPatientNotes}
                  onChange={(e) => setNewPatientNotes(e.target.value)}
                  placeholder="e.g., Fitzpatrick III, adult-onset cheek acne and barrier sensitivity."
                  className="clinical-input w-full px-3 py-2 text-sm"
                />
              </div>
            </div>

            {dialogError && (
              <div
                role="alert"
                className="rounded-lg border border-[#e3b5b0] bg-[#fbeae8] px-3 py-2 text-xs font-medium text-[#6e1f18]"
              >
                {dialogError}
              </div>
            )}

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-[#cbdce9]">
              <button
                type="button"
                onClick={() => createDialogRef.current?.close()}
                className="clinical-button clinical-button-secondary"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={creating}
                className="clinical-button clinical-button-primary"
              >
                {creating ? "Enrolling Patient..." : "Create Chart & Open"}
              </button>
            </div>
          </form>
        </dialog>

        {/* Confirm Patient Removal Modal Dialog */}
        <dialog
          ref={deleteDialogRef}
          aria-labelledby="delete-patient-dialog-title"
          aria-describedby="delete-patient-dialog-desc"
          className="clinical-card p-6 max-w-md w-full"
        >
          <div className="space-y-4">
            <div className="space-y-1.5">
              <span className="inline-flex items-center gap-1 rounded bg-rose-50 border border-rose-200 px-2 py-0.5 text-[11px] font-bold text-rose-900">
                Confirm Chart Deletion
              </span>
              <h2
                id="delete-patient-dialog-title"
                className="text-base font-bold text-slate-900"
              >
                Remove patient chart from clinic directory?
              </h2>
              <p
                id="delete-patient-dialog-desc"
                className="text-xs text-slate-600 leading-relaxed"
              >
                You are about to permanently remove{" "}
                <strong className="text-slate-900">
                  {pendingDeletePatient?.full_name}
                </strong>{" "}
                ({pendingDeletePatient?.external_ref || "Unassigned Ref"}) and
                all associated visits, skin concern scores, and prescriptions.
              </p>
            </div>

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-200">
              <button
                type="button"
                autoFocus
                disabled={deletingPatient}
                onClick={() => {
                  deleteDialogRef.current?.close();
                  setPendingDeletePatient(null);
                }}
                className="clinical-button clinical-button-secondary"
              >
                Keep Patient Chart
              </button>
              <button
                type="button"
                disabled={deletingPatient}
                onClick={() => void confirmDeletePatient()}
                className="rounded-lg bg-rose-700 hover:bg-rose-800 disabled:opacity-60 px-4 py-2 text-xs font-semibold text-white shadow-sm"
              >
                {deletingPatient ? "Removing..." : "Delete Patient Chart"}
              </button>
            </div>
          </div>
        </dialog>
      </main>
    </>
  );
}
