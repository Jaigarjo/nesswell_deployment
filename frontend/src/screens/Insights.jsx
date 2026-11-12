import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { signed } from "../components/charts/scale";
import FactorChart from "../components/charts/FactorChart";
import ForecastCard from "../components/ForecastCard";
import { ExperimentCard, SuggestionCard } from "../components/Recommendations";
import { GeneralTips, ProgressSection } from "../components/Progress";

const TARGETS = [["morning", "Morning"], ["evening", "Evening"], ["daily", "Whole day"]];

export default function Insights({ me }) {
  const [data, setData] = useState(null);
  const [recs, setRecs] = useState(null);
  const [progress, setProgress] = useState(null);
  const [error, setError] = useState(null);
  const [target, setTarget] = useState("morning");


  useEffect(() => {
    let cancelled = false;
    Promise.all([api.get("/insights"), api.get("/recommendations"), api.get("/progress")])
      .then(([d, r, p]) => { if (!cancelled) { setData(d); setRecs(r); setProgress(p); } })
      .catch((e) => { if (!cancelled) setError(e.message); });
    return () => { cancelled = true; };
  }, []);

  if (error) return <main className="screen"><h1 className="display small">Insights</h1><p className="error">{error}</p></main>;
  if (!data || !recs || !progress) return <main className="screen"><h1 className="display small">Insights</h1><p className="muted pad">Looking for patterns…</p></main>;

  const exp = recs.experiment;
  const setExp = (e) => setRecs((r) => ({ ...r, experiment: e }));
  // Patterns already shown as suggestions don't need repeating below.
  const suggested = new Set(recs.suggestions.map((s) => `${s.key}:${s.lag}`));
  const others = data.top.filter((t) => !suggested.has(`${t.key}:${t.lag}`));

  return (
    <main className="screen insights">
      <h1 className="display small">Insights</h1>

      {exp && <ExperimentCard exp={exp} onChange={setExp} />}

      {/* Early on, progress comes first; once personal patterns exist, they lead. */}
      {recs.suggestions.length === 0 && <ProgressSection p={progress} />}

      <section aria-label="What helps you most">
        <h2>What helps you most</h2>
        {recs.suggestions.length === 0 ? (
          <p className="muted">
            Nothing personal yet. Suggestions appear once something clearly lifts your mood in your own data.
          </p>
        ) : (
          <ol className="suggestions">
            {recs.suggestions.map((s) => (
              <SuggestionCard key={`${s.key}-${s.target}-${s.lag}`} s={s}
                              canTest={!exp || exp.status !== "active"} onStarted={setExp} />
            ))}
          </ol>
        )}
        {exp?.status === "active" && recs.suggestions.length > 0 && (
          <p className="muted small">One experiment at a time. Finish or stop the current one to test another.</p>
        )}
      </section>

      <GeneralTips tips={progress.tips} />

      {recs.suggestions.length > 0 && <ProgressSection p={progress} />}

      {/* While it's still collecting mornings, the progress box already shows the forecast's status. */}
      {!(data.forecast.reason === "not_enough_data") && (
        <ForecastCard forecast={data.forecast} model={data.model} today={me.today} />
      )}

      {others.length > 0 && (
        <section className="standouts" aria-label="Other patterns">
          <h2>Other patterns</h2>
          <ol className="cards">
            {others.map((t) => (
              <li key={`${t.key}-${t.lag}-${t.target}`} className="card">
                <span className={t.diff > 0 ? "badge up" : "badge down"}>{signed(t.diff)}</span>
                <p>{t.text}</p>
                <p className="muted small">{t.lag ? "Next-day pattern" : "Same-day pattern"}. Based on {t.n_high} and {t.n_low} days.</p>
              </li>
            ))}
          </ol>
        </section>
      )}

      {Object.values(data.next_day).some((rows) => rows.some((r) => r.enough)) && (
      <section aria-label="Next-day effects">
        <h2>What carries over</h2>
        <p className="muted small">Yesterday's factors against today's mood. Pick which of today's scores to compare.</p>
        <div className="segmented" role="radiogroup" aria-label="Compared with">
          {TARGETS.map(([id, label]) => (
            <button key={id} role="radio" aria-checked={target === id}
                    className={target === id ? "active" : ""} onClick={() => setTarget(id)}>{label}</button>
          ))}
        </div>
        <FactorChart factors={data.next_day[target]} minGroup={5} dayWords={["The day after", "Otherwise"]}
                     caption="How much higher or lower your mood was the day after." />
      </section>
      )}
    </main>
  );
}
