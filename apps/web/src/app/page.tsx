"use client";

import { useEffect } from "react";
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
    <main className="max-w-3xl mx-auto px-4 py-16 text-center">
      <h1 className="text-2xl font-bold text-slate-900">Dermatology Bridge</h1>
      <p className="mt-2 text-sm text-slate-600">{CLINICAL_DISCLAIMER}</p>
    </main>
  );
}

