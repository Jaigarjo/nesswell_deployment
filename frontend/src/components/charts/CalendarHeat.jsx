import { toTime } from "./scale";

const DAY = 86400000;
const iso = (t) => {
  const d = new Date(t);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
};

export default function CalendarHeat({ series, start, end, onOpen }) {
  const values = Object.fromEntries(series.map((p) => [p.day, p.value]));
  const first = new Date(toTime(start));
  const mondayOffset = (first.getDay() + 6) % 7;
  let t = toTime(start) - mondayOffset * DAY;
  const last = toTime(end);

  const weeks = [];
  while (t <= last) {
    const days = [];
    for (let i = 0; i < 7; i++, t += DAY) days.push(iso(t));
    weeks.push(days);
  }

  // Stretch the colour ramp to this person's own range; most moods live between 4 and 8.
  const vals = series.map((p) => p.value);
  const lo = vals.length ? Math.floor(Math.min(...vals)) : 1;
  const hi = vals.length ? Math.ceil(Math.max(...vals)) : 10;
  const pct = (v) => (hi === lo ? 70 : Math.round(10 + ((v - lo) / (hi - lo)) * 90));
  // Greyscale: low days sit close to the page colour, high days close to the ink.
  const fill = (v) => `color-mix(in srgb, var(--ink) ${pct(v)}%, var(--bg))`;

  return (
    <figure className="chart">
      <div className="cal" role="grid" aria-label="Mood calendar">
        <div className="cal-row head" role="row">
          <span />
          {["M", "T", "W", "T", "F", "S", "S"].map((d, i) => <span key={i} role="columnheader">{d}</span>)}
        </div>
        {weeks.map((w) => {
          // Label the row where a month begins (or the first row).
          const labelDay = w.find((d) => d >= start && d <= end && (d.endsWith("-01") || d === start));
          return (
            <div className="cal-row" role="row" key={w[0]}>
              <span className="cal-month">
                {labelDay ? new Date(labelDay + "T12:00:00").toLocaleDateString(undefined, { month: "short" }) : ""}
              </span>
              {w.map((d) => {
                const v = values[d];
                const out = d < start || d > end;
                if (out) return <span key={d} className="cal-cell out" />;
                return (
                  <button
                    key={d} role="gridcell"
                    className={v == null ? "cal-cell empty" : "cal-cell"}
                    style={v == null ? undefined : { background: fill(v), color: pct(v) > 50 ? "var(--bg)" : "var(--ink)", borderColor: "transparent" }}
                    aria-label={`${d}: ${v == null ? "no check-in" : v}`}
                    onClick={() => onOpen(d)}
                  >
                    {v != null && <span className="cal-num">{Math.round(v)}</span>}
                  </button>
                );
              })}
            </div>
          );
        })}
      </div>
      <div className="cal-legend" aria-hidden="true"><span>{lo}</span><span className="ramp" /><span>{hi}</span></div>
      <figcaption>Tap a day to open it.</figcaption>
    </figure>
  );
}
