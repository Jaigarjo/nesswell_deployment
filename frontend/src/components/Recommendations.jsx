import { useState } from "react";
import { api } from "../lib/api";
import { signed } from "./charts/scale";

const TARGET = {
  "0:morning": "on your morning mood", "0:evening": "on your evening mood",
  "0:daily": "on your day overall", "1:morning": "on the next morning",
};
const WEEKDAY = (day) => new Date(day + "T12:00:00").toLocaleDateString(undefined, { weekday: "narrow" });
const STATUS_TEXT = { done: "done", missed: "not done", unlogged: "not logged", today: "today", upcoming: "still to come" };

export function SuggestionCard({ s, canTest, onStarted }) {
  const [choosing, setChoosing] = useState(false);
  const [goal, setGoal] = useState(4);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function start() {
    setBusy(true); setError(null);
    try {
      onStarted(await api.post("/experiments", { key: s.key, target: s.target, lag: s.lag, goal_days: goal }));
    } catch (e) { setError(e.message); setBusy(false); }
  }

  return (
    <li className="suggestion">
      <h3>{s.action}</h3>
      <p className="gain">
        <span className="pts">{signed(s.gain)}</span>
        <span className="unit">points{s.percent != null && <> ({s.percent > 0 ? "+" : ""}{s.percent}%)</>}</span>
        <span className="where">{TARGET[`${s.lag}:${s.target}`]}</span>
      </p>
      <p className="muted small">
        {s.good_mean.toFixed(1)} when you do, {s.bad_mean.toFixed(1)} when you don't, across {s.n_good} and {s.n_bad} days.
      </p>

      {canTest && !choosing && (
        <button className="secondary" onClick={() => setChoosing(true)}>Test it for a week</button>
      )}
      {choosing && (
        <div className="chooser">
          <p className="small">On how many of the next 7 days?</p>
          <div className="segmented" role="radiogroup" aria-label="Days to aim for">
            {[3, 4, 5, 6].map((n) => (
              <button key={n} role="radio" aria-checked={goal === n} className={goal === n ? "active" : ""} onClick={() => setGoal(n)}>{n} days</button>
            ))}
          </div>
          <div className="row">
            <button className="primary" disabled={busy} onClick={start}>{busy ? "Starting…" : "Start experiment"}</button>
            <button className="link" onClick={() => setChoosing(false)}>Cancel</button>
          </div>
          {error && <p className="error">{error}</p>}
        </div>
      )}
    </li>
  );
}

export function ExperimentCard({ exp, onChange, compact = false }) {
  const [busy, setBusy] = useState(false);
  const p = exp.progress;
  const done = exp.status !== "active";
  const where = TARGET[`${exp.lag}:${exp.target}`];

  async function stop() {
    if (!window.confirm("Stop this experiment? Its progress won't be scored.")) return;
    setBusy(true);
    try { await api.post(`/experiments/${exp.id}/stop`); onChange(null); } catch { setBusy(false); }
  }

  return (
    <section className={compact ? "experiment compact" : "experiment"} aria-label="Experiment">
      {compact ? (
        <p className="exp-line"><span className="muted">Experiment day {p.day} of {p.days_total}:</span> {exp.action}</p>
      ) : (
        <>
          <p className="exp-kicker">{done ? "Experiment finished" : `Experiment, day ${p.day} of ${p.days_total}`}</p>
          <h2>{exp.action}</h2>
        </>
      )}
      <ol className="exp-days" aria-label="Days">
        {p.days.map((d) => (
          <li key={d.day} className={`exp-day ${d.status}`} aria-label={`${d.day}: ${STATUS_TEXT[d.status]}`}>
            <span className="mark" aria-hidden="true">{d.status === "done" ? "✓" : d.status === "missed" ? "×" : ""}</span>
            <span className="wd" aria-hidden="true">{WEEKDAY(d.day)}</span>
          </li>
        ))}
      </ol>
      <p className="small">
        {p.done} of {exp.goal_days} days done{done ? "" : " so far"}.{!compact && <> Measuring the effect {where}.</>}
      </p>

      {!compact && exp.result && (
        <div className="exp-result">
          <p><strong>{exp.result.verdict}</strong></p>
          <p className="muted small">
            {exp.result.with_mean != null && <>Days you did it: {exp.result.with_mean.toFixed(1)} ({exp.result.n_with}). </>}
            {exp.result.without_mean != null && <>Days you didn't: {exp.result.without_mean.toFixed(1)} ({exp.result.n_without}). </>}
            {exp.result.vs_prior != null && <>The whole week vs the 4 weeks before: {signed(exp.result.vs_prior)}.</>}
          </p>
        </div>
      )}
      {!compact && !done && <button className="link" disabled={busy} onClick={stop}>Stop experiment</button>}
    </section>
  );
}
