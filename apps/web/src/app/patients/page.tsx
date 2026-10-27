"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  apiFetch,
  clearStoredSession,
  CLINICAL_DISCLAIMER,
  getStoredToken,
  PatientRecord,
  PRIVACY_NOTICE,
} from "@/lib/api";

interface PatientListPayload {
  patients: PatientRecord[];
  total: number;
  disclaimer: string;
}

export default function PatientsDirectoryPage() {
  const router = useRouter();
  const dialogRef = useRef<HTMLDialogElement | null>(null);

  const [patients, setPatients] = useState<PatientRecord[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // New patient modal form state
  const [fullName, setFullName] = useState("");
  const [externalRef, setExternalRef] = useState("");
  const [dob, setDob] = useState("");
  const [notes, setNotes] = useState("");
  const [creating, setCreating] = useState(false);

  const loadPatients = useCallback(
    async (query: string) => {
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
          err instanceof Error ? err.message : "Failed to load patient directory."
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

  function openNewPatientDialog() {
    dialogRef.current?.showModal();
  }

  function closeNewPatientDialog() {
    dialogRef.current?.close();
  }

  async function handleCreatePatient(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!fullName.trim()) return;
    setCreating(true);
    setError(null);
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
      setError(err instanceof Error ? err.message : "Could not create patient.");
    } finally {
      setCreating(false);
    }
  }

  return (
    <main className="max-w-7xl w-full mx-auto px-4 sm:px-6 py-8 space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">
            Patient Longitudinal Directory
          </h1>
          <p className="text-xs text-slate-600 mt-1">
            Bridge Dermatology Clinic &bull;{" "}
            <span className="font-semibold text-slate-800">
              {CLINICAL_DISCLAIMER}
            </span>
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={openNewPatientDialog}
            className="rounded-lg bg-sky-700 hover:bg-sky-800 text-white text-sm font-semibold px-4 py-2 transition"
          >
            + New Patient
          </button>
          <button
            type="button"
            onClick={() => {
              clearStoredSession();
              router.push("/login");
            }}
            className="rounded-lg border border-slate-300 bg-white hover:bg-slate-100 text-slate-700 text-sm font-medium px-3 py-2 transition"
          >
            Sign Out
          </button>
        </div>
      </header>

      <form
        onSubmit={handleSearchSubmit}
        className="flex flex-wrap items-center gap-3 bg-white border border-slate-200 rounded-xl p-4 shadow-sm"
      >
        <label htmlFor="patient-search" className="sr-only">
          Search patients by name or chart reference
        </label>
        <input
          type="search"
          id="patient-search"
          name="q"
          enterKeyHint="search"
          placeholder="Search patients by full name, chart ref (e.g. PT-DEMO-001), or clinical notes..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="flex-1 min-w-[240px] rounded-lg border border-slate-300 px-3.5 py-2 text-sm text-slate-900 focus:border-sky-600 focus:outline-none"
        />
        <button
          type="submit"
          className="rounded-lg bg-slate-900 hover:bg-slate-800 text-white text-sm font-semibold px-4 py-2"
        >
          Search
        </button>
        {searchQuery && (
          <button
            type="button"
            onClick={() => {
              setSearchQuery("");
              void loadPatients("");
            }}
            className="rounded-lg border border-slate-300 px-3 py-2 text-xs text-slate-700 hover:bg-slate-100"
          >
            Reset
          </button>
        )}
      </form>

      {error && (
        <div
          role="alert"
          className="rounded-lg bg-rose-50 border border-rose-200 p-4 text-sm text-rose-800"
        >
          {error}
        </div>
      )}

      <div
        tabIndex={0}
        role="region"
        aria-labelledby="patient-directory-caption"
        className="table-wrapper bg-white border border-slate-200 rounded-xl shadow-sm"
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
            Clinic patients enrolled in longitudinal skin tracking
          </caption>
          <thead className="bg-slate-100 text-xs uppercase text-slate-600">
            <tr>
              <th className="py-3 px-4 border-b border-slate-200">
                Patient Name
              </th>
              <th className="py-3 px-4 border-b border-slate-200">Chart Ref</th>
              <th className="py-3 px-4 border-b border-slate-200">DOB</th>
              <th className="py-3 px-4 border-b border-slate-200">
                Completed Visits
              </th>
              <th className="py-3 px-4 border-b border-slate-200">
                Latest Scan
              </th>
              <th className="py-3 px-4 border-b border-slate-200">Consent</th>
              <th className="py-3 px-4 border-b border-slate-200">Workspace</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200">
            {loading ? (
              <tr>
                <td colSpan={7} className="py-8 px-4 text-center text-slate-500">
                  Loading patient charts...
                </td>
              </tr>
            ) : patients.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-8 px-4 text-center text-slate-500">
                  No matching patient records found.
                </td>
              </tr>
            ) : (
              patients.map((pt) => (
                <tr key={pt.id} className="hover:bg-slate-50">
                  <th className="py-3.5 px-4 font-semibold text-slate-900">
                    <Link
                      href={`/patients/${pt.id}`}
                      className="text-sky-700 hover:underline"
                    >
                      {pt.full_name}
                    </Link>
                    {pt.notes && (
                      <p className="text-xs font-normal text-slate-500 mt-0.5 line-clamp-1">
                        {pt.notes}
                      </p>
                    )}
                  </th>
                  <td className="py-3.5 px-4 font-mono text-xs text-slate-700">
                    {pt.external_ref || "—"}
                  </td>
                  <td className="py-3.5 px-4 text-slate-700">
                    {pt.dob || "—"}
                  </td>
                  <td className="py-3.5 px-4">
                    <span className="inline-flex items-center rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-semibold text-slate-800">
                      {pt.visit_count} visits
                    </span>
                  </td>
                  <td className="py-3.5 px-4 text-slate-700">
                    {pt.latest_visit_date || "No scans yet"}
                  </td>
                  <td className="py-3.5 px-4 text-xs text-slate-600">
                    {pt.consent_version}
                  </td>
                  <td className="py-3.5 px-4">
                    <Link
                      href={`/patients/${pt.id}`}
                      className="inline-flex items-center rounded-lg bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold px-3 py-1.5"
                    >
                      Open Chart &rarr;
                    </Link>
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
        className="w-full max-w-lg rounded-xl border border-slate-200 bg-white p-6 shadow-xl"
      >
        <h2
          id="new-patient-dialog-title"
          className="text-lg font-bold text-slate-900"
        >
          Enroll New Patient
        </h2>
        <p className="mt-1 text-xs text-slate-600">
          {PRIVACY_NOTICE} {CLINICAL_DISCLAIMER}
        </p>

        <form onSubmit={handleCreatePatient} className="mt-4 space-y-4">
          <div>
            <label
              htmlFor="new-patient-name"
              className="block text-xs font-semibold uppercase text-slate-700 mb-1"
            >
              Full Name *
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
              placeholder="e.g. Jordan Patel"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label
                htmlFor="new-patient-ref"
                className="block text-xs font-semibold uppercase text-slate-700 mb-1"
              >
                Clinic Chart Ref
              </label>
              <input
                type="text"
                id="new-patient-ref"
                name="external_ref"
                value={externalRef}
                onChange={(e) => setExternalRef(e.target.value)}
                placeholder="e.g. PT-1042"
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
            </div>

            <div>
              <label
                htmlFor="new-patient-dob"
                className="block text-xs font-semibold uppercase text-slate-700 mb-1"
              >
                Date of Birth
              </label>
              <input
                type="date"
                id="new-patient-dob"
                name="dob"
                value={dob}
                onChange={(e) => setDob(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
            </div>
          </div>

          <div>
            <label
              htmlFor="new-patient-notes"
              className="block text-xs font-semibold uppercase text-slate-700 mb-1"
            >
              Standing Clinical Notes
            </label>
            <textarea
              id="new-patient-notes"
              name="notes"
              rows={2}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Baseline skin type, sensitivities, or standing history..."
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </div>

          <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-200">
            <button
              type="button"
              onClick={closeNewPatientDialog}
              className="rounded-lg border border-slate-300 px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={creating}
              className="rounded-lg bg-sky-700 hover:bg-sky-800 disabled:opacity-60 px-4 py-2 text-xs font-semibold text-white"
            >
              {creating ? "Creating..." : "Create Patient Chart"}
            </button>
          </div>
        </form>
      </dialog>
    </main>
  );
}

