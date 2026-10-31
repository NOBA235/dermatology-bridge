import React from "react";

export function SparklineSvg({
  points,
  verdict,
  label,
}: {
  points: { score: string; visit_date: string }[];
  verdict: string;
  label?: string;
}) {
  if (!points || points.length === 0) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-slate-500 italic">
        <span aria-hidden="true">&mdash;</span> No scans recorded
      </span>
    );
  }

  const scores = points.map((p) => Number(p.score));
  const minVal = Math.max(0, Math.min(...scores) - 8);
  const maxVal = Math.min(100, Math.max(...scores) + 8);
  const span = Math.max(10, maxVal - minVal);
  const width = 104;
  const height = 28;

  const coords = scores.map((val, idx) => {
    const x =
      scores.length === 1
        ? width / 2
        : 10 + (idx / (scores.length - 1)) * (width - 20);
    const y = height - 5 - ((val - minVal) / span) * (height - 10);
    return { x, y, val, date: points[idx].visit_date };
  });

  const strokeColor =
    verdict === "improving"
      ? "#15803d"
      : verdict === "worsening"
      ? "#be123c"
      : "#475569";

  const polylinePoints = coords.map((c) => `${c.x},${c.y}`).join(" ");
  const firstPt = coords[0];
  const lastPt = coords[coords.length - 1];

  const accessibleSummary =
    coords.length === 1
      ? `${label ? `${label}: ` : ""}Single baseline scan score ${
          firstPt.val
        } on ${firstPt.date}`
      : `${label ? `${label}: ` : ""}Trend across ${
          points.length
        } scans from ${firstPt.val} (${firstPt.date}) to ${lastPt.val} (${
          lastPt.date
        })`;

  return (
    <div className="inline-flex items-center gap-2">
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={accessibleSummary}
        className="overflow-visible shrink-0"
      >
        {/* Subtle baseline reference line */}
        {coords.length > 1 && (
          <line
            x1={6}
            y1={firstPt.y}
            x2={width - 6}
            y2={firstPt.y}
            stroke="#cbd5e1"
            strokeWidth="1"
            strokeDasharray="2 2"
          />
        )}
        {coords.length > 1 && (
          <polyline
            fill="none"
            stroke={strokeColor}
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            points={polylinePoints}
          />
        )}
        {coords.map((c, idx) => {
          const isLast = idx === coords.length - 1 && coords.length > 1;
          return isLast ? (
            <rect
              key={idx}
              x={c.x - 3.5}
              y={c.y - 3.5}
              width="7"
              height="7"
              rx="1"
              fill={strokeColor}
              stroke="#ffffff"
              strokeWidth="1.25"
            />
          ) : (
            <circle
              key={idx}
              cx={c.x}
              cy={c.y}
              r="3"
              fill={idx === 0 ? "#ffffff" : strokeColor}
              stroke={strokeColor}
              strokeWidth="1.75"
            />
          );
        })}
      </svg>
      <span className="font-mono text-[11px] text-slate-600 whitespace-nowrap">
        {coords.length} {coords.length === 1 ? "pt" : "pts"}
      </span>
    </div>
  );
}
