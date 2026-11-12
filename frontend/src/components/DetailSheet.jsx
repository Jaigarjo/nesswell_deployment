import { useEffect, useRef } from "react";
import FactorInput from "./FactorInput";

function NumberField({ f, value, onChange }) {
  const step = f.step ?? 1;
  const start = f.key === "minutes" ? 30 : f.key === "hours" ? 8 : f.min ?? 0;
  const clamp = (v) => Math.round(Math.min(f.max, Math.max(f.min, v)) * 100) / 100;
  const bump = (d) => onChange(clamp(value === undefined ? start : value + d));
  return (
    <div className="stepper">
      <button type="button" aria-label={`Less: ${f.label}`} onClick={() => bump(-step)}>−</button>
      <output aria-live="polite">{value === undefined ? "–" : value}{value !== undefined && f.unit ? <small> {f.unit}</small> : null}</output>
      <button type="button" aria-label={`More: ${f.label}`} onClick={() => bump(step)}>+</button>
    </div>
  );
}

function Options({ f, value, onChange, multiple }) {
  const selected = multiple ? value || [] : value;
  const isOn = (o) => (multiple ? selected.includes(o) : selected === o);
  const toggle = (o) => {
    if (!multiple) return onChange(selected === o ? undefined : o);
    onChange(isOn(o) ? selected.filter((x) => x !== o) : [...selected, o]);
  };
  return (
    <div className="options" role={multiple ? "group" : "radiogroup"} aria-label={f.label}>
      {f.options.map((o) => (
        <button key={o} type="button" role={multiple ? "checkbox" : "radio"} aria-checked={isOn(o)}
                className={isOn(o) ? "option on" : "option"} onClick={() => toggle(o)}>{o}</button>
      ))}
    </div>
  );
}

function Field({ f, value, onChange }) {
  return (
    <div className="detail-field">
      <span className="detail-label">{f.label}</span>
      {f.type === "number" && <NumberField f={f} value={value} onChange={onChange} />}
      {f.type === "choice" && <Options f={f} value={value} onChange={onChange} />}
      {f.type === "multi" && <Options f={f} value={value} onChange={onChange} multiple />}
      {f.type === "time" && (
        <input type="time" aria-label={f.label} value={value || ""} onChange={(e) => onChange(e.target.value || undefined)} />
      )}
    </div>
  );
}

export default function DetailSheet({ factor, value, onValue, detail, onDetail, onClose }) {
  const sheet = useRef(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  const d = detail || { note: "", data: {} };
  const setField = (k, v) => onDetail({ ...d, data: { ...d.data, [k]: v } });

  // Runs once per opening: focus the sheet, Escape closes, page behind doesn't scroll.
  useEffect(() => {
    sheet.current?.focus();
    const onKey = (e) => { if (e.key === "Escape") closeRef.current(); };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = prev; };
  }, []);

  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <div className="sheet" role="dialog" aria-modal="true" aria-labelledby="sheet-title"
           ref={sheet} tabIndex={-1} onClick={(e) => e.stopPropagation()}>
        <header className="sheet-head">
          <h2 id="sheet-title">{factor.label}</h2>
          <button type="button" className="primary sheet-done" onClick={onClose}>Done</button>
        </header>

        <div className="sheet-main">
          <FactorInput factor={factor} value={value} onChange={onValue} bare />
        </div>

        {(factor.detail_schema || []).map((f) => (
          <Field key={f.key} f={f} value={d.data?.[f.key]} onChange={(v) => setField(f.key, v)} />
        ))}

        <label className="field">
          <span>Anything else</span>
          <textarea rows={3} maxLength={1000} value={d.note || ""}
                    placeholder="Context, what happened, how it felt"
                    onChange={(e) => onDetail({ ...d, note: e.target.value })} />
        </label>
        <p className="muted small sheet-foot">Everything here is optional and saves with your check-in.</p>
      </div>
    </div>
  );
}
