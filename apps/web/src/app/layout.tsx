import type { Metadata } from "next";
import "./globals.css";
import { CLINICAL_DISCLAIMER, PRIVACY_NOTICE } from "@/lib/api";

export const metadata: Metadata = {
  title: "Dermatology Bridge — Clinical Decision Support",
  description: `Longitudinal skin analysis decision-support workspace built on YouCam Skin AI. ${CLINICAL_DISCLAIMER}`,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-surface-canvas text-ink-primary antialiased flex flex-col">
        <a href="#main-content" className="skip-link">
          Skip to main content
        </a>
        <div
          role="note"
          aria-label="Clinical disclaimer and privacy notice"
          className="bg-slate-900 text-slate-100 text-xs py-2 px-4 border-b border-slate-800"
        >
          <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-x-6 gap-y-1">
            <span className="inline-flex items-center gap-2 font-semibold tracking-wide text-sky-300">
              <span
                aria-hidden="true"
                className="inline-block h-1.5 w-1.5 rounded-full bg-sky-400"
              />
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
