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

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("dr.chen@bridgederm.local");
  const [password, setPassword] = useState("clinician-demo-pass");
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
        body: JSON.stringify({ email, password }),
      });
      if (!response.ok) {
        const errBody = await response.json().catch(() => ({}));
        throw new Error(errBody.detail || "Invalid clinician credentials.");
      }
      const data = (await response.json()) as LoginResponsePayload;
      setStoredSession(data.access_token, data.clinician);
      router.push("/patients");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex-1 flex flex-col justify-center items-center px-4 py-10">
      <div className="w-full max-w-md bg-white border border-slate-200 rounded-xl shadow-sm p-6 sm:p-8">
        <div className="mb-6">
          <span className="inline-block text-xs font-semibold uppercase tracking-wider text-sky-700 bg-sky-50 border border-sky-200 rounded px-2.5 py-0.5">
            Clinician Portal
          </span>
          <h1 className="mt-2 text-2xl font-bold text-slate-900">
            Sign in to Dermatology Bridge
          </h1>
          <p className="mt-1 text-xs text-slate-600">
            Longitudinal skin assessment decision-support workspace.{" "}
            <strong className="text-slate-800">{CLINICAL_DISCLAIMER}</strong>
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label
              htmlFor="email"
              className="block text-sm font-medium text-slate-800 mb-1"
            >
              Clinician Email
            </label>
            <input
              type="email"
              id="email"
              name="email"
              autoComplete="username"
              spellCheck={false}
              enterKeyHint="next"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-sky-600 focus:outline-none focus:ring-2 focus:ring-sky-600/20"
            />
          </div>

          <div>
            <div className="flex items-center justify-between mb-1">
              <label
                htmlFor="current-password"
                className="block text-sm font-medium text-slate-800"
              >
                Password
              </label>
              <button
                type="button"
                onClick={() => setShowPassword((prev) => !prev)}
                className="text-xs font-medium text-sky-700 hover:text-sky-900"
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
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-sky-600 focus:outline-none focus:ring-2 focus:ring-sky-600/20"
            />
          </div>

          {error && (
            <div
              role="alert"
              className="rounded-lg bg-rose-50 border border-rose-200 px-3 py-2 text-xs text-rose-800"
            >
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-lg bg-slate-900 hover:bg-slate-800 disabled:opacity-60 text-white font-semibold py-2.5 px-4 text-sm transition"
          >
            {submitting ? "Signing in..." : "Sign In"}
          </button>
        </form>

        <div className="mt-6 pt-4 border-t border-slate-200 text-xs text-slate-500 space-y-1">
          <p>{PRIVACY_NOTICE}</p>
          <p className="font-medium text-slate-700">{CLINICAL_DISCLAIMER}</p>
        </div>
      </div>
    </main>
  );
}

