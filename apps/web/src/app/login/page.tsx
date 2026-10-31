"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import {
  API_BASE_URL,
  CLINICAL_DISCLAIMER,
  ClinicianProfile,
  PRIVACY_NOTICE,
  setStoredSession,
} from "@/lib/api";

interface LoginResponsePayload {
  access_token: string;
  token_type: string;
  clinician: ClinicianProfile;
}

const DEMO_EMAIL = "dr.chen@bridgederm.local";
const DEMO_PASS = "clinician-demo-pass";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState(DEMO_EMAIL);
  const [password, setPassword] = useState(DEMO_PASS);
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const response = await fetch(`${API_BASE_URL}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim(), password }),
      });
      if (!response.ok) {
        const errBody = await response.json().catch(() => ({}));
        throw new Error(
          errBody.detail ||
            "Invalid clinician email or password. Please verify your credentials."
        );
      }
      const data = (await response.json()) as LoginResponsePayload;
      setStoredSession(data.access_token, data.clinician);
      router.push("/patients");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to reach the clinical API service. Verify the backend is running."
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main
      id="main-content"
      className="flex-1 flex flex-col justify-center items-center px-4 py-8 sm:py-12"
    >
      <div className="w-full max-w-md bg-white border border-slate-200 rounded-xl shadow-clinical p-6 sm:p-8">
        <header className="mb-5">
          <div className="flex items-center gap-2.5 mb-3">
            <span
              aria-hidden="true"
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-slate-900 text-white font-bold text-xs"
            >
              DB
            </span>
            <div>
              <span className="block text-xs font-semibold text-sky-800">
                Bridge Dermatology Clinic
              </span>
              <span className="block text-[11px] text-slate-600">
                Clinician Decision-Support Workspace
              </span>
            </div>
          </div>

          <h1 className="text-xl sm:text-2xl font-bold text-slate-900 tracking-tight">
            Sign in to Dermatology Bridge
          </h1>
          <p className="mt-1 text-xs text-slate-600 leading-relaxed">
            Review longitudinal skin concern trajectories, record regimens, and
            prepare consultation reports.{" "}
            <strong className="font-semibold text-slate-800">
              {CLINICAL_DISCLAIMER}
            </strong>
          </p>
        </header>

        {/* Primary inputs and submit kept high in viewport per modern-web-guidance 'autofill-sign-in-form' */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label
              htmlFor="email"
              className="block text-sm font-semibold text-slate-800 mb-1"
            >
              Clinician Email
            </label>
            <span
              id="email-hint"
              className="block text-xs text-slate-600 mb-1.5"
            >
              Clinic account email (e.g., dr.chen@bridgederm.local)
            </span>
            <input
              type="email"
              id="email"
              name="email"
              autoComplete="username"
              inputMode="email"
              spellCheck={false}
              enterKeyHint="next"
              required
              aria-describedby="email-hint"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="clinical-input w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 shadow-sm transition"
            />
            <div className="field-error-msg">
              Please enter a valid clinic email address.
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-1">
              <label
                htmlFor="current-password"
                className="block text-sm font-semibold text-slate-800"
              >
                Password
              </label>
              <button
                type="button"
                aria-pressed={showPassword}
                aria-controls="current-password"
                onClick={() => setShowPassword((prev) => !prev)}
                className="text-xs font-semibold text-sky-700 hover:text-sky-900 hover:underline px-1 py-0.5 rounded"
              >
                {showPassword ? "Hide password" : "Show password"}
              </button>
            </div>
            <input
              type={showPassword ? "text" : "password"}
              id="current-password"
              name="password"
              autoComplete="current-password"
              enterKeyHint="done"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="clinical-input w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 shadow-sm transition"
            />
            <div className="field-error-msg">Password is required.</div>
          </div>

          {error && (
            <div
              role="alert"
              className="rounded-lg bg-rose-50 border border-rose-300 px-3.5 py-2.5 text-xs font-medium text-rose-900 flex items-start gap-2"
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
            className="w-full rounded-lg bg-sky-700 hover:bg-sky-800 disabled:opacity-60 text-white font-semibold py-2.5 px-4 text-sm shadow-sm transition"
          >
            {submitting ? "Signing in to workspace..." : "Sign In"}
          </button>
        </form>

        {(email !== DEMO_EMAIL || password !== DEMO_PASS) && (
          <div className="mt-3 text-right">
            <button
              type="button"
              onClick={() => {
                setEmail(DEMO_EMAIL);
                setPassword(DEMO_PASS);
                setError(null);
              }}
              className="text-xs font-medium text-sky-700 hover:text-sky-900 hover:underline"
            >
              Restore demo clinician credentials
            </button>
          </div>
        )}

        <footer className="mt-6 pt-4 border-t border-slate-200 text-xs text-slate-600 space-y-1.5">
          <p>
            <strong className="font-semibold text-slate-800">
              Privacy &amp; Data Handling:
            </strong>{" "}
            {PRIVACY_NOTICE}
          </p>
          <p className="font-medium text-slate-700">{CLINICAL_DISCLAIMER}</p>
        </footer>
      </div>
    </main>
  );
}
