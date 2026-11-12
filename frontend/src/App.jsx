import { useEffect, useState } from "react";
import { supabase } from "./lib/supabase";
import { api, warmUp } from "./lib/api";
import { deviceTimezone } from "./lib/dates";
import { useTheme } from "./lib/theme";
import Login from "./screens/Login";
import CheckIn from "./screens/CheckIn";
import History from "./screens/History";
import Settings from "./screens/Settings";
import Stats from "./screens/Stats";
import Insights from "./screens/Insights";

// A reminder notification opens "/?kind=evening&day=2026-09-28".
// Pure on purpose: React may call it twice, so clearing the URL happens in an effect.
function readTarget() {
  const q = new URLSearchParams(window.location.search);
  const kind = q.get("kind");
  const day = q.get("day");
  return {
    kind: kind === "morning" || kind === "evening" ? kind : null,
    day: /^\d{4}-\d{2}-\d{2}$/.test(day || "") ? day : null,
  };
}

export default function App() {
  const [session, setSession] = useState(undefined); // undefined = still checking
  const [me, setMe] = useState(null);
  const [factors, setFactors] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [tab, setTab] = useState("checkin");
  const [target, setTarget] = useState(readTarget);
  const [theme, themePref, setThemePref] = useTheme();
  const [theming, setTheming] = useState(false);

  // Crossfade only while the palette changes.
  useEffect(() => {
    setTheming(true);
    const t = setTimeout(() => setTheming(false), 500);
    return () => clearTimeout(t);
  }, [theme]);

  // Tidy the address bar once the link has been read.
  useEffect(() => {
    if (window.location.search) window.history.replaceState(null, "", "/");
  }, []);

  useEffect(() => {
    warmUp();
    supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data } = supabase.auth.onAuthStateChange((_e, s) => setSession(s));
    return () => data.subscription.unsubscribe();
  }, []);

  const userId = session?.user?.id;
  useEffect(() => {
    if (!userId) { setMe(null); setFactors(null); return; }
    let cancelled = false;
    (async () => {
      try {
        setLoadError(null);
        let profile = await api.get("/me");
        // New accounts start on UTC; adopt this device's timezone once.
        const tz = deviceTimezone();
        if (profile.timezone === "UTC" && tz && tz !== "UTC") {
          profile = await api.patch("/me", { timezone: tz });
        }
        const f = await api.get("/factors");
        if (!cancelled) { setMe(profile); setFactors(f); }
      } catch (e) {
        if (!cancelled) setLoadError(e.message);
      }
    })();
    return () => { cancelled = true; };
  }, [userId]);

  if (session === undefined) return <div className="app" data-theme={theme} />;
  if (!session) return <div className="app" data-theme={theme}><Login /></div>;

  if (loadError) {
    return (
      <div className="app" data-theme={theme}>
        <main className="screen centered">
          <p className="error">{loadError}</p>
          <button className="primary" onClick={() => window.location.reload()}>Try again</button>
        </main>
      </div>
    );
  }
  if (!me || !factors) {
    return (
      <div className="app" data-theme={theme}>
        <main className="screen centered"><p className="muted">Loading your days…</p></main>
      </div>
    );
  }

  const openDay = (day, kind) => { setTarget({ day, kind }); setTab("checkin"); };

  return (
    <div className="app" data-theme={theme} data-theming={theming || undefined}>
      {tab === "checkin" && (
        <CheckIn me={me} factors={factors} target={target} />
      )}
      {tab === "history" && <History me={me} onOpen={openDay} />}
      {tab === "stats" && <Stats me={me} onOpen={openDay} />}
      {tab === "insights" && <Insights me={me} />}
      {tab === "settings" && <Settings me={me} onProfile={setMe} themePref={themePref} onThemePref={setThemePref} />}

      <nav className="tabs" aria-label="Main">
        {[["checkin", "Check in"], ["history", "History"], ["stats", "Stats"], ["insights", "Insights"], ["settings", "Settings"]].map(([id, label]) => (
          <button
            key={id}
            className={tab === id ? "tab active" : "tab"}
            aria-current={tab === id ? "page" : undefined}
            onClick={() => {
              if (id === "checkin") setTarget({ day: null, kind: null });
              setTab(id);
            }}
          >
            {label}
          </button>
        ))}
      </nav>
    </div>
  );
}
