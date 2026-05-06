import { useCallback, useEffect, useMemo, useState } from "react";
import StatusCard from "./components/StatusCard";
import DailyCard from "./components/DailyCard";
import FlowChart from "./components/FlowChart";
import HomeScreen, { type RiverSummary } from "./components/HomeScreen";
import Logo from "./components/Logo";
import PerformanceCard, { type PerformanceData } from "./components/PerformanceCard";
import { API_BASE, COLORS } from "./config";
import "./App.css";

interface StatusData {
  river: string;
  current_cfs: number;
  display_unit: string;
  status: string;
  runnable: boolean;
  sweet_spot: boolean;
  updated_at: string;
  range: { runnable_min: number; runnable_max: number; sweet_min: number; sweet_max: number };
}

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

interface HourlyData {
  history: { time: string; cfs: number }[];
  forecast: { time: string; cfs: number }[];
}

export default function App() {
  const [rivers, setRivers] = useState<RiverSummary[]>([]);
  const [selectedRiver, setSelectedRiver] = useState<RiverSummary | null>(null);
  const [status, setStatus] = useState<StatusData | null>(null);
  const [daily, setDaily] = useState<DayData[]>([]);
  const [hourly, setHourly] = useState<HourlyData | null>(null);
  const [performance, setPerformance] = useState<PerformanceData | null>(null);
  const [loading, setLoading] = useState(true);
  const [riverLoading, setRiverLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchRivers = useCallback(async () => {
    try {
      setError(null);
      const res = await fetch(`${API_BASE}/rivers`);
      if (!res.ok) throw new Error("Server error");
      setRivers(await res.json());
    } catch {
      setError(`Could not reach server.\nMake sure the API is running at:\n${API_BASE}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRivers();
  }, [fetchRivers]);

  const fetchRiverDetail = useCallback(
    async (river: RiverSummary, forceRefresh = false) => {
      try {
        setError(null);
        if (forceRefresh) {
          await fetch(`${API_BASE}/rivers/${river.id}/refresh`, { method: "POST" });
        }
        const [statusRes, dailyRes, hourlyRes, perfRes] = await Promise.all([
          fetch(`${API_BASE}/rivers/${river.id}/status`),
          fetch(`${API_BASE}/rivers/${river.id}/forecast/daily`),
          fetch(`${API_BASE}/rivers/${river.id}/forecast/hourly`),
          fetch(`${API_BASE}/rivers/${river.id}/performance`),
        ]);
        if (!statusRes.ok || !dailyRes.ok || !hourlyRes.ok) throw new Error("Server error");
        const [statusData, dailyData, hourlyData] = await Promise.all([
          statusRes.json(),
          dailyRes.json(),
          hourlyRes.json(),
        ]);
        setStatus(statusData);
        setDaily(dailyData);
        setHourly(hourlyData);
        if (perfRes.ok) setPerformance(await perfRes.json());
      } catch {
        setError("Could not load river data.");
      } finally {
        setRiverLoading(false);
      }
    },
    []
  );

  const selectRiver = useCallback(
    (river: RiverSummary) => {
      setSelectedRiver(river);
      setStatus(null);
      setDaily([]);
      setHourly(null);
      setPerformance(null);
      setRiverLoading(true);
      fetchRiverDetail(river);
    },
    [fetchRiverDetail]
  );

  const onRiverRefresh = useCallback(() => {
    if (!selectedRiver) return;
    fetchRiverDetail(selectedRiver, true);
  }, [selectedRiver, fetchRiverDetail]);

  const filteredDaily = useMemo(() => {
    if (!daily.length || !status) return [];
    const { runnable_min, runnable_max } = status.range;

    return daily.filter((day) => {
      if (!hourly) return day.runnable;

      const after8am = new Date(`${day.date}T08:00:00`).getTime();
      const endOfDay = new Date(`${day.date}T23:59:59`).getTime();

      const hoursInWindow = hourly.forecast.filter((pt) => {
        const t = new Date(pt.time).getTime();
        return t >= after8am && t <= endOfDay;
      });

      if (hoursInWindow.length === 0) return day.runnable;

      const runnableCount = hoursInWindow.filter(
        (pt) => pt.cfs >= runnable_min && pt.cfs <= runnable_max
      ).length;

      return runnableCount > 4;
    });
  }, [daily, hourly, status]);

  return (
    <div className="app">
      <header className="app__header">
        <div className="app__header-top">
          {selectedRiver && (
            <button
              className="app__back"
              onClick={() => setSelectedRiver(null)}
              aria-label="Back"
            >
              ‹
            </button>
          )}
          <Logo size={48} />
          <div className="app__titles">
            <h1 className="app__title">IS IT IN?</h1>
            <p className="app__subtitle">
              {selectedRiver ? selectedRiver.name : "Whitewater Conditions"}
            </p>
          </div>
          {selectedRiver && (
            <button
              className="app__refresh"
              onClick={onRiverRefresh}
              aria-label="Refresh"
            >
              ↻
            </button>
          )}
        </div>
        <div className="app__divider" />
      </header>

      {error ? (
        <div className="app__error">
          <p className="app__error-text">{error}</p>
          <button
            className="app__retry"
            onClick={() => (selectedRiver ? fetchRiverDetail(selectedRiver) : fetchRivers())}
          >
            Retry
          </button>
        </div>
      ) : !selectedRiver ? (
        <HomeScreen
          rivers={rivers}
          loading={loading}
          onSelect={selectRiver}
          onRefresh={fetchRivers}
        />
      ) : (
        <div className="app__scroll">
          <StatusCard data={status} loading={riverLoading} />

          <h2 className="app__section">Flow Forecast</h2>
          {riverLoading || !hourly || !status ? (
            <div className="app__chart-loader">
              <div className="spinner" />
              <span className="app__chart-loader-text">Loading chart...</span>
            </div>
          ) : (
            <>
              <FlowChart history={hourly.history} forecast={hourly.forecast} range={status.range} />
              <div className="app__legend">
                <div className="app__legend-item">
                  <div className="app__legend-line" style={{ backgroundColor: COLORS.blue }} />
                  <span className="app__legend-text">Actual</span>
                </div>
                <div className="app__legend-item">
                  <div className="app__legend-dotted">
                    {[0, 1, 2, 3].map((i) => (
                      <div
                        key={i}
                        className="app__legend-dot"
                        style={{ backgroundColor: COLORS.red }}
                      />
                    ))}
                  </div>
                  <span className="app__legend-text">Forecast</span>
                </div>
              </div>
            </>
          )}

          <h2 className="app__section">7-Day Forecast</h2>
          {filteredDaily.length === 0 && !riverLoading ? (
            <p className="app__no-runs">No runnable days in the forecast.</p>
          ) : (
            filteredDaily.map((day) => <DailyCard key={day.date} day={day} />)
          )}

          <h2 className="app__section">Model Performance</h2>
          {performance && <PerformanceCard data={performance} />}

          <div style={{ height: 20 }} />
        </div>
      )}
    </div>
  );
}
