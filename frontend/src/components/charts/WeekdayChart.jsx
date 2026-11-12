import { linear } from "./scale";

const W = 340, ROW = 34, L = 44, R = 44, T = 6;

export default function WeekdayChart({ rows, mean }) {
  const vals = rows.flatMap((r) => [r.ci_low ?? r.mean, r.ci_high ?? r.mean]).filter((v) => v != null);
  const lo = Math.max(1, Math.floor(Math.min(...vals, mean ?? 10) - 0.5));
  const hi = Math.min(10, Math.ceil(Math.max(...vals, mean ?? 1) + 0.5));
  const x = linear(lo, hi, L, W - R);
  const H = T + rows.length * ROW + 22;
  const ticks = [];
  for (let v = lo; v <= hi; v++) ticks.push(v);

  return (
    <figure className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Average mood by day of the week">
        {ticks.map((v) => (
          <g key={v}>
            <line className="grid" x1={x(v)} x2={x(v)} y1={T} y2={H - 22} />
            <text className="tick" x={x(v)} y={H - 6} textAnchor="middle">{v}</text>
          </g>
        ))}
        {mean != null && <line className="mean" x1={x(mean)} x2={x(mean)} y1={T} y2={H - 22} />}
        {rows.map((r, i) => {
          const cy = T + i * ROW + ROW / 2;
          return (
            <g key={r.weekday}>
              <text className="label" x={0} y={cy + 5}>{r.label}</text>
              {r.ci_low != null && <line className="whisker" x1={x(r.ci_low)} x2={x(r.ci_high)} y1={cy} y2={cy} />}
              {r.mean != null && <circle className="point" cx={x(r.mean)} cy={cy} r="5.5" />}
              <text className="tick" x={W} y={cy + 4} textAnchor="end">{r.n ? `${r.n} days` : "none"}</text>
            </g>
          );
        })}
      </svg>
      <figcaption>Average for each weekday. The bar shows the likely range (95% interval); wide bars mean few days so far.</figcaption>
    </figure>
  );
}
