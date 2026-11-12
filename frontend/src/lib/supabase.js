import { createClient } from "@supabase/supabase-js";

export const DEMO = import.meta.env.VITE_DEMO_MODE === "1";

// Local demo: no accounts. A stand-in that always reports a signed-in demo user;
// the demo API ignores the token anyway.
const demoSession = {
  access_token: "demo",
  user: { id: "00000000-0000-4000-8000-00000000d3e0", email: "demo@nesswell.local" },
};
const demoAuth = {
  getSession: async () => ({ data: { session: demoSession } }),
  onAuthStateChange: () => ({ data: { subscription: { unsubscribe() {} } } }),
  signOut: async () => { window.alert("This is the local demo, so there's no account to sign out of."); return {}; },
  signInWithPassword: async () => ({ data: { session: demoSession } }),
  signUp: async () => ({ data: { session: demoSession } }),
  signInWithOAuth: async () => ({}),
};

export const supabase = DEMO
  ? { auth: demoAuth }
  : createClient(import.meta.env.VITE_SUPABASE_URL, import.meta.env.VITE_SUPABASE_ANON_KEY);
