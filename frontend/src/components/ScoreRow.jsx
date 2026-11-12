export default function ScoreRow({ value, onChange, label }) {
  return (
    <div className="scores" role="radiogroup" aria-label={label}>
      {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
        <button
          key={n}
          type="button"
          role="radio"
          aria-checked={value === n}
          className={value === n ? "score picked" : "score"}
          onClick={() => onChange(n)}
        >
          {n}
        </button>
      ))}
      <div className="score-ends" aria-hidden="true"><span>Awful</span><span>Great</span></div>
    </div>
  );
}
