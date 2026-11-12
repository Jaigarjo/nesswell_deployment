import { linear, signed } from "./scale";

const W = 340, L = 8, R = 8;
const avg = (g) => `${g.mean.toFixed(1)} over ${g.n} ${g.n === 1 ? "day" : "days"}`;

function Row({ f, x, minGroup, dayWords }) {
  const H = 26, cy = 13;
  return (
    <li className={f.enough ? "factor-row" : "factor-row faint"}>
      <div className="factor-head">
        <span className="factor-name">{f.label}</span>
        <span className="factor-diff">{f.enough ? signed(f.diff) : "Not enough yet"}</span>
      </div>
      {f.enough && (
        <svg viewBox={`0 0 ${W} ${H}`} aria-hidden="true">
          <line className="zero" x1={x(0)} x2={x(0)} y1={0} y2={H} />
          {f.ci_low != null && <line className="whisker" x1={x(f.ci_low)} x2={x(f.ci_high)} y1={cy} y2={cy} />}
          <circle className={f.clear ? "point" : "point hollow"} cx={x(f.diff)} cy={cy} r="6" />
        </svg>
      )}
      <p className="factor-detail">
        {f.value_type === "bool"
          ? <>{dayWords[0]}: {avg(f.high)}. {dayWords[1]}: {avg(f.low)}.</>
          : <>{f.high_label}: {avg(f.high)}. {f.low_label}: {avg(f.low)}.</>}
        {!f.enough && <> Needs {minGroup} days on each side.</>}
      </p>
    </li>
  );
}

export default function FactorChart({ factors, minGroup, caption, dayWords = ["Days you did", "Days you didn't"] }) {
  if (!factors.length) return <p className="muted pad">Log some factors (sleep, workouts and so on) to compare them here.</p>;
  const reach = Math.max(2, ...factors.filter((f) => f.enough).map((f) => Math.ceil(Math.max(Math.abs(f.ci_low ?? 0), Math.abs(f.ci_high ?? 0)))));
  const x = linear(-reach, reach, L, W - R);
  return (
    <figure className="chart">
      <div className="factor-scale" aria-hidden="true"><span>−{reach} lower</span><span>0</span><span>+{reach} higher</span></div>
      <ul className="factor-list">
        {factors.map((f) => <Row key={f.key} f={f} x={x} minGroup={minGroup} dayWords={dayWords} />)}
      </ul>
      <figcaption>
        {caption || "How much higher or lower your mood was on those days."} A filled dot means the difference
        holds up (its 95% interval doesn't cross zero). These are patterns, not proof of cause.
      </figcaption>
    </figure>
  );
}
