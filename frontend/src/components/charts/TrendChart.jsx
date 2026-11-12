import { linear, shortDate, toTime } from "./scale";

const W = 340, H = 210, L = 26, R = 8, T = 10, B = 26;

export default function TrendChart({ series, start, end, mean }) {
  const x = linear(toTime(start), toTime(end), L, W - R);
  const y = linear(1, 10, H - B, T);

  // Break the rolling line wherever there isn't enough data.
  const segments = [];
  let cur = [];
  for (const p of series) {
    if (p.rolling == null) { if (cur.length) segments.push(cur); cur = []; continue; }
    cur.push(`${x(toTime(p.day)).toFixed(1)},${y(p.rolling).toFixed(1)}`);
  }
  if (cur.length) segments.push(cur);

  const mid = new Date((toTime(start) + toTime(end)) / 2).toISOString().slice(0, 10);

  return (
    <figure className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Mood over time with a 7-day average line">
        {[2, 4, 6, 8, 10].map((v) => (
          <g key={v}>
            <line className="grid" x1={L} x2={W - R} y1={y(v)} y2={y(v)} />
            <text className="tick" x={L - 6} y={y(v) + 4} textAnchor="end">{v}</text>
          </g>
        ))}
        {mean != null && <line className="mean" x1={L} x2={W - R} y1={y(mean)} y2={y(mean)} />}
        {series.map((p) => <circle key={p.day} className="dot" cx={x(toTime(p.day))} cy={y(p.value)} r="2.6" />)}
        {segments.map((s, i) =>
          s.length > 1 ? <polyline key={i} className="line" points={s.join(" ")} /> : null)}
        {[start, mid, end].map((d, i) => (
          <text key={d + i} className="tick" x={x(toTime(d))} y={H - 6}
                textAnchor={i === 0 ? "start" : i === 2 ? "end" : "middle"}>{shortDate(d)}</text>
        ))}
      </svg>
      <figcaption>Dots are single days. The line is your 7-day average; the dashed line is the average for this period.</figcaption>
    </figure>
  );
}
