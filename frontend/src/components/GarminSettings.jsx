import { useEffect, useState } from "react";
import { api } from "../lib/api";

function ago(iso) {
  if (!iso) return "not yet";
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 2) return "just now";
  if (mins < 60) return `${mins} minutes ago`;
  const h = Math.round(mins / 60);
  return h < 36 ? `${h} hour${h === 1 ? "" : "s"} ago` : `${Math.round(h / 24)} days ago`;
}

export default function GarminSettings() {
  const [status, setStatus] = useState(null);
  const [step, setStep] = useState("idle"); // idle | form | mfa
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);

  const refresh = () => api.get("/garmin").then(setStatus).catch((e) => setError(e.message));
  useEffect(() => { refresh(); }, []);

  async function run(fn) {
    setBusy(true); setError(null); setNotice(null);
    try { await fn(); } catch (e) { setError(e.message); }
    setBusy(false);
  }

  const connect = (e) => { e.preventDefault(); run(async () => {
    const r = await api.post("/garmin/connect", { email, password });
    setPassword(""); // don't keep it in memory longer than needed
    if (r.status === "needs_mfa") { setStep("mfa"); return; }
    setStep("idle"); setNotice("Connected. Your last 30 days are importing in the background.");
    await refresh();
  }); };

  const submitCode = (e) => { e.preventDefault(); run(async () => {
    await api.post("/garmin/mfa", { code });
    setCode(""); setStep("idle"); setNotice("Connected. Your last 30 days are importing in the background.");
    await refresh();
  }); };

  const syncNow = () => run(async () => {
    const r = await api.post("/garmin/sync");
    setStatus(r);
    if (r.status === "connected" && !r.last_error) setNotice("Synced.");
  });

  const disconnect = () => {
    if (!window.confirm("Disconnect Garmin? Data already imported stays, and no new data will sync.")) return;
    run(async () => { await api.del("/garmin"); setStatus({ connected: false }); });
  };

  if (!status) return <p className="muted">Checking Garmin…</p>;

  const needsLogin = !status.connected || status.status === "reauth";

  return (
    <div className="garmin">
      {status.connected && status.status === "connected" && (
        <>
          <p>Connected. Last synced {ago(status.last_sync_at)}.</p>
          <p className="muted small">
            Sleep, HRV, resting heart rate, Body Battery, stress and steps sync every few hours.
            Garmin's sleep hours fill in your morning check-in; you can still change them.
          </p>
          {status.last_error && <p className="notice">{status.last_error}</p>}
          <div className="row">
            <button className="secondary" disabled={busy} onClick={syncNow}>{busy ? "Syncing…" : "Sync now"}</button>
            <button className="link" disabled={busy} onClick={disconnect}>Disconnect</button>
          </div>
        </>
      )}

      {needsLogin && step !== "mfa" && (
        <>
          {status.status === "reauth" && <p className="notice">Garmin needs you to sign in again to keep syncing.</p>}
          {step === "idle" ? (
            <>
              <p className="muted small">
                Pull sleep, HRV, resting heart rate, Body Battery, stress and steps from Garmin Connect so they
                can show up in your stats and insights.
              </p>
              <button className="secondary" onClick={() => setStep("form")}>
                {status.status === "reauth" ? "Sign in to Garmin" : "Connect Garmin"}
              </button>
            </>
          ) : (
            <form className="stack" onSubmit={connect}>
              <label className="field"><span>Garmin email</span>
                <input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
              </label>
              <label className="field"><span>Garmin password</span>
                <input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
              </label>
              <p className="muted small">
                Your password is used once to sign in and is never stored. This uses an unofficial connection to
                Garmin, so it can occasionally break when Garmin changes things.
              </p>
              <div className="row">
                <button className="primary" disabled={busy}>{busy ? "Signing in…" : "Connect"}</button>
                <button type="button" className="link" onClick={() => setStep("idle")}>Cancel</button>
              </div>
            </form>
          )}
        </>
      )}

      {step === "mfa" && (
        <form className="stack" onSubmit={submitCode}>
          <p>Garmin sent you a verification code. Enter it within 5 minutes.</p>
          <label className="field"><span>Verification code</span>
            <input inputMode="numeric" autoComplete="one-time-code" required value={code} onChange={(e) => setCode(e.target.value)} />
          </label>
          <div className="row">
            <button className="primary" disabled={busy}>{busy ? "Checking…" : "Verify"}</button>
            <button type="button" className="link" onClick={() => { setStep("form"); setCode(""); }}>Start over</button>
          </div>
        </form>
      )}

      {error && <p className="error" role="alert">{error}</p>}
      {notice && <p className="notice" role="status">{notice}</p>}
    </div>
  );
}
