// Helpers for the optional detail layer on each factor.

const filled = (v) => v !== undefined && v !== null && v !== "" && !(Array.isArray(v) && v.length === 0);

export function hasData(detail) {
  return Boolean(detail && Object.values(detail.data || {}).some(filled));
}

export function isEmpty(detail) {
  return !detail || (!(detail.note || "").trim() && !hasData(detail));
}

/** One short line, e.g. "Run, 35 min, Hard" or "3 drinks, Wine, note". */
export function summarize(schema, detail) {
  if (isEmpty(detail)) return null;
  const parts = [];
  for (const f of schema || []) {
    const v = detail.data?.[f.key];
    if (!filled(v)) continue;
    if (f.type === "number") parts.push(f.unit ? `${v} ${f.unit}` : `${v} ${f.label.toLowerCase()}`);
    else if (f.type === "multi") parts.push(v.length > 2 ? `${v.slice(0, 2).join(", ")} +${v.length - 2}` : v.join(", "));
    else if (f.type === "time") parts.push(`${f.label.toLowerCase()} ${v}`);
    else parts.push(v);
  }
  const shown = parts.slice(0, 3);
  if ((detail.note || "").trim()) shown.push("note");
  const text = shown.join(", ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** Only non-empty details, with cleared fields removed, ready to send. */
export function cleanDetails(details, keys) {
  const out = {};
  for (const k of keys) {
    const d = details[k];
    if (isEmpty(d)) continue;
    const data = Object.fromEntries(Object.entries(d.data || {}).filter(([, v]) => filled(v)));
    out[k] = { note: (d.note || "").trim() || null, data };
  }
  return out;
}
