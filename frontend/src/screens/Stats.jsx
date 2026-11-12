import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { addDays } from "../lib/dates";
import { signed } from "../components/charts/scale";
import TrendChart from "../components/charts/TrendChart";
import WeekdayChart from "../components/charts/WeekdayChart";
import FactorChart from "../components/charts/FactorChart";
import CalendarHeat from "../components/charts/CalendarHeat";

const RANGES = [["30", "30 days"], ["90", "90 days"], ["365", "Year"], ["all", "All"]];
const MEASURES = [["morning", "Morning"], ["evening", "Evening"], ["daily", "Whole day"]];
const VIEWS = [["trend", "Trend"], ["weekday", "Weekdays"], ["factors", "Factors"], ["calendar", "Calendar"]];
const MIN_DAYS = 3;

// Remember the last choices on this device.
function useRemembered(key, initial) {
  const [v, setV] = useState(() => {
    try { return localStorage.getItem(key) ?? initial; } catch { return initial; }
  });
  const set = (x) => { setV(x); try { localStorage.setItem(key, x); } catch { /* private mode */ } };
  return [v, set];
}

function Segmented({ options, value, onChange, label, className = "" }) {
  return (
    <div className={`segmented ${className}`} role="radiogroup" aria-label={label}>
      {options.map(([id, text]) => (
        <button key={id} role="radio" aria-checked={value === id}
                className={value === id ? "active" : ""} onClick={() => onChange(id)}>
          {text}
        </button>
      ))}
    </div>
  );
}

export default function Stats({ me, onOpen }) {
  const [range, setRange] = useRemembered("stats.range", "30");
  const [measure, setMeasure] = useRemembered("stats.measure", "daily");
  const [view, setView] = useRemembered("stats.view", "trend");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);


  useEffect(() => {
    let cancelled = false;
    const start = range === "all" ? "2000-01-01" : addDays(me.today, -(Number(range) - 1));
    setLoading(true); setError(null);
    api.get(`/stats?start=${start}&end=${me.today}`)
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) setError(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [range, me.today]);

  const m = data?.measures[measure];
  const s = m?.summary;
  // For "All", start the charts at the first check-in instead of the year 2000.
  const start = range === "all" && m?.series.length ? m.series[0].day : data?.range.start;
  const end = data?.range.end;
  const periodName = range === "all" ? null : range === "365" ? "year" : `${range} days`;

  return (
    <main className="screen stats">
      <h1 className="display small">Stats</h1>

      <Segmented options={RANGES} value={range} onChange={setRange} label="Time range" />
      <Segmented options={MEASURES} value={measure} onChange={setMeasure} label="Which score" className="measure" />

      {error && <p className="error" role="alert">{error}</p>}
      {!data && loading && <p className="muted pad">Loading…</p>}

      {data && (
        <div className={loading ? "stats-body updating" : "stats-body"} aria-busy={loading}>
          {s.n_days < MIN_DAYS ? (
            <div className="empty">
              <p>Stats appear after {MIN_DAYS} days of {measure === "daily" ? "check-ins" : `${measure} check-ins`} in this period. You have {s.n_days}.</p>
              <button className="primary" onClick={() => onOpen(me.today, null)}>Check in now</button>
            </div>
          ) : (
            <>
              <section className="summary" aria-label="Summary">
                <p className="big-avg"><span className="num">{s.mean.toFixed(1)}</span> average</p>
                <ul className="facts">
                  {s.prev_n >= MIN_DAYS && periodName && (
                    <li>{signed(s.mean - s.prev_mean)} vs the previous {periodName}</li>
                  )}
                  <li>{s.n_days} of {range === "all" ? "your" : data.range.days} days logged</li>
                  {data.streak > 1 && <li>{data.streak}-day streak</li>}
                </ul>
              </section>

              <Segmented options={VIEWS} value={view} onChange={setView} label="View" className="views" />

              {view === "trend" && <TrendChart series={m.series} start={start} end={end} mean={s.mean} />}
              {view === "weekday" && <WeekdayChart rows={m.weekday} mean={s.mean} />}
              {view === "factors" && <FactorChart factors={m.factors} minGroup={data.min_group} />}
              {view === "calendar" && (
                <CalendarHeat series={m.series} start={start} end={end}
                              onOpen={(d) => onOpen(d, measure === "evening" ? "evening" : "morning")} />
              )}
            </>
          )}
        </div>
      )}
    </main>
  );
}
