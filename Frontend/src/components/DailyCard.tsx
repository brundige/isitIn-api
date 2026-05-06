import { COLORS, STATUS_COLOR, STATUS_EMOJI } from "../config";
import "./DailyCard.css";

interface DayData {
  date: string;
  day: string;
  peak_cfs: number;
  mean_cfs: number;
  precip_in: number;
  status: string;
  runnable: boolean;
  sweet_spot: boolean;
}

export default function DailyCard({ day }: { day: DayData }) {
  const color = STATUS_COLOR[day.status] ?? COLORS.textMuted;
  const emoji = STATUS_EMOJI[day.status] ?? "•";

  const [dayName, dayDate] = day.day.split(" ");

  return (
    <div className="daily-card" style={{ borderLeftColor: color }}>
      <div className="daily-card__day">
        <div className="daily-card__day-name">{dayName?.toUpperCase()}</div>
        <div className="daily-card__day-date">{dayDate}</div>
      </div>

      <div className="daily-card__status">
        <span className="daily-card__emoji">{emoji}</span>
        <span className="daily-card__status-text" style={{ color }}>
          {day.status}
        </span>
      </div>

      <div className="daily-card__stats">
        <div className="daily-card__stat-row">
          <span className="daily-card__stat-label">PEAK</span>
          <span className="daily-card__stat-value" style={{ color }}>
            {day.peak_cfs}
          </span>
        </div>
        <div className="daily-card__stat-row">
          <span className="daily-card__stat-label">RAIN</span>
          <span className="daily-card__stat-value" style={{ color: COLORS.blue }}>
            {day.precip_in}"
          </span>
        </div>
      </div>
    </div>
  );
}
