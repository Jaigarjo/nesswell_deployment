// One factor in the check-in: bool = toggle, scale = 1-5, number = stepper.
// Long press (or the ⋯ button) opens its detail sheet. `bare` renders just the
// control, for use inside that sheet.
import { useLongPress } from "../lib/longpress";

function More({ label, onDetails, active }) {
  return (
    <button type="button" className={active ? "more active" : "more"}
            aria-label={`More about ${label.toLowerCase()}`} onClick={onDetails}>
      <span aria-hidden="true">⋯</span>
    </button>
  );
}

function Summary({ text }) {
  return text ? <span className="factor-summary">{text}</span> : null;
}

export default function FactorInput({ factor, value, onChange, hint, summary, onDetails, bare = false }) {
  const { key, label, value_type, min_value: min, max_value: max } = factor;
  const press = useLongPress(onDetails || (() => {}));
  const pressable = bare || !onDetails ? {} : press;

  if (value_type === "bool") {
    const on = value === 1;
    const toggle = (
      <button type="button" className="chip-main" aria-pressed={on} onClick={() => onChange(on ? 0 : 1)}>
        <span>{label}</span>
        {!bare && <Summary text={summary} />}
      </button>
    );
    if (bare) return <div className={on ? "chip on solo" : "chip solo"}>{toggle}</div>;
    return (
      <div className={on ? "chip on" : "chip"} {...pressable}>
        {toggle}
        <More label={label} onDetails={onDetails} active={Boolean(summary)} />
      </div>
    );
  }

  let control;
  if (value_type === "scale") {
    const opts = [];
    for (let n = min ?? 1; n <= (max ?? 5); n++) opts.push(n);
    const { low_label: lo, high_label: hi } = factor;
    control = (
      <div className="scale-wrap">
        <div className="segments" role="radiogroup" aria-labelledby={`l-${key}`}
             aria-describedby={lo || hi ? `e-${key}` : undefined}>
          {opts.map((n) => (
            <button key={n} type="button" role="radio" aria-checked={value === n}
                    className={value === n ? "seg picked" : "seg"}
                    onClick={() => onChange(value === n ? undefined : n)}>{n}</button>
          ))}
        </div>
        {(lo || hi) && (
          <div className="scale-ends" id={`e-${key}`}>
            <span>{lo ? `1 ${lo}` : ""}</span><span>{hi ? `${max ?? 5} ${hi}` : ""}</span>
          </div>
        )}
      </div>
    );
  } else {
    // number: stepper in half steps, first tap starts at a sensible default
    const step = 0.5;
    const start = key === "sleep_hours" ? 7 : (min ?? 0);
    const clamp = (v) => Math.min(max ?? Infinity, Math.max(min ?? -Infinity, v));
    const bump = (d) => onChange(clamp(value === undefined ? start : value + d));
    control = (
      <div className="stepper">
        <button type="button" aria-label={`Less ${label.toLowerCase()}`} onClick={() => bump(-step)}>−</button>
        <output aria-live="polite">{value === undefined ? "–" : value}</output>
        <button type="button" aria-label={`More ${label.toLowerCase()}`} onClick={() => bump(step)}>+</button>
      </div>
    );
  }

  if (bare) return <div className={`factor bare ${value_type}`}>{control}</div>;

  // Scales: label and ⋯ on top, full-width squares below. Numbers: one line.
  return (
    <div className={`factor ${value_type}`} {...pressable}>
      <span className="factor-label" id={`l-${key}`}>
        {label}
        {hint && <span className="factor-hint">{hint}</span>}
        <Summary text={summary} />
      </span>
      {control}
      <More label={label} onDetails={onDetails} active={Boolean(summary)} />
    </div>
  );
}
