import type { Metadata } from "next";
import "./globals.css";
import { CLINICAL_DISCLAIMER, PRIVACY_NOTICE } from "@/lib/api";

export const metadata: Metadata = {
  title: "Dermatology Bridge — Clinician Decision Support",
  description: `Longitudinal skin analysis decision-support tool built on YouCam Skin AI. ${CLINICAL_DISCLAIMER}`,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50 text-slate-900 antialiased flex flex-col">
        <div
          role="note"
          aria-label="Clinical disclaimer"
          className="bg-slate-900 text-slate-100 text-xs py-2 px-4 border-b border-slate-700"
        >
          <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-2">
            <span className="font-semibold tracking-wide text-sky-300">
              {CLINICAL_DISCLAIMER}
            </span>
            <span className="text-slate-300">{PRIVACY_NOTICE}</span>
          </div>
        </div>
        <div className="flex-1 flex flex-col">{children}</div>
      </body>
    </html>
  );
}

