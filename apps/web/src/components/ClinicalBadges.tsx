import React from "react";

export type SeverityLevel = "clear" | "mild" | "moderate" | "severe";
export type VerdictType =
  | "improving"
  | "stalled"
  | "worsening"
  | "insufficient_data";

const SEVERITY_CONFIG: Record<
  SeverityLevel,
  { symbol: string; label: string; classes: string }
> = {
  clear: {
    symbol: "●",
    label: "Clear",
    classes: "bg-emerald-50 text-emerald-900 border-emerald-300",
  },
  mild: {
    symbol: "◐",
    label: "Mild",
    classes: "bg-sky-50 text-sky-900 border-sky-300",
  },
  moderate: {
    symbol: "▲",
    label: "Moderate",
    classes: "bg-amber-50 text-amber-950 border-amber-300",
  },
  severe: {
    symbol: "◆",
    label: "Severe",
    classes: "bg-rose-50 text-rose-950 border-rose-300",
  },
};

const VERDICT_CONFIG: Record<
  VerdictType,
  { symbol: string; label: string; shortCode: string; classes: string }
> = {
  improving: {
    symbol: "↗",
    label: "Improving",
    shortCode: "improving",
    classes: "bg-emerald-50 text-emerald-900 border-emerald-300",
  },
  stalled: {
    symbol: "→",
    label: "Stable / Stalled",
    shortCode: "stalled",
    classes: "bg-slate-100 text-slate-800 border-slate-300",
  },
  worsening: {
    symbol: "↘",
    label: "Worsening",
    shortCode: "worsening",
    classes: "bg-rose-50 text-rose-900 border-rose-300",
  },
  insufficient_data: {
    symbol: "◊",
    label: "Insufficient Data",
    shortCode: "insufficient_data",
    classes: "bg-slate-50 text-slate-600 border-slate-300 border-dashed",
  },
};

export const MED_RESPONSE_CONFIG: Record<
  string,
  { symbol: string; label: string; classes: string }
> = {
  clinically_responsive: {
    symbol: "✓",
    label: "Favorable Co-Movement (≥ MDC)",
    classes: "bg-emerald-50 text-emerald-900 border-emerald-300",
  },
  early_favorable_trend: {
    symbol: "↗",
    label: "Early Favorable Trend",
    classes: "bg-sky-50 text-sky-900 border-sky-300",
  },
  minimal_change: {
    symbol: "→",
    label: "Within MDC Variability (|Δ| < MDC)",
    classes: "bg-slate-100 text-slate-800 border-slate-300",
  },
  potential_adverse_flare: {
    symbol: "▲",
    label: "Review: Potential Barrier / Flare Signal",
    classes: "bg-rose-50 text-rose-900 border-rose-300",
  },
  insufficient_followup: {
    symbol: "◷",
    label: "Within Onset Window / Awaiting Follow-Up",
    classes: "bg-amber-50/70 text-amber-950 border-amber-300 border-dashed",
  },
};

export const MED_CATEGORY_STYLES: Record<string, string> = {
  topical_retinoid: "bg-slate-100 text-slate-800 border-slate-300",
  oral_retinoid: "bg-slate-100 text-slate-800 border-slate-300",
  barrier_repair: "bg-teal-50 text-teal-900 border-teal-200",
  topical_acid: "bg-amber-50 text-amber-900 border-amber-200",
  anti_androgen: "bg-sky-50 text-sky-900 border-sky-200",
  oral_antibiotic: "bg-indigo-50 text-indigo-900 border-indigo-200",
  topical_antimicrobial: "bg-cyan-50 text-cyan-900 border-cyan-200",
  corticosteroid: "bg-orange-50 text-orange-900 border-orange-200",
  other: "bg-slate-100 text-slate-800 border-slate-300",
};

export function SeverityBadge({
  severity,
}: {
  severity: SeverityLevel | string | null | undefined;
}) {
  if (!severity || !(severity in SEVERITY_CONFIG)) {
    return (
      <span
        data-severity="unscored"
        className="inline-flex items-center gap-1 rounded border border-dashed border-slate-300 bg-slate-50 px-2 py-0.5 text-xs font-medium text-slate-600"
      >
        <span aria-hidden="true">○</span>
        <span>Not scored</span>
      </span>
    );
  }
  const cfg = SEVERITY_CONFIG[severity as SeverityLevel];
  return (
    <span
      data-severity={severity}
      className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 text-xs font-semibold ${cfg.classes}`}
    >
      <span aria-hidden="true" className="text-[10px]">
        {cfg.symbol}
      </span>
      <span>{cfg.label}</span>
    </span>
  );
}

export function VerdictBadge({
  verdict,
  delta,
}: {
  verdict: VerdictType | string;
  delta?: string | null;
}) {
  const cfg =
    VERDICT_CONFIG[verdict as VerdictType] || VERDICT_CONFIG.insufficient_data;
  const formattedDelta =
    delta !== undefined && delta !== null
      ? Number(delta) > 0
        ? `+${delta}`
        : String(delta)
      : null;

  return (
    <span
      data-verdict={verdict}
      className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 text-xs font-semibold ${cfg.classes}`}
    >
      <span aria-hidden="true">{cfg.symbol}</span>
      <span>{cfg.label}</span>
      {formattedDelta !== null && verdict !== "insufficient_data" && (
        <span className="font-mono text-[11px] opacity-90">
          (&Delta; {formattedDelta})
        </span>
      )}
    </span>
  );
}

export function DirectionBadge({
  direction,
  mdc,
  compact = false,
}: {
  direction: "higher_is_better" | "lower_is_better";
  mdc?: number;
  compact?: boolean;
}) {
  const isHigherBetter = direction === "higher_is_better";
  return (
    <span className="inline-flex flex-wrap items-center gap-1 text-xs text-slate-600">
      <span
        aria-hidden="true"
        className="inline-flex h-4 w-4 items-center justify-center rounded bg-slate-100 font-mono text-[11px] font-bold text-slate-700"
      >
        {isHigherBetter ? "↑" : "↓"}
      </span>
      <span>
        {compact
          ? isHigherBetter
            ? "Higher is better"
            : "Lower is better"
          : isHigherBetter
          ? "Higher score = healthier (0–100)"
          : "Lower score = less burden (0–100)"}
      </span>
      {mdc !== undefined && (
        <span
          className="font-mono text-[11px] text-slate-500"
          title="Minimal Detectable Change threshold on 0–100 scale"
        >
          &bull; MDC &plusmn;{mdc}
        </span>
      )}
    </span>
  );
}

export function ProvenanceBadge({
  kind,
}: {
  kind: "measured" | "hypothesis" | "correlation";
}) {
  if (kind === "measured") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded border border-slate-300 bg-slate-100 px-2.5 py-0.5 text-xs font-semibold text-slate-800">
        <span aria-hidden="true" className="text-sky-700">
          ●
        </span>
        <span>Observed Measurement (0–100 Scale)</span>
      </span>
    );
  }
  if (kind === "correlation") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded border border-amber-300 bg-amber-50 px-2.5 py-0.5 text-xs font-semibold text-amber-950">
        <span aria-hidden="true">◇</span>
        <span>Temporal Co-Movement &mdash; Not Proof of Causation</span>
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 rounded border border-sky-300 bg-sky-50 px-2.5 py-0.5 text-xs font-semibold text-sky-950">
      <span aria-hidden="true">✦</span>
      <span>Generated Hypothesis &mdash; For Clinician Review</span>
    </span>
  );
}
