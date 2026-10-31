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
} from "@/components/ClinicalShell";

interface PatientListPayload {
  patients: PatientRecord[];
  total: number;
  disclaimer: string;
}

export default function PatientsDirectoryPage() {
  const router = useRouter();
  const dialogRef = useRef<HTMLDialogElement | null>(null);
  const deleteDialogRef = useRef<HTMLDialogElement | null>(null);

  const [patients, setPatients] = useState<PatientRecord[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [searchQuery, setSearchQuery] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // New patient modal form state
  const [fullName, setFullName] = useState("");
  const [externalRef, setExternalRef] = useState("");
  const [dob, setDob] = useState("");
  const [notes, setNotes] = useState("");
  const [creating, setCreating] = useState(false);
  const [dialogError, setDialogError] = useState<string | null>(null);

  // Destructive-action confirmation modal state for patient removal
  const [pendingDeletePatient, setPendingDeletePatient] =
    useState<PatientRecord | null>(null);
  const [deletingPatient, setDeletingPatient] = useState(false);

  const loadPatients = useCallback(
    async (query: string) => {
      if (!getStoredToken()) {
        router.replace("/login");
        return;
      }
      const trimmed = query.trim();
      setLoading(true);
      setError(null);
      try {
        const qs = trimmed ? `?q=${encodeURIComponent(trimmed)}` : "";
        const data = await apiFetch<PatientListPayload>(`/api/patients${qs}`);
        setPatients(data.patients);
        setTotalCount(data.total);
        setAppliedQuery(trimmed);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Failed to load the clinic patient directory."
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

  async function handleSearchSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    await loadPatients(searchQuery);
  }

  function handleResetSearch() {
    setSearchQuery("");
    void loadPatients("");
  }

  function openNewPatientDialog() {
    setDialogError(null);
    dialogRef.current?.showModal();
  }

  function closeNewPatientDialog() {
    setDialogError(null);
    dialogRef.current?.close();
  }

  function requestDeletePatient(pt: PatientRecord) {
    setPendingDeletePatient(pt);
    deleteDialogRef.current?.showModal();
  }

  async function confirmDeletePatient() {
    if (!pendingDeletePatient) return;
    setDeletingPatient(true);
    try {
      const token = getStoredToken();
      const res = await fetch(
        `${API_BASE_URL}/api/patients/${pendingDeletePatient.id}`,
        {
          method: "DELETE",
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        }
      );
      if (!res.ok) {
        throw new Error(`Could not delete patient (HTTP ${res.status})`);
      }
      deleteDialogRef.current?.close();
      setPendingDeletePatient(null);
      await loadPatients(appliedQuery);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to remove patient chart."
      );
      deleteDialogRef.current?.close();
    } finally {
      setDeletingPatient(false);
    }
  }

  async function handleCreatePatient(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!fullName.trim()) {
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
          full_name: fullName.trim(),
          external_ref: externalRef.trim() || null,
          dob: dob || null,
          consent_version: "v1-2026-10",
          notes: notes.trim() || null,
        }),
      });
      setFullName("");
      setExternalRef("");
      setDob("");
      setNotes("");
      closeNewPatientDialog();
      router.push(`/patients/${created.id}`);
    } catch (err) {
      setDialogError(
        err instanceof Error ? err.message : "Could not enroll patient."
      );
    } finally {
      setCreating(false);
    }
  }

  return (
    <>
      <ClinicianWorkspaceHeader
        rightActions={
          <button
            type="button"
            onClick={openNewPatientDialog}
            className="rounded-lg bg-sky-700 hover:bg-sky-800 text-white text-xs font-semibold px-3 py-1.5 sm:px-3.5 sm:py-2 shadow-sm transition"
          >
            + Enroll Patient
          </button>
        }
      />

      <main
        id="main-content"
        className="max-w-7xl w-full mx-auto px-4 sm:px-6 py-6 sm:py-8 space-y-6"
      >
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-xl sm:text-2xl font-bold text-slate-900 tracking-tight">
              Patient Longitudinal Directory
            </h1>
            <p className="text-xs text-slate-600 mt-1">
              Find an enrolled patient chart by name, chart reference, or
              standing clinical note.
            </p>
          </div>
          <div className="text-xs text-slate-600">
            {!loading && !error && (
              <span role="status" aria-live="polite">
                Showing{" "}
                <strong className="font-semibold text-slate-900">
                  {patients.length}
                </strong>{" "}
                {patients.length === 1 ? "patient chart" : "patient charts"}
                {appliedQuery ? ` matching "${appliedQuery}"` : ""}
              </span>
            )}
          </div>
        </div>

        <ClinicalInlineNotice />

        {/* Primary Search Bar */}
        <form
          role="search"
          aria-label="Find patient chart"
          onSubmit={handleSearchSubmit}
          className="bg-white border border-slate-200 rounded-xl p-4 shadow-clinical space-y-2"
        >
          <label
            htmlFor="patient-search"
            className="block text-xs font-semibold text-slate-800"
          >
            Find Patient Chart
          </label>
          <div className="flex flex-wrap items-center gap-2.5">
            <input
              type="search"
              id="patient-search"
              name="q"
              enterKeyHint="search"
              placeholder="Name, chart ref (e.g. PT-DEMO-001), or clinical note..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="flex-1 min-w-[220px] rounded-lg border border-slate-300 bg-white px-3.5 py-2 text-sm text-slate-900 shadow-sm transition"
            />
            <button
              type="submit"
              disabled={loading}
              className="rounded-lg bg-slate-900 hover:bg-slate-800 disabled:opacity-60 text-white text-sm font-semibold px-4 py-2 transition"
            >
              Search
            </button>
            {(searchQuery || appliedQuery) && (
              <button
                type="button"
                onClick={handleResetSearch}
                className="rounded-lg border border-slate-300 bg-white hover:bg-slate-50 px-3.5 py-2 text-xs font-semibold text-slate-700 transition"
              >
                Reset
              </button>
            )}
          </div>
        </form>

        {/* Explicit Error State with Retry Action */}
        {error && (
          <div
            role="alert"
            className="rounded-xl bg-rose-50 border border-rose-300 p-4 text-sm text-rose-900 flex flex-wrap items-center justify-between gap-3"
          >
            <div>
              <p className="font-semibold">Unable to load patient directory</p>
              <p className="text-xs text-rose-800 mt-0.5">{error}</p>
            </div>
            <button
              type="button"
              onClick={() => void loadPatients(appliedQuery)}
              className="rounded-lg border border-rose-300 bg-white hover:bg-rose-100 px-3 py-1.5 text-xs font-semibold text-rose-900 transition"
            >
              Retry
            </button>
          </div>
        )}

        {/* Directory Table / Responsive Stacked Cards */}
        <div
          tabIndex={0}
          role="region"
          aria-labelledby="patient-directory-caption"
          className="table-wrapper bg-white border border-slate-200 rounded-xl shadow-clinical"
        >
          <table
            className="responsive-data-table text-left text-sm"
            style={
              {
                "--label-2": '"Chart Ref"',
                "--label-3": '"Date of Birth"',
                "--label-4": '"Visits"',
                "--label-5": '"Latest Scan"',
                "--label-6": '"Consent"',
                "--label-7": '"Action"',
              } as React.CSSProperties
            }
          >
            <caption id="patient-directory-caption" className="sr-only">
              Clinic patients enrolled in longitudinal skin tracking (
              {totalCount} records)
            </caption>
            <thead className="bg-slate-100 text-xs font-semibold text-slate-700 border-b border-slate-200">
              <tr>
                <th scope="col" className="py-3 px-4 border-b border-slate-200">
                  Patient Identity &amp; Standing Notes
                </th>
                <th scope="col" className="py-3 px-4 border-b border-slate-200">
                  Chart Ref
                </th>
                <th scope="col" className="py-3 px-4 border-b border-slate-200">
                  Date of Birth
                </th>
                <th scope="col" className="py-3 px-4 border-b border-slate-200">
                  Completed Visits
                </th>
                <th scope="col" className="py-3 px-4 border-b border-slate-200">
                  Latest Scan Date
                </th>
                <th scope="col" className="py-3 px-4 border-b border-slate-200">
                  Consent
                </th>
                <th
                  scope="col"
                  className="py-3 px-4 border-b border-slate-200 text-right"
                >
                  Chart Action
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {loading ? (
                <tr>
                  <td
                    colSpan={7}
                    className="py-10 px-4 text-center text-sm text-slate-600"
                  >
                    Loading patient charts&hellip;
                  </td>
                </tr>
              ) : patients.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-10 px-4 text-center">
                    {appliedQuery ? (
                      <div className="max-w-md mx-auto space-y-2">
                        <p className="text-sm font-semibold text-slate-900">
                          No matching patient records found for &ldquo;
                          {appliedQuery}&rdquo;.
                        </p>
                        <p className="text-xs text-slate-600">
                          Check the spelling or chart reference, or clear the
                          search filter to view all enrolled patients.
                        </p>
                        <div className="pt-1 flex justify-center gap-2">
                          <button
                            type="button"
                            onClick={handleResetSearch}
                            className="rounded-lg border border-slate-300 bg-white hover:bg-slate-50 px-3.5 py-1.5 text-xs font-semibold text-slate-800"
                          >
                            Clear Search Filter
                          </button>
                          <button
                            type="button"
                            onClick={openNewPatientDialog}
                            className="rounded-lg bg-sky-700 hover:bg-sky-800 px-3.5 py-1.5 text-xs font-semibold text-white"
                          >
                            + Enroll New Patient
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="max-w-md mx-auto space-y-2">
                        <p className="text-sm font-semibold text-slate-900">
                          No patients enrolled in this clinic directory yet.
                        </p>
                        <p className="text-xs text-slate-600">
                          Enroll a patient to begin recording guided skin scans,
                          medications, and longitudinal trajectory reports.
                        </p>
                        <div className="pt-1">
                          <button
                            type="button"
                            onClick={openNewPatientDialog}
                            className="rounded-lg bg-sky-700 hover:bg-sky-800 px-4 py-2 text-xs font-semibold text-white"
                          >
                            + Enroll First Patient
                          </button>
                        </div>
                      </div>
                    )}
                  </td>
                </tr>
              ) : (
                patients.map((pt) => (
                  <tr key={pt.id} className="hover:bg-slate-50/80 transition">
                    <th
                      scope="row"
                      className="py-3.5 px-4 font-semibold text-slate-900 align-top"
                    >
                      <Link
                        href={`/patients/${pt.id}`}
                        className="text-sky-800 hover:text-sky-950 hover:underline font-bold text-sm"
                      >
                        {pt.full_name}
                      </Link>
                      {pt.notes ? (
                        <p className="text-xs font-normal text-slate-600 mt-0.5 line-clamp-2 max-w-md">
                          {pt.notes}
                        </p>
                      ) : (
                        <p className="text-xs font-normal text-slate-500 mt-0.5 italic">
                          No standing clinical notes
                        </p>
                      )}
                    </th>
                    <td className="py-3.5 px-4 font-mono text-xs text-slate-800 align-middle">
                      {pt.external_ref ? (
                        <span className="inline-block rounded bg-slate-100 border border-slate-200 px-2 py-0.5 font-semibold whitespace-nowrap">
                          {pt.external_ref}
                        </span>
                      ) : (
                        <span className="text-slate-500">Unassigned</span>
                      )}
                    </td>
                    <td className="py-3.5 px-4 text-xs text-slate-700 font-mono align-middle whitespace-nowrap">
                      {pt.dob || "Not recorded"}
                    </td>
                    <td className="py-3.5 px-4 align-middle">
                      <span
                        className={`inline-flex items-center gap-1 rounded border px-2.5 py-0.5 text-xs font-semibold whitespace-nowrap ${
                          pt.visit_count >= 2
                            ? "bg-emerald-50 text-emerald-900 border-emerald-200"
                            : pt.visit_count === 1
                            ? "bg-sky-50 text-sky-900 border-sky-200"
                            : "bg-slate-50 text-slate-600 border-slate-200"
                        }`}
                      >
                        <span>
                          {pt.visit_count}{" "}
                          {pt.visit_count === 1 ? "visit" : "visits"}
                        </span>
                      </span>
                    </td>
                    <td className="py-3.5 px-4 text-xs text-slate-700 font-mono align-middle whitespace-nowrap">
                      {pt.latest_visit_date || (
                        <span className="font-sans text-slate-500 italic">
                          No scans yet
                        </span>
                      )}
                    </td>
                    <td className="py-3.5 px-4 text-xs text-slate-700 align-middle">
                      <span className="inline-flex items-center gap-1 rounded bg-slate-100 px-2 py-0.5 font-mono text-[11px] text-slate-700 whitespace-nowrap">
                        <span aria-hidden="true" className="text-emerald-700">
                          ✓
                        </span>
                        {pt.consent_version}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 text-right align-middle">
                      <div className="inline-flex items-center justify-end gap-2">
                        <Link
                          href={`/patients/${pt.id}`}
                          className="inline-flex items-center gap-1 rounded-lg bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold px-3 py-1.5 shadow-sm transition whitespace-nowrap"
                        >
                          <span>Open Chart</span>
                          <span aria-hidden="true">&rarr;</span>
                        </Link>
                        <button
                          type="button"
                          onClick={() => requestDeletePatient(pt)}
                          className="inline-flex items-center rounded-lg border border-rose-200 bg-white hover:bg-rose-50 text-rose-700 text-xs font-semibold px-2.5 py-1.5 transition"
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

        {/* Native <dialog> modal per modern-web-guidance 'dialog' */}
        <dialog
          ref={dialogRef}
          aria-labelledby="new-patient-dialog-title"
          className="w-full max-w-lg rounded-xl border border-slate-300 bg-white p-6 shadow-xl"
        >
          <div className="flex items-start justify-between gap-3 border-b border-slate-200 pb-3">
            <div>
              <h2
                id="new-patient-dialog-title"
                className="text-lg font-bold text-slate-900"
              >
                Enroll New Patient
              </h2>
              <p className="mt-0.5 text-xs text-slate-600">
                {PRIVACY_NOTICE} {CLINICAL_DISCLAIMER}
              </p>
            </div>
            <button
              type="button"
              onClick={closeNewPatientDialog}
              aria-label="Close enroll patient dialog"
              className="rounded-lg p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-800"
            >
              <span aria-hidden="true" className="text-lg leading-none">
                &times;
              </span>
            </button>
          </div>

          <form onSubmit={handleCreatePatient} className="mt-4 space-y-4">
            <div>
              <label
                htmlFor="new-patient-name"
                className="block text-xs font-semibold text-slate-800 mb-1"
              >
                Patient Full Name <span className="text-rose-700">*</span>
              </label>
              <input
                type="text"
                id="new-patient-name"
                name="full_name"
                autoComplete="name"
                required
                autoFocus
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="e.g., Jordan Patel"
                className="clinical-input w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
              />
              <div className="field-error-msg">
                Please enter the patient&apos;s full name.
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label
                  htmlFor="new-patient-ref"
                  className="block text-xs font-semibold text-slate-800 mb-1"
                >
                  Clinic Chart Reference
                </label>
                <input
                  type="text"
                  id="new-patient-ref"
                  name="external_ref"
                  value={externalRef}
                  onChange={(e) => setExternalRef(e.target.value)}
                  placeholder="e.g., PT-1042"
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 font-mono"
                />
              </div>

              <div>
                <label
                  htmlFor="new-patient-dob"
                  className="block text-xs font-semibold text-slate-800 mb-1"
                >
                  Date of Birth
                </label>
                <input
                  type="date"
                  id="new-patient-dob"
                  name="dob"
                  value={dob}
                  onChange={(e) => setDob(e.target.value)}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
                />
              </div>
            </div>

            <div>
              <label
                htmlFor="new-patient-notes"
                className="block text-xs font-semibold text-slate-800 mb-1"
              >
                Standing Clinical Context / Notes
              </label>
              <textarea
                id="new-patient-notes"
                name="notes"
                rows={2}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Fitzpatrick skin type, known sensitivities, or baseline clinical history..."
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
              />
            </div>

            {dialogError && (
              <div
                role="alert"
                className="rounded-lg bg-rose-50 border border-rose-300 px-3 py-2 text-xs font-medium text-rose-900"
              >
                {dialogError}
              </div>
            )}

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-200">
              <button
                type="button"
                onClick={closeNewPatientDialog}
                className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={creating}
                className="rounded-lg bg-sky-700 hover:bg-sky-800 disabled:opacity-60 px-4 py-2 text-xs font-semibold text-white shadow-sm"
              >
                {creating ? "Creating Chart..." : "Create Patient Chart"}
              </button>
            </div>
          </form>
        </dialog>

        {/* Destructive Action Confirmation Modal for Removing a Patient Chart */}
        <dialog
          ref={deleteDialogRef}
          aria-labelledby="delete-patient-dialog-title"
          aria-describedby="delete-patient-dialog-desc"
          className="w-full max-w-md rounded-xl border border-slate-300 bg-white p-6 shadow-xl"
        >
          <div className="space-y-4">
            <div className="space-y-1.5">
              <span className="inline-flex items-center gap-1 rounded bg-rose-50 border border-rose-200 px-2 py-0.5 text-[11px] font-bold text-rose-900">
                Confirm Chart Removal
              </span>
              <h2
                id="delete-patient-dialog-title"
                className="text-base font-bold text-slate-900"
              >
                Remove patient chart and stored visit scans?
              </h2>
              <p
                id="delete-patient-dialog-desc"
                className="text-xs text-slate-600 leading-relaxed"
              >
                You are about to permanently remove{" "}
                <strong className="text-slate-900">
                  {pendingDeletePatient?.full_name || "this patient"}
                </strong>{" "}
                ({pendingDeletePatient?.external_ref || "Unassigned"}) and all
                associated visit scans, scores, and medications.
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
                className="rounded-lg border border-slate-300 bg-white hover:bg-slate-50 px-4 py-2 text-xs font-semibold text-slate-800"
              >
                Keep Chart
              </button>
              <button
                type="button"
                disabled={deletingPatient}
                onClick={() => void confirmDeletePatient()}
                className="rounded-lg bg-rose-700 hover:bg-rose-800 disabled:opacity-60 px-4 py-2 text-xs font-semibold text-white shadow-sm"
              >
                {deletingPatient ? "Removing..." : "Remove Patient Chart"}
              </button>
            </div>
          </div>
        </dialog>
      </main>
    </>
  );
}
