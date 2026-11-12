import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { addDays, formatDay } from "../lib/dates";
import ScoreRow from "../components/ScoreRow";
import FactorInput from "../components/FactorInput";
import ForecastCard from "../components/ForecastCard";
import { ExperimentCard } from "../components/Recommendations";
import DetailSheet from "../components/DetailSheet";
import { savedLine } from "../components/Progress";
import { cleanDetails, hasData, summarize } from "../lib/details";

const EMPTY = { score: null, note: "", values: {}, details: {} };

function pickKind(entries) {
  const beforeAfternoon = new Date().getHours() < 15;
  if (!entries.morning && beforeAfternoon) return "morning";
  if (!entries.evening) return "evening";
  return beforeAfternoon ? "morning" : "evening";
}

function useSlowHint(active, ms = 4000) {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    if (!active) { setSlow(false); return; }
    const t = setTimeout(() => setSlow(true), ms);
    return () => clearTimeout(t);
  }, [active, ms]);
  return slow;
}

export default function CheckIn({ me, factors, target }) {
  const today = me.today;
  const [day, setDay] = useState(target.day && target.day <= today ? target.day : today);
  const [kind, setKind] = useState(target.kind);
  const [entries, setEntries] = useState(null); // { morning?: Entry, evening?: Entry } for `day`
  const [form, setForm] = useState(EMPTY);
  const [openFactor, setOpenFactor] = useState(null);
  const [cheer, setCheer] = useState(null); // streak / milestone line shown after saving // key of the factor whose detail sheet is open
  const [status, setStatus] = useState("loading"); // loading | ready | saving | saved
  const [error, setError] = useState(null);
  const [forecast, setForecast] = useState(null);
  const [experiment, setExperiment] = useState(null);
  const [prefilled, setPrefilled] = useState(false);
  const kindChosen = useRef(Boolean(target.kind));
  const justSaved = useRef(false);
  const forecastRef = useRef(null);
  const slow = useSlowHint(status === "loading" || status === "saving");

  // Load both check-ins for the selected day.
  useEffect(() => {
    let cancelled = false;
    setStatus("loading"); setError(null); setEntries(null);
    api.get(`/entries?start=${day}&end=${day}`)
      .then((rows) => {
        if (cancelled) return;
        const byKind = Object.fromEntries(rows.map((r) => [r.kind, r]));
        setEntries(byKind);
        if (!kindChosen.current) { setKind(pickKind(byKind)); kindChosen.current = true; }
        setStatus("ready");
      })
      .catch((e) => { if (!cancelled) { setError(e.message); setStatus("ready"); } });
    return () => { cancelled = true; };
  }, [day]);

  // Fill the form from whatever is saved for this day + kind.
  useEffect(() => {
    if (!entries || !kind) return;
    const e = entries[kind];
    setForm(e ? { score: e.score, note: e.note || "", values: e.values, details: e.details || {} } : EMPTY);
    setOpenFactor(null);
    setCheer(null);
  }, [entries, kind]);


  // New morning check-in: fill hours slept from Garmin if it has them. You can still change it.
  useEffect(() => {
    setPrefilled(false);
    if (kind !== "morning" || !entries || entries.morning) return;
    let cancelled = false;
    api.get(`/metrics?start=${day}&end=${day}`).then((m) => {
      const hours = m?.[day]?.g_sleep_hours;
      if (cancelled || hours == null) return;
      setForm((f) => (f.values.sleep_hours !== undefined ? f : { ...f, values: { ...f.values, sleep_hours: Math.round(hours * 2) / 2 } }));
      setPrefilled(true);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [kind, day, entries]);

  // A running experiment shows up in the check-in it's measured by.
  useEffect(() => {
    let cancelled = false;
    api.get("/experiments/current").then((r) => { if (!cancelled) setExperiment(r.experiment); }).catch(() => {});
    return () => { cancelled = true; };
  }, [entries]);
  const showExperiment = experiment && experiment.status === "active" && experiment.applies_to === kind
    && day >= experiment.start_day && day <= experiment.end_day;

  // After tonight's check-in exists, show the forecast for tomorrow morning.
  const eveningStamp = entries?.evening?.logged_at;
  useEffect(() => {
    setForecast(null);
    if (kind !== "evening" || day !== today || !eveningStamp) return;
    let cancelled = false;
    api.get(`/forecast?day=${day}`).then((r) => { if (!cancelled) setForecast(r); }).catch(() => {});
    return () => { cancelled = true; };
  }, [kind, day, today, eveningStamp]);

  // Bring the forecast into view right after saving tonight's check-in.
  useEffect(() => {
    if (!forecast || !justSaved.current) return;
    justSaved.current = false;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    forecastRef.current?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "center" });
  }, [forecast]);



  // Device factors (Garmin) sync on their own; only manual ones are typed in.
  const shown = factors.filter((f) => f.applies_to === kind && f.source === "manual");
  const toggles = shown.filter((f) => f.value_type === "bool");
  const others = shown.filter((f) => f.value_type !== "bool");
  const existing = Boolean(entries?.[kind]);
  const isToday = day === today;

  const setValue = (key, v) =>
    setForm((f) => {
      const values = { ...f.values };
      if (v === undefined) delete values[key]; else values[key] = v;
      return { ...f, values };
    });

  // Adding specifics ("Run, 35 min") to a yes/no factor means yes.
  const setDetail = (f, d) =>
    setForm((prev) => {
      const values = { ...prev.values };
      if (f.value_type === "bool" && hasData(d) && values[f.key] !== 1) values[f.key] = 1;
      return { ...prev, values, details: { ...prev.details, [f.key]: d } };
    });
  const summaryOf = (f) => summarize(f.detail_schema, form.details[f.key]);
  const sheetFactor = shown.find((f) => f.key === openFactor);

  async function save() {
    setStatus("saving"); setError(null);
    const values = {};
    for (const f of shown) {
      const v = form.values[f.key];
      if (f.value_type === "bool") values[f.key] = v ?? 0; // you saw the toggle, so off means no
      else if (v !== undefined) values[f.key] = v;
    }
    try {
      const saved = await api.put(`/entries/${day}/${kind}`, {
        score: form.score, note: form.note.trim() || null, values,
        details: cleanDetails(form.details, shown.map((f) => f.key)),
      });
      setEntries((prev) => ({ ...prev, [kind]: saved }));
      justSaved.current = kind === "evening";
      setStatus("saved");
      api.get("/progress").then((p) => setCheer(savedLine(p))).catch(() => {});
      setTimeout(() => setStatus((s) => (s === "saved" ? "ready" : s)), 2000);
    } catch (e) {
      setError(e.message); setStatus("ready");
    }
  }

  async function remove() {
    if (!window.confirm(`Delete the ${kind} check-in for ${formatDay(day, today).toLowerCase()}?`)) return;
    try {
      await api.del(`/entries/${day}/${kind}`);
      setEntries((prev) => { const n = { ...prev }; delete n[kind]; return n; });
    } catch (e) { setError(e.message); }
  }

  const question = kind === "morning"
    ? (isToday ? "How are you this morning?" : "How were you that morning?")
    : (isToday ? "How was today?" : "How was that day?");

  return (
    <main className="screen checkin">
      <header className="day-nav">
        <button className="icon" aria-label="Previous day" onClick={() => setDay(addDays(day, -1))}>‹</button>
        <label className="day-label">
          <span>{formatDay(day, today)}</span>
          <input
            type="date" max={today} value={day} aria-label="Pick a date"
            onChange={(e) => e.target.value && e.target.value <= today && setDay(e.target.value)}
          />
        </label>
        <button className="icon" aria-label="Next day" disabled={day >= today} onClick={() => setDay(addDays(day, 1))}>›</button>
      </header>

      <div className="moment-switch" role="tablist" aria-label="Check-in">
        {["morning", "evening"].map((k) => (
          <button
            key={k} role="tab" aria-selected={kind === k}
            className={kind === k ? "active" : ""}
            onClick={() => { setKind(k); kindChosen.current = true; }}
          >
            {k === "morning" ? "Morning" : "Evening"}
            {entries?.[k] && <span className="done" aria-label="logged"> ✓</span>}
          </button>
        ))}
      </div>

      {status === "loading" || !kind ? (
        <p className="muted pad">{slow ? "Waking up the server. The first load can take up to a minute." : "Loading…"}</p>
      ) : (
        <form className="checkin-form" onSubmit={(e) => { e.preventDefault(); if (form.score) save(); }}>
          {showExperiment && <ExperimentCard exp={experiment} compact />}
          <h1 className="question">{question}</h1>
          <ScoreRow value={form.score} onChange={(score) => setForm((f) => ({ ...f, score }))} label={question} />

          {others.map((f) => (
            <FactorInput key={f.key} factor={f} value={form.values[f.key]}
                         summary={summaryOf(f)} onDetails={() => setOpenFactor(f.key)}
                         hint={prefilled && f.key === "sleep_hours" ? "From Garmin" : null}
                         onChange={(v) => { if (f.key === "sleep_hours") setPrefilled(false); setValue(f.key, v); }} />
          ))}

          {toggles.length > 0 && (
            <fieldset className="chips">
              <legend>{kind === "evening" ? "Today I…" : "This morning"}</legend>
              {toggles.map((f) => (
                <FactorInput key={f.key} factor={f} value={form.values[f.key]} onChange={(v) => setValue(f.key, v)}
                             summary={summaryOf(f)} onDetails={() => setOpenFactor(f.key)} />
              ))}
            </fieldset>
          )}

          <label className="field">
            <span>Note</span>
            <textarea
              rows={3} maxLength={2000} value={form.note}
              placeholder={kind === "morning" ? "Anything on your mind?" : "What happened today?"}
              onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))}
            />
          </label>

          {error && <p className="error" role="alert">{error}</p>}

          <div className="actions">
            <button className="primary wide" disabled={!form.score || status === "saving"}>
              {status === "saving" ? (slow ? "Saving… server is waking up" : "Saving…")
                : status === "saved" ? "Saved"
                : existing ? "Save changes" : "Save check-in"}
            </button>
            {cheer && <p className="cheer" role="status">{cheer}</p>}
            {existing && <button type="button" className="link danger" onClick={remove}>Delete this check-in</button>}
          </div>
        </form>
      )}

      {sheetFactor && (
        <DetailSheet
          factor={sheetFactor}
          value={form.values[sheetFactor.key]}
          onValue={(v) => setValue(sheetFactor.key, v)}
          detail={form.details[sheetFactor.key]}
          onDetail={(d) => setDetail(sheetFactor, d)}
          onClose={() => setOpenFactor(null)}
        />
      )}

      <div ref={forecastRef}>
        {forecast && forecast.forecast.available && (
          <ForecastCard forecast={forecast.forecast} model={forecast.model} today={today} compact />
        )}
      </div>
    </main>
  );
}
