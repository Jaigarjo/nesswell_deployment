import { signed } from "./charts/scale";
import { addDays, formatDay } from "../lib/dates";

function heading(forDay, today) {
  if (forDay === addDays(today, 1)) return "Tomorrow morning";
  if (forDay === today) return "This morning";
  return `${formatDay(forDay, today)} morning`;
}

export function ModelNote({ model }) {
  if (!model?.ready) return null;
  return (
    <p className="muted small">
      Tested on {model.n_train} past mornings: off by {model.mae_model.toFixed(1)} points on average.
      Just guessing your usual would be off by {model.mae_baseline.toFixed(1)}.
    </p>
  );
}

export default function ForecastCard({ forecast: f, model, today, compact = false }) {
  if (!f) return null;
  if (!f.available) {
    return (
      <section className="forecast empty-forecast" aria-label="Tomorrow's forecast">
        <h2>Tomorrow morning</h2>
        <p className="muted">
          {f.reason === "no_evening"
            ? "Do tonight's check-in to see a forecast for tomorrow morning."
            : `Forecasts start once you have ${f.needed} mornings that follow an evening check-in. You have ${f.n_train}.`}
        </p>
      </section>
    );
  }
  return (
    <section className="forecast" aria-label="Forecast">
      <h2>{heading(f.for_day, today)}</h2>
      <p className="forecast-value">
        <span className="num">{f.value.toFixed(1)}</span>
        <span className="range">likely between {f.low.toFixed(1)} and {f.high.toFixed(1)}</span>
      </p>
      {f.model_used ? (
        f.contributions.length > 0 && (
          <ul className="contribs" aria-label="What's moving the forecast">
            {f.contributions.map((c) => (
              <li key={c.text}>
                <span>{c.text}</span>
                <span className={c.points > 0 ? "up" : "down"}>{signed(c.points)}</span>
              </li>
            ))}
          </ul>
        )
      ) : (
        <p className="muted">Close to your usual {f.usual.toFixed(1)}. Nothing you've logged predicts your mornings reliably yet.</p>
      )}
      {!compact && <ModelNote model={model} />}
    </section>
  );
}
