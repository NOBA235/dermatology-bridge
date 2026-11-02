"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import {
  apiFetch,
  CLINICAL_DISCLAIMER,
  ClinicianProfile,
  setStoredSession,
} from "@/lib/api";
import { DermBridgeCrestIcon } from "@/components/ClinicalShell";

interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  clinician: ClinicianProfile;
  disclaimer: string;
}

export default function ClinicianLoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("dr.chen@bridgederm.local");
  const [password, setPassword] = useState("BridgeDerm2026!");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      const data = await apiFetch<LoginResponse>("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim(), password }),
      });
      setStoredSession(data.access_token, data.clinician);
      router.push("/patients");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Authentication failed. Please verify your clinician credentials."
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex flex-col">
      {/* DermNet Two-Tier Masthead Banner on Login */}
      <header className="shadow-clinical-md">
        <div className="bg-[#006599] text-white">
          <div className="mx-auto max-w-7xl px-4 sm:px-6 py-3.5 flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3">
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
            </div>

            <div className="flex items-center gap-3">
              <span className="hidden sm:inline text-xs font-medium text-sky-100">
                Are you a healthcare professional?
              </span>
              <span className="inline-flex items-center gap-1.5 rounded-full bg-[#0b2c44] text-white px-4 py-1.5 text-xs font-bold uppercase tracking-wider border border-white/15">
                <span>DERMBRIDGE PRO PORTAL</span>
                <span aria-hidden="true">&rarr;</span>
              </span>
            </div>
          </div>
        </div>
        <div className="bg-[#127eb8] text-white border-t border-white/15">
          <div className="mx-auto max-w-7xl px-4 sm:px-6 py-2 flex flex-wrap items-center justify-between gap-2 text-xs font-semibold">
            <div className="flex flex-wrap items-center divide-x divide-white/30">
              <span className="pr-3.5">Bridge Dermatology Clinic</span>
              <span className="px-3.5">12 YouCam S2S Skin Topics</span>
              <span className="px-3.5">Longitudinal Case Tracking</span>
              <span className="pl-3.5">Rx Cross-Reference &amp; FHIR R4</span>
            </div>
            <span className="text-[11px] text-sky-50">
              {CLINICAL_DISCLAIMER}
            </span>
          </div>
        </div>
      </header>

      <main
        id="main-content"
        className="flex-1 flex flex-col items-center justify-center px-4 py-10 sm:py-14"
      >
        <div className="w-full max-w-md space-y-5">
          <section
            aria-labelledby="login-heading"
            className="clinical-card p-6 sm:p-8 space-y-6"
          >
            {/* Brand Identity Header */}
            <div className="space-y-2 border-b border-[#cbdce9] pb-5">
              <div className="flex items-center gap-3">
                <div
                  aria-hidden="true"
                  className="flex h-11 w-11 items-center justify-center rounded-xl bg-[#006599] text-white shadow-sm"
                >
                  <DermBridgeCrestIcon className="h-7 w-7 text-white" />
                </div>
                <div>
                  <span className="block text-[11px] font-bold uppercase tracking-wider text-[#006599]">
                    Bridge Dermatology Clinic
                  </span>
                  <h1
                    id="login-heading"
                    className="text-xl font-extrabold text-ink-primary tracking-tight"
                  >
                    Clinician Workspace Sign In
                  </h1>
                </div>
              </div>
              <p className="text-xs text-ink-secondary leading-relaxed pt-1">
                Sign in to review longitudinal skin concern trajectories,
                prescription co-movement, and consultation reports.
              </p>
            </div>

            {/* Hedged Decision Support Framing */}
            <div
              role="note"
              aria-label="Clinical decision support notice"
              className="clinical-notice px-3.5 py-2.5 text-xs"
            >
              <strong className="font-bold text-[#006599]">
                {CLINICAL_DISCLAIMER}
              </strong>{" "}
              Longitudinal measurements and generated hypotheses assist clinical
              review during patient consultations.
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label
                  htmlFor="username"
                  className="block text-xs font-semibold text-ink-primary mb-1.5"
                >
                  Clinician Email Address
                </label>
                <input
                  id="username"
                  name="username"
                  type="email"
                  autoComplete="username"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="clinician@bridgederm.local"
                  className="clinical-input w-full px-3.5 py-2.5 text-sm"
                />
                <div className="field-error-msg">
                  Please enter a valid clinician email address.
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label
                    htmlFor="current-password"
                    className="block text-xs font-semibold text-ink-primary"
                  >
                    Password
                  </label>
                  <button
                    type="button"
                    onClick={() => setShowPassword((prev) => !prev)}
                    aria-controls="current-password"
                    aria-pressed={showPassword}
                    className="text-xs font-semibold text-[#006599] hover:text-[#004e78] hover:underline"
                  >
                    {showPassword ? "Hide password" : "Show password"}
                  </button>
                </div>
                <input
                  id="current-password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="clinical-input w-full px-3.5 py-2.5 text-sm"
                />
                <div className="field-error-msg">
                  Password is required to sign in.
                </div>
              </div>

              {error && (
                <div
                  role="alert"
                  className="rounded-lg border border-[#e3b5b0] bg-[#fbeae8] px-3.5 py-2.5 text-xs font-medium text-[#6e1f18] flex items-start gap-2"
                >
                  <span aria-hidden="true" className="font-bold">
                    !
                  </span>
                  <span>{error}</span>
                </div>
              )}

              <button
                type="submit"
                disabled={submitting}
                className="clinical-button clinical-button-primary w-full py-2.5 text-sm"
              >
                {submitting
                  ? "Signing in to clinic workspace..."
                  : "Sign In to Patient Directory \u2192"}
              </button>
            </form>

            {/* Demo Clinic Credentials Helper */}
            <div className="clinical-subtle-panel p-3.5 text-xs text-ink-secondary space-y-1">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-ink-primary">
                  Seeded Demo Clinician Account
                </span>
                <button
                  type="button"
                  onClick={() => {
                    setEmail("dr.chen@bridgederm.local");
                    setPassword("BridgeDerm2026!");
                    setError(null);
                  }}
                  className="text-[#006599] hover:text-[#004e78] font-semibold hover:underline"
                >
                  Restore defaults
                </button>
              </div>
              <div className="font-mono text-[11px] text-ink-secondary">
                dr.chen@bridgederm.local &bull; BridgeDerm2026!
              </div>
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
