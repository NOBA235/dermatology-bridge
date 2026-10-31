"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  clearStoredSession,
  CLINICAL_DISCLAIMER,
  ClinicianProfile,
  getStoredClinician,
} from "@/lib/api";

export function ClinicianWorkspaceHeader({
  currentPatientName,
  currentPatientRef,
  rightActions,
}: {
  currentPatientName?: string | null;
  currentPatientRef?: string | null;
  rightActions?: React.ReactNode;
}) {
  const router = useRouter();
  const [clinician, setClinician] = useState<ClinicianProfile | null>(null);

  useEffect(() => {
    setClinician(getStoredClinician());
  }, []);

  function handleSignOut() {
    clearStoredSession();
    router.push("/login");
  }

  return (
    <header className="bg-white border-b border-slate-200 sticky top-0 z-20">
      <div className="max-w-7xl w-full mx-auto px-4 sm:px-6 py-2.5 min-h-[3.5rem] flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
        <div className="flex items-center gap-2.5 min-w-0">
          <Link
            href="/patients"
            className="flex items-center gap-2 text-slate-900 hover:text-sky-800 transition shrink-0"
          >
            <span
              aria-hidden="true"
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-slate-900 text-white font-bold text-xs tracking-tight shrink-0"
            >
              DB
            </span>
            <div className="leading-tight">
              <span className="font-bold text-sm tracking-tight block whitespace-nowrap">
                Dermatology Bridge
              </span>
              <span className="text-[11px] text-slate-600 hidden sm:block">
                Bridge Dermatology Clinic &bull; Longitudinal Decision Support
              </span>
            </div>
          </Link>

          <nav
            aria-label="Breadcrumb"
            className="hidden md:flex items-center gap-2 text-xs text-slate-600 pl-3 border-l border-slate-200 truncate"
          >
            <Link
              href="/patients"
              className={`font-medium hover:text-sky-800 hover:underline ${
                !currentPatientName
                  ? "text-slate-900 font-semibold"
                  : "text-slate-600"
              }`}
              aria-current={!currentPatientName ? "page" : undefined}
            >
              Patient Directory
            </Link>
            {currentPatientName && (
              <>
                <span aria-hidden="true" className="text-slate-400">
                  /
                </span>
                <span
                  className="font-semibold text-slate-900 truncate max-w-[240px]"
                  aria-current="page"
                >
                  {currentPatientName}
                  {currentPatientRef ? ` (${currentPatientRef})` : ""}
                </span>
              </>
            )}
          </nav>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {rightActions}
          {clinician && (
            <div className="hidden lg:flex flex-col items-end text-right leading-tight pr-1">
              <span className="text-xs font-semibold text-slate-800">
                {clinician.full_name || clinician.email}
              </span>
              <span className="text-[11px] text-slate-500">
                {clinician.email}
              </span>
            </div>
          )}
          <button
            type="button"
            onClick={handleSignOut}
            className="rounded-lg border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 text-xs font-semibold px-2.5 sm:px-3 py-1.5 transition"
          >
            Sign Out
          </button>
        </div>
      </div>
    </header>
  );
}

export function ClinicalInlineNotice({
  children,
}: {
  children?: React.ReactNode;
}) {
  return (
    <div
      role="note"
      aria-label="Clinical decision support notice"
      className="rounded-lg bg-slate-100/90 border border-slate-200/90 px-3.5 py-2.5 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-700"
    >
      <div className="flex items-center gap-2">
        <span
          aria-hidden="true"
          className="inline-block h-2 w-2 rounded-full bg-sky-700 shrink-0"
        />
        <span>
          <strong className="font-semibold text-slate-900">
            {CLINICAL_DISCLAIMER}
          </strong>{" "}
          {children ||
            "Longitudinal scores, deltas, and generated hypotheses support clinician review and do not establish a medical diagnosis."}
        </span>
      </div>
    </div>
  );
}
