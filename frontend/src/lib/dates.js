// All days are "YYYY-MM-DD" strings, matching the API.

export function addDays(day, n) {
  const d = new Date(day + "T12:00:00"); // noon avoids DST edge cases
  d.setDate(d.getDate() + n);
  const pad = (x) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function formatDay(day, today) {
  if (day === today) return "Today";
  if (day === addDays(today, -1)) return "Yesterday";
  const d = new Date(day + "T12:00:00");
  const sameYear = day.slice(0, 4) === today.slice(0, 4);
  return d.toLocaleDateString(undefined, {
    weekday: "short", day: "numeric", month: "short", ...(sameYear ? {} : { year: "numeric" }),
  });
}

// Which palette the app chrome uses right now (the check-in screen follows the selected kind).
export function currentMoment() {
  const h = new Date().getHours();
  return h >= 4 && h < 15 ? "morning" : "evening";
}

export const deviceTimezone = () => Intl.DateTimeFormat().resolvedOptions().timeZone;
