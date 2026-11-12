// Tiny helpers so the charts don't need a chart library.
export const linear = (d0, d1, r0, r1) => (v) => r0 + ((v - d0) / (d1 - d0 || 1)) * (r1 - r0);
export const toTime = (day) => new Date(day + "T12:00:00").getTime();
export const shortDate = (day) =>
  new Date(day + "T12:00:00").toLocaleDateString(undefined, { day: "numeric", month: "short" });
export const signed = (x) => (x > 0 ? `+${x.toFixed(1)}` : x.toFixed(1)).replace("-", "−");
