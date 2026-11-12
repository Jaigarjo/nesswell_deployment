import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { addDays, formatDay } from "../lib/dates";

const PAGE_DAYS = 60;

function groupByDay(rows) {
  const days = new Map();
  for (const r of rows) {
    if (!days.has(r.day)) days.set(r.day, {});
    days.get(r.day)[r.kind] = r;
  }
  return [...days.entries()].sort((a, b) => (a[0] < b[0] ? 1 : -1));
}

function Bar({ entry, kind }) {
  return (
    <div className={`bar ${kind}`}>
      <span className="bar-track">
        {entry && <span className="bar-fill" style={{ width: `${entry.score * 10}%` }} />}
      </span>
      <span className="bar-num">{entry ? entry.score : "–"}</span>
    </div>
  );
}

export default function History({ me, onOpen }) {
  const [rows, setRows] = useState([]);
  const [oldest, setOldest] = useState(null); // earliest day loaded so far
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  async function load(end) {
    setLoading(true); setError(null);
    const start = addDays(end, -(PAGE_DAYS - 1));
    try {
      const page = await api.get(`/entries?start=${start}&end=${end}`);
      setRows((prev) => [...prev, ...page]);
      setOldest(start);
    } catch (e) { setError(e.message); }
    setLoading(false);
  }

  useEffect(() => { load(me.today); }, [me.today]); // eslint-disable-line react-hooks/exhaustive-deps

  const days = groupByDay(rows);

  return (
    <main className="screen history">
      <h1 className="display small">History</h1>
      <div className="legend" aria-hidden="true">
        <span className="key morning">Morning</span><span className="key evening">Evening</span>
      </div>

      {error && <p className="error" role="alert">{error}</p>}

      {!loading && days.length === 0 && !error && (
        <div className="empty">
          <p>No check-ins in the last {PAGE_DAYS} days.</p>
          <button className="primary" onClick={() => onOpen(me.today, null)}>Do today's check-in</button>
        </div>
      )}

      <ol className="days">
        {days.map(([day, e]) => (
          <li key={day}>
            <button className="day-row" onClick={() => onOpen(day, e.morning ? "morning" : "evening")}>
              <span className="day-name">{formatDay(day, me.today)}</span>
              <span className="bars">
                <Bar entry={e.morning} kind="morning" />
                <Bar entry={e.evening} kind="evening" />
              </span>
              {(e.evening?.note || e.morning?.note) && (
                <span className="day-note">{e.evening?.note || e.morning?.note}</span>
              )}
            </button>
          </li>
        ))}
      </ol>

      {loading && <p className="muted pad">Loading…</p>}
      {!loading && oldest && days.length > 0 && (
        <button className="secondary wide" onClick={() => load(addDays(oldest, -1))}>
          Show {PAGE_DAYS} days before {formatDay(oldest, me.today)}
        </button>
      )}
    </main>
  );
}
