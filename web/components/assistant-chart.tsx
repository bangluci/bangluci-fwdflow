import { formatNumber } from "@/lib/format";
import type { AssistantAnswer, ChartSpec } from "@/lib/assistant-types";

const MAX_POINTS = 30;
const W = 640;
const H = 260;
const PAD = { top: 16, right: 16, bottom: 56, left: 56 };
const COLORS = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)"];

type Point = { label: string; value: number };

function toPoints(chart: ChartSpec, columns: string[], rows: AssistantAnswer["rows"]): Point[] {
  const xi = columns.indexOf(chart.x);
  const yi = columns.indexOf(chart.y);
  return rows.slice(0, MAX_POINTS).map((row) => ({ label: String(row[xi] ?? ""), value: Number(row[yi] ?? 0) }));
}

const shorten = (text: string) => (text.length > 14 ? `${text.slice(0, 13)}…` : text);

function Axes({ max }: { max: number }) {
  const ticks = [0, 0.5, 1].map((f) => f * max);
  return (
    <g className="text-[10px] text-muted-foreground" fill="currentColor">
      {ticks.map((t) => {
        const y = PAD.top + (1 - t / max) * (H - PAD.top - PAD.bottom);
        return (
          <g key={t}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y} y2={y} stroke="var(--border)" />
            <text x={PAD.left - 6} y={y + 3} textAnchor="end">{formatNumber(Math.round(t * 100) / 100)}</text>
          </g>
        );
      })}
    </g>
  );
}

function Bars({ points }: { points: Point[] }) {
  const max = Math.max(...points.map((p) => p.value), 1);
  const slot = (W - PAD.left - PAD.right) / points.length;
  return (
    <>
      <Axes max={max} />
      {points.map((p, i) => {
        const height = (p.value / max) * (H - PAD.top - PAD.bottom);
        const x = PAD.left + i * slot + slot * 0.15;
        return (
          <g key={i}>
            <rect x={x} y={H - PAD.bottom - height} width={slot * 0.7} height={height} rx={2} fill={COLORS[0]} />
            <text x={x + slot * 0.35} y={H - PAD.bottom + 14} textAnchor="middle" className="text-[10px]" fill="currentColor">{shorten(p.label)}</text>
          </g>
        );
      })}
    </>
  );
}

function Line({ points }: { points: Point[] }) {
  const max = Math.max(...points.map((p) => p.value), 1);
  const slot = (W - PAD.left - PAD.right) / Math.max(points.length - 1, 1);
  const at = (i: number, v: number) => [PAD.left + i * slot, PAD.top + (1 - v / max) * (H - PAD.top - PAD.bottom)] as const;
  const path = points.map((p, i) => at(i, p.value).join(",")).join(" ");
  return (
    <>
      <Axes max={max} />
      <polyline points={path} fill="none" stroke={COLORS[0]} strokeWidth={2} />
      {points.map((p, i) => (
        <g key={i}>
          <circle cx={at(i, p.value)[0]} cy={at(i, p.value)[1]} r={3} fill={COLORS[0]} />
          <text x={at(i, p.value)[0]} y={H - PAD.bottom + 14} textAnchor="middle" className="text-[10px]" fill="currentColor">{shorten(p.label)}</text>
        </g>
      ))}
    </>
  );
}

function Pie({ points }: { points: Point[] }) {
  const total = points.reduce((sum, p) => sum + Math.max(p.value, 0), 0) || 1;
  const cx = 130;
  const cy = H / 2;
  const r = 100;
  const shares = points.map((p) => Math.max(p.value, 0) / total);
  const starts = shares.map((_, i) => -Math.PI / 2 + shares.slice(0, i).reduce((a, b) => a + b, 0) * 2 * Math.PI);
  return (
    <>
      {points.map((p, i) => {
        const [start, end] = [starts[i], starts[i] + shares[i] * 2 * Math.PI];
        const large = shares[i] > 0.5 ? 1 : 0;
        const [x1, y1] = [cx + r * Math.cos(start), cy + r * Math.sin(start)];
        const [x2, y2] = [cx + r * Math.cos(end), cy + r * Math.sin(end)];
        const d = shares[i] >= 0.9999 ? `M ${cx - r} ${cy} a ${r} ${r} 0 1 0 ${2 * r} 0 a ${r} ${r} 0 1 0 ${-2 * r} 0` : `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} Z`;
        return <path key={i} d={d} fill={COLORS[i % COLORS.length]} stroke="var(--background)" strokeWidth={1} />;
      })}
      <g className="text-[11px]" fill="currentColor">
        {points.slice(0, 12).map((p, i) => (
          <g key={i} transform={`translate(270 ${30 + i * 18})`}>
            <rect width={10} height={10} y={-9} fill={COLORS[i % COLORS.length]} rx={2} />
            <text x={16}>{shorten(p.label)}: {formatNumber(p.value)} ({Math.round(shares[i] * 100)}%)</text>
          </g>
        ))}
      </g>
    </>
  );
}

/** Biểu đồ SVG đơn giản (cột / đường / tròn) cho tối đa 30 điểm; bảng kết quả đi kèm là bản đầy đủ cho trình đọc màn hình. */
export function AssistantChart({ chart, columns, rows }: { chart: ChartSpec; columns: string[]; rows: AssistantAnswer["rows"] }) {
  const points = toPoints(chart, columns, rows);
  if (points.length === 0) return null;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Biểu đồ ${chart.y} theo ${chart.x}`} className="h-auto w-full max-w-2xl text-foreground">
      {chart.type === "bar" && <Bars points={points} />}
      {chart.type === "line" && <Line points={points} />}
      {chart.type === "pie" && <Pie points={points} />}
    </svg>
  );
}
