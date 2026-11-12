import { useEffect, useState } from "react";

const KEY = "theme"; // "system" | "light" | "dark", remembered per device
const media = () => window.matchMedia("(prefers-color-scheme: dark)");

function readPref() {
  try { return localStorage.getItem(KEY) || "system"; } catch { return "system"; }
}

/** Returns [effective theme ("light" | "dark"), preference, setPreference]. Follows the phone unless overridden. */
export function useTheme() {
  const [pref, setPrefState] = useState(readPref);
  const [systemDark, setSystemDark] = useState(() => media().matches);

  useEffect(() => {
    const m = media();
    const onChange = (e) => setSystemDark(e.matches);
    m.addEventListener("change", onChange);
    return () => m.removeEventListener("change", onChange);
  }, []);

  const theme = pref === "system" ? (systemDark ? "dark" : "light") : pref;

  // Match the phone's status bar to the page.
  useEffect(() => {
    document.querySelectorAll('meta[name="theme-color"]').forEach((m) => m.remove());
    const meta = document.createElement("meta");
    meta.name = "theme-color";
    meta.content = theme === "dark" ? "#000000" : "#ffffff";
    document.head.appendChild(meta);
    document.documentElement.style.colorScheme = theme;
  }, [theme]);

  const setPref = (p) => {
    setPrefState(p);
    try { localStorage.setItem(KEY, p); } catch { /* private mode: still works for this session */ }
  };
  return [theme, pref, setPref];
}
