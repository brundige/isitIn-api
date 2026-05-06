import { STATUS_COLOR, STATUS_EMOJI } from "../config";
import "./LegendKey.css";

const ITEMS = [
  { label: "Sweet Spot", status: "SWEET SPOT" },
  { label: "Paddable", status: "PADDABLE" },
  { label: "Too Low", status: "TOO LOW" },
  { label: "Too High", status: "TOO HIGH" },
];

export default function LegendKey() {
  return (
    <div className="legend">
      {ITEMS.map(({ label, status }) => {
        const color = STATUS_COLOR[status];
        const emoji = STATUS_EMOJI[status];
        return (
          <div key={status} className="legend__chip" style={{ borderColor: color + "66" }}>
            <span className="legend__emoji">{emoji}</span>
            <span className="legend__label" style={{ color }}>
              {label}
            </span>
          </div>
        );
      })}
    </div>
  );
}
