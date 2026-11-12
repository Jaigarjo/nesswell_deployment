// The early-days layer: streaks, progress toward insights, and general research tips.

const MILESTONE_TEXT = {
  1: "Your first check-in. Welcome to NessWell.",
  3: "3 days logged. A good start.",
  7: "One week of check-ins.",
  14: "Two weeks in.",
  30: "30 days logged. Your patterns are taking shape.",
  60: "60 days logged.",
  100: "100 days logged.",
  200: "200 days logged.",
  365: "A full year of check-ins.",
};

/** One short line after saving: milestone, streak and the best behaviour streak. */
export function savedLine(p) {
  if (!p) return null;
  const parts = [];
  if (p.milestone && MILESTONE_TEXT[p.milestone]) parts.push(MILESTONE_TEXT[p.milestone]);
  else if (p.streak > 1) parts.push(`${p.streak}-day streak.`);
  if (p.behaviour_streaks?.length) parts.push(`${p.behaviour_streaks[0].text}.`);
  return parts.join(" ") || null;
}

function unlockText(u) {
  if (u.value_type === "bool") {
    return `${Math.min(u.have.with, u.needed)} of ${u.needed} days with, ${Math.min(u.have.without, u.needed)} of ${u.needed} without`;
  }
  return `${Math.min(u.have.days, u.needed * 2)} of ${u.needed * 2} days logged`;
}

function Bar({ value, max }) {
  return (
    <span className="unlock-bar" aria-hidden="true">
      <span style={{ width: `${Math.min(100, (value / max) * 100)}%` }} />
    </span>
  );
}

export function ProgressSection({ p }) {
  const pending = p.unlocks.filter((u) => !u.enough && (u.source === "manual" || u.have.days || u.have.with || u.have.without));
  const forecastReady = p.forecast.have >= p.forecast.needed;
  if (!pending.length && forecastReady && !p.behaviour_streaks.length && p.streak < 2) return null;

  return (
    <section className="progress" aria-label="Your progress">
      <h2>Getting to know you</h2>
      <ul className="streaks">
        <li><span className="num">{p.days_logged}</span><span>days logged</span></li>
        <li><span className="num">{p.streak}</span><span>day streak</span></li>
      </ul>
      {p.behaviour_streaks.length > 0 && (
        <ul className="behaviour">
          {p.behaviour_streaks.map((s) => <li key={s.key}>{s.text}</li>)}
        </ul>
      )}

      {(pending.length > 0 || !forecastReady) && (
        <>
          <p className="muted small">
            Personal insights unlock as you log. Each comparison needs at least {p.unlocks[0]?.needed ?? 5} days on each side.
          </p>
          <ul className="unlocks">
            {!forecastReady && (
              <li>
                <span className="unlock-name">Tomorrow's forecast</span>
                <span className="muted small">{p.forecast.have} of {p.forecast.needed} mornings after an evening check-in</span>
                <Bar value={p.forecast.have} max={p.forecast.needed} />
              </li>
            )}
            {pending.map((u) => {
              const done = u.value_type === "bool"
                ? Math.min(u.have.with, u.needed) + Math.min(u.have.without, u.needed)
                : Math.min(u.have.days, u.needed * 2);
              return (
                <li key={u.key}>
                  <span className="unlock-name">{u.label}</span>
                  <span className="muted small">{unlockText(u)}</span>
                  <Bar value={done} max={u.needed * 2} />
                </li>
              );
            })}
          </ul>
        </>
      )}
    </section>
  );
}

export function GeneralTips({ tips }) {
  if (!tips?.length) return null;
  return (
    <section className="tips" aria-label="General tips">
      <h2>General tips</h2>
      <p className="muted small">From research, not your data. Each one retires once you've logged enough to judge it for yourself.</p>
      <ol className="tip-list">
        {tips.map((t) => (
          <li key={t.key} className="tip">
            <h3>{t.action}</h3>
            <p>{t.why}</p>
            <a className="tip-source" href={t.url} target="_blank" rel="noopener noreferrer">{t.source}</a>
          </li>
        ))}
      </ol>
    </section>
  );
}
