import { useState } from "react";
import { COLORS, STATUS_COLOR, STATUS_EMOJI } from "../config";
import RequestRiverModal from "./RequestRiverModal";
import "./HomeScreen.css";

export interface RiverSummary {
  id: string;
  name: string;
  current_cfs: number;
  status: string;
  runnable: boolean;
  sweet_spot: boolean;
  updated_at: string;
  range: { runnable_min: number; runnable_max: number; sweet_min: number; sweet_max: number };
}

interface Props {
  rivers: RiverSummary[];
  loading: boolean;
  onSelect: (river: RiverSummary) => void;
  onRefresh: () => void;
}

export default function HomeScreen({ rivers, loading, onSelect, onRefresh }: Props) {
  const [modalVisible, setModalVisible] = useState(false);

  return (
    <div className="home">
      <div className="home__heading-row">
        <span className="home__heading">SELECT A RIVER</span>
        <button className="home__refresh" onClick={onRefresh} aria-label="Refresh">
          ↻
        </button>
      </div>

      {loading ? (
        <div className="home__loader">
          <div className="spinner" />
          <span className="home__loader-text">Loading rivers...</span>
        </div>
      ) : (
        rivers.map((river) => {
          const color = STATUS_COLOR[river.status] ?? COLORS.textMuted;
          const emoji = STATUS_EMOJI[river.status] ?? "•";
          const updatedTime = new Date(river.updated_at).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          });

          return (
            <button
              key={river.id}
              className="home__card"
              style={{ borderLeftColor: color }}
              onClick={() => onSelect(river)}
            >
              <div className="home__card-top">
                <div className="home__name-row">
                  <span className="home__river-name">{river.name}</span>
                  <span className="home__arrow">›</span>
                </div>
                <div className="home__badge" style={{ borderColor: color }}>
                  <span className="home__badge-emoji">{emoji}</span>
                  <span className="home__badge-text" style={{ color }}>
                    {river.status}
                  </span>
                </div>
              </div>

              <div className="home__card-bottom">
                <div className="home__stat">
                  <span className="home__stat-label">NOW</span>
                  <span className="home__stat-value" style={{ color }}>
                    {river.current_cfs} <span className="home__stat-unit">CFS</span>
                  </span>
                </div>
                <div className="home__stat">
                  <span className="home__stat-label">RUNNABLE</span>
                  <span className="home__stat-value">
                    {river.range?.runnable_min}–{river.range?.runnable_max}
                  </span>
                </div>
                <div className="home__stat">
                  <span className="home__stat-label">SWEET SPOT</span>
                  <span className="home__stat-value" style={{ color: COLORS.green }}>
                    {river.range?.sweet_min}–{river.range?.sweet_max}
                  </span>
                </div>
              </div>

              <div className="home__updated">Updated {updatedTime}</div>
            </button>
          );
        })
      )}

      <button className="home__request" onClick={() => setModalVisible(true)}>
        + Request a River
      </button>

      <RequestRiverModal visible={modalVisible} onClose={() => setModalVisible(false)} />
    </div>
  );
}
