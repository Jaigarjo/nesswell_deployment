import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { DEMO, supabase } from "../lib/supabase";
import { deviceTimezone } from "../lib/dates";
import { disablePush, enablePush, pushStatus } from "../lib/push";
import GarminSettings from "../components/GarminSettings";

const hhmm = (t) => (t ? t.slice(0, 5) : "");
const DEFAULTS = { morning: "08:00", evening: "21:30" };

function ReminderRow({ kind, value, onSave }) {
  const on = Boolean(value);
  const label = kind === "morning" ? "Morning reminder" : "Evening reminder";
  return (
    <div className="reminder">
      <label className="switch">
        <input type="checkbox" checked={on} onChange={() => onSave(on ? null : DEFAULTS[kind])} />
        <span>{label}</span>
      </label>
      {on && (
        <input
          type="time" aria-label={`${label} time`} value={hhmm(value)}
          onChange={(e) => e.target.value && onSave(e.target.value)}
        />
      )}
    </div>
  );
}

export default function Settings({ me, onProfile, themePref, onThemePref }) {
  const [push, setPush] = useState("checking");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const tz = deviceTimezone();

  useEffect(() => { pushStatus().then(setPush).catch(() => setPush("unsupported")); }, []);

  async function update(patch) {
    setError(null);
    try { onProfile(await api.patch("/me", patch)); }
    catch (e) { setError(e.message); }
  }

  async function togglePush() {
    setBusy(true); setError(null); setNotice(null);
    try {
      if (push === "on") { await disablePush(); setPush("off"); }
      else { await enablePush(); setPush("on"); }
    } catch (e) { setError(e.message); setPush(await pushStatus().catch(() => "unsupported")); }
    setBusy(false);
  }

  async function testPush() {
    setError(null); setNotice(null);
    try { await api.post("/push/test"); setNotice("Test notification sent."); }
    catch (e) { setError(e.message); }
  }

  const remindersSet = me.morning_reminder || me.evening_reminder;

  return (
    <main className="screen settings">
      <h1 className="display small">Settings</h1>

      <section>
        <h2>Appearance</h2>
        <div className="segmented" role="radiogroup" aria-label="Appearance">
          {[["system", "Match phone"], ["light", "Light"], ["dark", "Dark"]].map(([id, label]) => (
            <button key={id} role="radio" aria-checked={themePref === id}
                    className={themePref === id ? "active" : ""} onClick={() => onThemePref(id)}>{label}</button>
          ))}
        </div>
      </section>

      <section>
        <h2>Reminders</h2>
        <ReminderRow kind="morning" value={me.morning_reminder} onSave={(v) => update({ morning_reminder: v })} />
        <ReminderRow kind="evening" value={me.evening_reminder} onSave={(v) => update({ evening_reminder: v })} />
        <p className="muted small">You won't get a reminder if you've already checked in.</p>

        {push === "needs-install" && (
          <p className="notice">
            On iPhone, notifications only work from the Home Screen app. Tap Share, then Add to Home Screen, and open NessWell from there.
          </p>
        )}
        {push === "unsupported" && <p className="notice">This browser can't show notifications.</p>}
        {push === "denied" && (
          <p className="notice">Notifications are blocked for this site. Allow them in your browser settings, then come back here.</p>
        )}
        {(push === "on" || push === "off") && (
          <div className="row">
            <button className={push === "on" ? "secondary" : "primary"} disabled={busy} onClick={togglePush}>
              {busy ? "One moment…" : push === "on" ? "Turn off on this device" : "Turn on notifications"}
            </button>
            {push === "on" && <button className="link" onClick={testPush}>Send a test</button>}
          </div>
        )}
        {push === "off" && remindersSet && (
          <p className="muted small">Reminders are set, but this device won't get them until you turn notifications on.</p>
        )}
      </section>

      <section>
        <h2>Garmin</h2>
        <GarminSettings />
      </section>

      <section>
        <h2>Time zone</h2>
        <p>Your days are counted in <strong>{me.timezone.replace(/_/g, " ")}</strong>. Anything logged before 4am counts toward the day before.</p>
        {tz && tz !== me.timezone && (
          <button className="secondary" onClick={() => update({ timezone: tz })}>
            Switch to {tz.replace(/_/g, " ")}
          </button>
        )}
      </section>

      {error && <p className="error" role="alert">{error}</p>}
      {notice && <p className="notice" role="status">{notice}</p>}

      <section>
        {DEMO ? (
          <p className="muted small">Local demo: everything stays on this computer. Run the demo script with --reset for fresh sample data.</p>
        ) : (
          <button className="link" onClick={() => supabase.auth.signOut()}>Sign out</button>
        )}
      </section>
    </main>
  );
}
