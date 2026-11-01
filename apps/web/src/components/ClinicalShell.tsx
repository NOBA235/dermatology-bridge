"use client";

import React, { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  clearStoredSession,
  CLINICAL_DISCLAIMER,
  ClinicianProfile,
  getStoredClinician,
} from "@/lib/api";

interface ClinicianWorkspaceHeaderProps {
  currentPatientName?: string | null;
  currentPatientRef?: string | null;
  rightActions?: React.ReactNode;
  searchValue?: string;
  onSearchChange?: (value: string) => void;
  onSearchSubmit?: (value: string) => void;
}

/**
 * Iconic DermNet-inspired layered globe & epidermal crest SVG emblem.
 */
export function DermBridgeCrestIcon({
  className = "h-10 w-10",
}: {
  className?: string;
}) {
  return (
    <svg
      viewBox="0 0 48 48"
      fill="none"
      aria-hidden="true"
      className={className}
    >
      <circle
        cx="24"
        cy="24"
        r="21"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeOpacity="0.9"
      />
      {/* Epidermal & dermal horizontal wave bands */}
      <path
        d="M7 15.5C13 13.5 18.5 17 24 17C29.5 17 35 13.5 41 15.5"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
      <path
        d="M5.5 22C12 19.8 18 23.2 24 23.2C30 23.2 36 19.8 42.5 22"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
      <path
        d="M6.5 28.5C12.5 26.5 18.5 29.8 24 29.8C29.5 29.8 35.5 26.5 41.5 28.5"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
      <path
        d="M10 35C15 33.4 19.5 36 24 36C28.5 36 33 33.4 38 35"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
      />
      {/* Central clinical axis */}
      <circle cx="24" cy="10.5" r="2.3" fill="currentColor" />
      <path
        d="M24 13.5V39.5"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
      />
    </svg>
  );
}

/**
 * Authoritative Two-Tier DermNet-Inspired Clinical Masthead.
 * Top tier: #006599 Cerulean Medical Blue with Brand Crest, Center White Search Bar (Ctrl+K), and Navy CTA Pill.
 * Bottom tier: #127eb8 Sub-Navigation Bar with pipe-separated clinical links and active chart context.
 */
export function ClinicianWorkspaceHeader({
  currentPatientName,
  currentPatientRef,
  rightActions,
  searchValue,
  onSearchChange,
  onSearchSubmit,
}: ClinicianWorkspaceHeaderProps) {
  const router = useRouter();
  const pathname = usePathname();
  const [clinician, setClinician] = useState<ClinicianProfile | null>(null);
  const [internalSearch, setInternalSearch] = useState(searchValue ?? "");
  const searchInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setClinician(getStoredClinician());
  }, []);

  useEffect(() => {
    if (searchValue !== undefined) {
      setInternalSearch(searchValue);
    }
  }, [searchValue]);

  // Global Ctrl+K / Cmd+K shortcut to focus the masthead search bar
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        searchInputRef.current?.focus();
        searchInputRef.current?.select();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  function handleSignOut() {
    clearStoredSession();
    router.replace("/login");
  }

  function handleMastheadSearchSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = internalSearch.trim();
    if (onSearchSubmit) {
      onSearchSubmit(trimmed);
      return;
    }
    router.push("/patients");
  }

  return (
    <header className="sticky top-0 z-30 shadow-clinical-md">
      {/* TIER 1: Primary Cerulean Medical Masthead (#006599) */}
      <div className="bg-[#006599] text-white">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 py-3 flex flex-wrap items-center justify-between gap-4">
          {/* Left: DermBridge® Crest + Title */}
          <Link
            href="/patients"
            className="flex items-center gap-3 text-white hover:opacity-95 transition shrink-0"
          >
            <DermBridgeCrestIcon className="h-10 w-10 text-white shrink-0" />
            <div>
              <div className="flex items-baseline gap-1">
                <span className="text-xl sm:text-2xl font-extrabold tracking-tight leading-none">
                  DermBridge
                </span>
                <sup className="text-[11px] font-bold opacity-90">&reg;</sup>
              </div>
              <span className="block text-[11px] font-medium text-sky-100 tracking-wide mt-0.5">
                All about the skin &bull; Longitudinal AI
              </span>
            </div>
          </Link>

          {/* Center: Signature DermNet White Search Bar with Ctrl+K badge */}
          <form
            role="search"
            aria-label="Quick clinical directory search"
            onSubmit={handleMastheadSearchSubmit}
            className="flex-1 min-w-[240px] max-w-xl mx-auto"
          >
            <div className="flex items-center bg-white rounded-md px-3 py-1.5 shadow-sm border border-white/20 focus-within:ring-2 focus-within:ring-sky-200">
              <svg
                viewBox="0 0 20 20"
                fill="none"
                aria-hidden="true"
                className="h-4 w-4 text-slate-500 shrink-0 mr-2.5"
              >
                <circle
                  cx="9"
                  cy="9"
                  r="6"
                  stroke="currentColor"
                  strokeWidth="2"
                />
                <path
                  d="M13.5 13.5L17 17"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                />
              </svg>
              <label htmlFor="masthead-quick-search" className="sr-only">
                Search DermBridge patient charts, skin concerns, or Rx
              </label>
              <input
                ref={searchInputRef}
                id="masthead-quick-search"
                type="search"
                value={internalSearch}
                onChange={(e) => {
                  const val = e.target.value;
                  setInternalSearch(val);
                  onSearchChange?.(val);
                }}
                placeholder="Search DermBridge charts, 12 skin concerns, or Rx..."
                className="w-full bg-transparent text-xs sm:text-sm text-slate-900 placeholder:text-slate-500 focus:outline-none"
              />
              <div
                aria-hidden="true"
                className="hidden sm:inline-flex items-center gap-1 ml-2 shrink-0"
              >
                <kbd className="rounded border border-slate-300 bg-slate-50 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-slate-700 shadow-sm">
                  Ctrl
                </kbd>
                <kbd className="rounded border border-slate-300 bg-slate-50 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-slate-700 shadow-sm">
                  K
                </kbd>
              </div>
            </div>
          </form>

          {/* Right: Healthcare Professional Portal Action Pill + Clinician Session */}
          <div className="flex flex-wrap items-center gap-3 shrink-0">
            <div className="hidden xl:flex flex-col items-end text-right">
              <span className="text-[11px] font-medium text-sky-100">
                Healthcare Professional Workspace
              </span>
              {clinician && (
                <span className="text-xs font-bold text-white">
                  {clinician.full_name || "Attending Dermatologist"}{" "}
                  <span className="font-normal text-sky-100">
                    ({clinician.email})
                  </span>
                </span>
              )}
            </div>

            {rightActions ? (
              <div className="flex items-center gap-2">{rightActions}</div>
            ) : (
              <Link
                href="/patients"
                className="inline-flex items-center gap-2 rounded-full bg-[#0b2c44] hover:bg-[#071f31] text-white px-4 py-2 text-xs font-bold uppercase tracking-wider shadow-sm border border-white/15 transition"
              >
                <span>GO TO DERMBRIDGE PRO</span>
                <span aria-hidden="true">&rarr;</span>
              </Link>
            )}

            <button
              type="button"
              onClick={handleSignOut}
              className="rounded-full bg-[#0b2c44]/80 hover:bg-[#071f31] text-white border border-white/20 px-3.5 py-1.5 text-xs font-semibold transition"
            >
              Sign Out
            </button>
          </div>
        </div>
      </div>

      {/* TIER 2: Secondary Clinical Navigation Bar (#127eb8) with Vertical Pipe Dividers */}
      <nav
        aria-label="Clinical navigation"
        className="bg-[#127eb8] text-white border-t border-white/15"
      >
        <div className="mx-auto max-w-7xl px-4 sm:px-6 py-2 flex flex-wrap items-center justify-between gap-2 text-xs font-semibold">
          <div className="flex flex-wrap items-center divide-x divide-white/30">
            <Link
              href="/patients"
              aria-current={pathname === "/patients" ? "page" : undefined}
              className="pr-3.5 py-0.5 text-white hover:text-sky-100 hover:underline transition"
            >
              Home / Directory
            </Link>
            <a
              href={
                pathname === "/patients"
                  ? "#clinical-atlas"
                  : "#snapshot-matrix-heading"
              }
              className="px-3.5 py-0.5 text-white hover:text-sky-100 hover:underline transition"
            >
              Skin Topics A&ndash;Z (12)
            </a>
            <a
              href={
                pathname === "/patients"
                  ? "#patient-directory-section"
                  : "#priority-concerns-heading"
              }
              className="px-3.5 py-0.5 text-white hover:text-sky-100 hover:underline transition"
            >
              Longitudinal Cases
            </a>
            <a
              href={
                pathname === "/patients"
                  ? "#clinical-atlas"
                  : "#prescription-correlations-heading"
              }
              className="px-3.5 py-0.5 text-white hover:text-sky-100 hover:underline transition"
            >
              Rx Cross-Reference
            </a>
            <a
              href={
                pathname === "/patients"
                  ? "#patient-directory-section"
                  : "#visits-timeline-heading"
              }
              className="pl-3.5 py-0.5 text-white hover:text-sky-100 hover:underline transition"
            >
              YouCam S2S Skin Checker
            </a>
          </div>

          {/* Right side of Sub-Nav: Active Patient Breadcrumb or Clinical Disclaimer */}
          <div className="flex items-center gap-2 text-[11px] text-sky-50">
            {currentPatientName ? (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-[#0b2c44]/75 border border-white/20 px-3 py-0.5 text-white font-semibold">
                <span>Active Chart: {currentPatientName}</span>
                {currentPatientRef && (
                  <span className="font-mono text-sky-200">
                    ({currentPatientRef})
                  </span>
                )}
              </span>
            ) : (
              <span className="hidden md:inline font-medium">
                {CLINICAL_DISCLAIMER}
              </span>
            )}
          </div>
        </div>
      </nav>
    </header>
  );
}

/**
 * Non-sticky inline clinical notice for hedged decision-support framing.
 */
export function ClinicalInlineNotice({
  children,
}: {
  children?: React.ReactNode;
}) {
  return (
    <div
      role="note"
      aria-label="Clinical decision support notice"
      className="clinical-notice px-4 py-3 text-xs sm:text-sm"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-ink-secondary">
          <strong className="font-bold text-[#006599]">
            {CLINICAL_DISCLAIMER}
          </strong>{" "}
          {children ||
            "Longitudinal scores, deltas, and generated hypotheses support clinician review and do not establish a medical diagnosis."}
        </p>
      </div>
    </div>
  );
}
