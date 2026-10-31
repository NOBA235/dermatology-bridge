"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { CLINICAL_DISCLAIMER, getStoredToken } from "@/lib/api";

export default function HomePage() {
  const router = useRouter();

  useEffect(() => {
    const token = getStoredToken();
    if (token) {
      router.replace("/patients");
    } else {
      router.replace("/login");
    }
  }, [router]);

  return (
    <main
      id="main-content"
      className="flex-1 flex flex-col items-center justify-center px-4 py-16 text-center"
    >
      <div className="max-w-md w-full rounded-xl bg-white border border-slate-200 p-6 shadow-clinical space-y-3">
        <div className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-slate-900 text-white font-bold text-xs">
          DB
        </div>
        <h1 className="text-lg font-bold text-slate-900">Dermatology Bridge</h1>
        <p className="text-xs text-slate-600" role="status" aria-live="polite">
          Opening clinical workspace&hellip;
        </p>
        <p className="text-xs text-slate-500 pt-2 border-t border-slate-100">
          {CLINICAL_DISCLAIMER}
        </p>
        <div className="pt-1 flex justify-center gap-4 text-xs font-semibold text-sky-700">
          <Link href="/patients" className="hover:underline">
            Patient Directory
          </Link>
          <span aria-hidden="true" className="text-slate-300">
            &bull;
          </span>
          <Link href="/login" className="hover:underline">
            Clinician Sign In
          </Link>
        </div>
      </div>
    </main>
  );
}
