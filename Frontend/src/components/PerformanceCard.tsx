import { COLORS } from "../config";
import "./PerformanceCard.css";

export interface PerformanceData {
  river_id: string;
  river_name: string;
  display_unit: string;
  accuracy_90h: number;
  overall_accuracy_pct: number;
  r2: number;
  mae: number;
  holdout_days: number;
  daily_accuracy: { day: number; accuracy_pct: number }[];
}

function AccuracyBar({ pct, label }: { pct: number; label: string }) {
  const color = pct >= 90 ? COLORS.green : pct >= 75 ? COLORS.blue : COLORS.orange;
  return (
    <div className="perf__bar-row">
      <span className="perf__bar-label">{label}</span>
      <div className="perf__bar-track">
        <div
          className="perf__bar-fill"
          style={{ width: `${Math.round(pct)}%`, backgroundColor: color }}
        />
      </div>
      <span className="perf__bar-pct" style={{ color }}>
        {pct.toFixed(0)}%
      </span>
    </div>
  );
}

interface Props {
  data: PerformanceData;
}

export default function PerformanceCard({ data }: Props) {
  const horizonLabel =
    data.accuracy_90h >= 48
      ? `${(data.accuracy_90h / 24).toFixed(1)} days`
      : `${data.accuracy_90h} hrs`;

  return (
    <div className="perf">
      <div className="perf__headline">
        <div>
          <div className="perf__horizon-num">{horizonLabel}</div>
          <div className="perf__horizon-label">≥90% accurate forecast horizon</div>
        </div>
        <div className="perf__stats-box">
          <div className="perf__stat">
            <div className="perf__stat-value">{data.overall_accuracy_pct}%</div>
            <div className="perf__stat-label">Overall</div>
          </div>
          <div className="perf__stat-divider" />
          <div className="perf__stat">
            <div className="perf__stat-value">{data.r2}</div>
            <div className="perf__stat-label">R²</div>
          </div>
          <div className="perf__stat-divider" />
          <div className="perf__stat">
            <div className="perf__stat-value">{data.mae}</div>
            <div className="perf__stat-label">MAE {data.display_unit}</div>
          </div>
        </div>
      </div>

      <div className="perf__divider" />

      <div className="perf__section-label">Accuracy — last {data.holdout_days} days</div>
      {data.daily_accuracy.map(({ day, accuracy_pct }) => (
        <AccuracyBar key={day} pct={accuracy_pct} label={`Day ${day}`} />
      ))}

      <div className="perf__footnote">
        Accuracy = predictions within 10% of observed flow
      </div>
    </div>
  );
}
