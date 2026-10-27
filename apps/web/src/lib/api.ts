/**
 * Typed client for the Dermatology Bridge FastAPI backend.
 *
 * For clinician review — not a diagnosis.
 */

export const CLINICAL_DISCLAIMER = "For clinician review — not a diagnosis.";
export const PRIVACY_NOTICE =
  "Photos are stored privately and deletable on request.";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

const TOKEN_STORAGE_KEY = "dermobridge_clinician_jwt";
const CLINICIAN_STORAGE_KEY = "dermobridge_clinician_profile";

export interface ClinicianProfile {
  id: string;
  clinic_id: string;
  email: string;
  full_name: string | null;
}

export interface PatientRecord {
  id: string;
  clinic_id: string;
  external_ref: string | null;
  full_name: string;
  dob: string | null;
  consent_version: string;
  notes: string | null;
  created_at: string;
  visit_count: number;
  latest_visit_date: string | null;
  disclaimer: string;
}

export interface ConcernScoreItem {
  id: number;
  visit_id: string;
  concern: string;
  score: string;
  severity: "clear" | "mild" | "moderate" | "severe";
}

export interface VisitRecord {
  id: string;
  patient_id: string;
  visit_date: string;
  chief_complaint: string | null;
  routine_text: string | null;
  treatment_changes: string | null;
  analysis_version: number;
  youcam_status: "pending" | "success" | "failed";
  concern_scores: ConcernScoreItem[];
  created_at: string;
  disclaimer: string;
}

export interface TrendPoint {
  visit_id: string;
  visit_date: string;
  score: string;
  severity: "clear" | "mild" | "moderate" | "severe";
}

export interface ConcernTrend {
  concern: string;
  label: string;
  direction: "higher_is_better" | "lower_is_better";
  mdc: number;
  baseline_score: string | null;
  baseline_severity: "clear" | "mild" | "moderate" | "severe" | null;
  latest_score: string | null;
  latest_severity: "clear" | "mild" | "moderate" | "severe" | null;
  delta: string | null;
  pct_change: string | null;
  verdict: "improving" | "stalled" | "worsening" | "insufficient_data";
  points: TrendPoint[];
}

export interface PatientTrendsResponse {
  patient_id: string;
  visit_count: number;
  analysis_version: number | null;
  baseline_date: string | null;
  latest_date: string | null;
  days_between: number | null;
  concerns: ConcernTrend[];
  disclaimer: string;
}

export interface TreatmentFlagRecord {
  id: number;
  patient_id: string;
  concern: string;
  delta: string;
  pct_change: string | null;
  verdict: "improving" | "stalled" | "worsening" | "insufficient_data";
  hypothesis: string | null;
  generated_at: string;
}

export interface PatientFlagsResponse {
  patient_id: string;
  visit_count: number;
  top_concern_indices: number[];
  top_concerns: string[];
  summary: string;
  used_fallback: boolean;
  flags: TreatmentFlagRecord[];
  disclaimer: string;
}

export interface CaptureTokenResponse {
  token: string;
  capture_path: string;
  expires_in_seconds: number;
  patient_id: string;
  privacy_notice: string;
  disclaimer: string;
}

export interface CaptureSessionInfo {
  valid: boolean;
  patient_id: string;
  patient_display_name: string;
  clinic_name: string;
  consent_version: string;
  privacy_notice: string;
  disclaimer: string;
}

export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function setStoredSession(
  token: string,
  clinician: ClinicianProfile
): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
  window.localStorage.setItem(CLINICIAN_STORAGE_KEY, JSON.stringify(clinician));
}

export function clearStoredSession(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_STORAGE_KEY);
  window.localStorage.removeItem(CLINICIAN_STORAGE_KEY);
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getStoredToken();
  const headers = new Headers(options.headers || {});
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  });
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const errJson = await response.json();
      if (errJson?.detail) detail = String(errJson.detail);
    } catch {
      // ignore json parse error
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

