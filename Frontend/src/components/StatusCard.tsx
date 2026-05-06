import { COLORS, STATUS_COLOR, STATUS_EMOJI } from "../config";
import "./StatusCard.css";

interface StatusData {
  river: string;
  current_cfs: number;
  display_unit: string;
  status: string;
  runnable: boolean;
  sweet_spot: boolean;
  updated_at: string;
  range: {
    runnable_min: number;
    runnable_max: number;
    sweet_min: number;
    sweet_max: number;
  };
}

interface Props {
  data: StatusData | null;
  loading: boolean;
}

export default function StatusCard({ data, loading }: Props) {
  if (loading && !data) {
    return (
      <div className="status-card status-card--loading">
        <div className="spinner" />
        <span className="status-card__loading-text">Loading river conditions...</span>
      </div>
    );
  }

  if (!data) return null;

  const color = STATUS_COLOR[data.status] ?? COLORS.textMuted;
  const emoji = STATUS_EMOJI[data.status] ?? "•";
  const isIn = data.runnable;
  const unit = data.display_unit ?? "CFS";
  const updatedTime = new Date(data.updated_at).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div className="status-card">
      <div className="status-card__row">
        <div className="status-card__badge" style={{ borderColor: color }}>
          <span className="status-card__badge-text" style={{ color }}>
            {isIn ? "IT'S IN!" : "NOT IN"}
          </span>
          <span className="status-card__emoji">{emoji}</span>
        </div>

        <div className="status-card__right">
          <div className="status-card__cfs">
            <span className="status-card__cfs-value" style={{ color }}>
              {data.current_cfs}
            </span>
            <span className="status-card__cfs-unit"> {unit}</span>
          </div>
          <div className="status-card__status-label">{data.status}</div>
          <div className="status-card__range">
            Runnable {data.range.runnable_min}–{data.range.runnable_max} {unit}
          </div>
          <div className="status-card__range" style={{ color: COLORS.green }}>
            Sweet {data.range.sweet_min}–{data.range.sweet_max}
          </div>
        </div>
      </div>

      <div className="status-card__updated">Updated {updatedTime}</div>
    </div>
  );
}
