import { useEffect, useMemo, useRef, useState } from "react";
import { Fragment } from "react";
import { COLORS } from "../config";
import "./FlowChart.css";

interface DataPoint {
  time: string;
  cfs: number;
}

interface Range {
  runnable_min: number;
  runnable_max: number;
  sweet_min: number;
  sweet_max: number;
}

interface Props {
  history: DataPoint[];
  forecast: DataPoint[];
  range: Range;
}

const RANGE_OPTS = [
  { label: "1D", backH: 24, fwdH: 24 },
  { label: "3D", backH: 24, fwdH: 48 },
  { label: "7D", backH: 72, fwdH: 96 },
  { label: "All", backH: null, fwdH: null },
] as const;

type RangeLabel = (typeof RANGE_OPTS)[number]["label"];

const ONE_HOUR = 3_600_000;
const SEVEN_DAYS = 7 * 24 * ONE_HOUR;

const H = 320;
const PAD = { top: 16, right: 8, bottom: 40, left: 0 };

type Anchor =
  | { mode: "pinch"; tMin: number; tMax: number; dist: number; frac: number; midT: number }
  | { mode: "pan"; tMin: number; tMax: number; startX: number };

export default function FlowChart({ history, forecast, range }: Props) {
  const [activeRange, setActiveRange] = useState<RangeLabel>("3D");
  const [zoomOverride, setZoomOverride] = useState<{ tMin: number; tMax: number } | null>(null);
  const [width, setWidth] = useState<number>(
    typeof window !== "undefined" ? window.innerWidth : 375
  );

  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w) setWidth(w);
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  const PLOT_W = width - PAD.left - PAD.right;
  const PLOT_H = H - PAD.top - PAD.bottom;

  const histPts = useMemo(
    () => history.map((p) => ({ t: new Date(p.time).getTime(), cfs: p.cfs })),
    [history]
  );
  const fcastPts = useMemo(
    () => forecast.map((p) => ({ t: new Date(p.time).getTime(), cfs: p.cfs })),
    [forecast]
  );

  const nowT = useMemo(
    () => (histPts.length ? histPts[histPts.length - 1].t : Date.now()),
    [histPts]
  );

  const { rangeTMin, rangeTMax } = useMemo(() => {
    const opt = RANGE_OPTS.find((r) => r.label === activeRange)!;
    const allT = [...histPts, ...fcastPts].map((p) => p.t);
    const tStart = opt.backH === null ? Math.min(...allT) : nowT - opt.backH * ONE_HOUR;
    const tEnd = opt.fwdH === null ? Math.max(...allT) : nowT + opt.fwdH * ONE_HOUR;
    return { rangeTMin: tStart, rangeTMax: tEnd };
  }, [activeRange, histPts, fcastPts, nowT]);

  const tMin = zoomOverride?.tMin ?? rangeTMin;
  const tMax = zoomOverride?.tMax ?? rangeTMax;

  const boundsRef = useRef({ tMin, tMax });
  useEffect(() => {
    boundsRef.current = { tMin, tMax };
  }, [tMin, tMax]);

  // Pointer-event-based pan/pinch
  const pointersRef = useRef<Map<number, { x: number; y: number }>>(new Map());
  const anchorRef = useRef<Anchor | null>(null);

  const setAnchor = () => {
    const pts = Array.from(pointersRef.current.values());
    const { tMin, tMax } = boundsRef.current;
    if (pts.length >= 2) {
      const dx = pts[0].x - pts[1].x;
      const dy = pts[0].y - pts[1].y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      const midX = (pts[0].x + pts[1].x) / 2;
      const rect = containerRef.current?.getBoundingClientRect();
      const localX = midX - (rect?.left ?? 0);
      const frac = Math.max(0, Math.min(1, (localX - PAD.left) / PLOT_W));
      anchorRef.current = {
        mode: "pinch",
        tMin,
        tMax,
        dist,
        frac,
        midT: tMin + frac * (tMax - tMin),
      };
    } else if (pts.length === 1) {
      anchorRef.current = { mode: "pan", tMin, tMax, startX: pts[0].x };
    } else {
      anchorRef.current = null;
    }
  };

  const onPointerDown = (e: React.PointerEvent) => {
    (e.target as Element).setPointerCapture?.(e.pointerId);
    pointersRef.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    setAnchor();
  };

  const onPointerMove = (e: React.PointerEvent) => {
    if (!pointersRef.current.has(e.pointerId)) return;
    pointersRef.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    const anchor = anchorRef.current;
    if (!anchor) return;
    const pts = Array.from(pointersRef.current.values());

    if (anchor.mode === "pinch" && pts.length >= 2) {
      const dx = pts[0].x - pts[1].x;
      const dy = pts[0].y - pts[1].y;
      const newDist = Math.sqrt(dx * dx + dy * dy);
      const scale = anchor.dist / newDist;
      const oldSpan = anchor.tMax - anchor.tMin;
      const newSpan = Math.max(ONE_HOUR, Math.min(SEVEN_DAYS, oldSpan * scale));
      setZoomOverride({
        tMin: anchor.midT - anchor.frac * newSpan,
        tMax: anchor.midT + (1 - anchor.frac) * newSpan,
      });
    } else if (anchor.mode === "pan" && pts.length === 1) {
      const deltaX = pts[0].x - anchor.startX;
      const timePerPx = (anchor.tMax - anchor.tMin) / PLOT_W;
      setZoomOverride({
        tMin: anchor.tMin - deltaX * timePerPx,
        tMax: anchor.tMax - deltaX * timePerPx,
      });
    }
  };

  const onPointerUp = (e: React.PointerEvent) => {
    pointersRef.current.delete(e.pointerId);
    if (pointersRef.current.size === 0) {
      anchorRef.current = null;
    } else {
      setAnchor();
    }
  };

  const onWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const localX = e.clientX - rect.left;
    const frac = Math.max(0, Math.min(1, (localX - PAD.left) / PLOT_W));
    const { tMin, tMax } = boundsRef.current;
    const midT = tMin + frac * (tMax - tMin);
    const scale = Math.exp(e.deltaY * 0.001);
    const oldSpan = tMax - tMin;
    const newSpan = Math.max(ONE_HOUR, Math.min(SEVEN_DAYS, oldSpan * scale));
    setZoomOverride({
      tMin: midT - frac * newSpan,
      tMax: midT + (1 - frac) * newSpan,
    });
  };

  // Derived chart values
  const { visHist, visFcast, yMin, yMax } = useMemo(() => {
    const visH = histPts.filter((p) => p.t >= tMin && p.t <= tMax);
    const visF = fcastPts.filter((p) => p.t >= tMin && p.t <= tMax);
    const allCfs = [...visH, ...visF].map((p) => p.cfs);
    if (!allCfs.length) return { visHist: [], visFcast: [], yMin: 0, yMax: 500 };
    const rawMin = Math.min(...allCfs);
    const rawMax = Math.max(...allCfs);
    const pad = (rawMax - rawMin) * 0.12;
    return { visHist: visH, visFcast: visF, yMin: Math.max(0, rawMin - pad), yMax: rawMax + pad };
  }, [tMin, tMax, histPts, fcastPts]);

  const xS = (t: number) => PAD.left + ((t - tMin) / (tMax - tMin)) * PLOT_W;
  const yS = (v: number) => PAD.top + PLOT_H - ((v - yMin) / (yMax - yMin)) * PLOT_H;

  const toPath = (pts: { t: number; cfs: number }[]) =>
    pts
      .map((p, i) => `${i === 0 ? "M" : "L"}${xS(p.t).toFixed(1)},${yS(p.cfs).toFixed(1)}`)
      .join(" ");

  const yTicks = useMemo(() => {
    const steps = 5;
    return Array.from({ length: steps }, (_, i) =>
      Math.round(yMin + ((yMax - yMin) * i) / (steps - 1))
    );
  }, [yMin, yMax]);

  const xTicks = useMemo(() => {
    const spanH = (tMax - tMin) / ONE_HOUR;
    const stepH = spanH <= 6 ? 1 : spanH <= 24 ? 6 : spanH <= 72 ? 12 : 24;
    const d = new Date(tMin);
    d.setMinutes(0, 0, 0);
    d.setHours(d.getHours() + 1);
    const ticks: number[] = [];
    while (d.getTime() <= tMax) {
      if (d.getTime() >= tMin) ticks.push(d.getTime());
      d.setHours(d.getHours() + stepH);
    }
    return ticks;
  }, [tMin, tMax]);

  const dayBoundaries = useMemo(() => {
    const boundaries: number[] = [];
    const d = new Date(tMin);
    d.setHours(0, 0, 0, 0);
    d.setDate(d.getDate() + 1);
    while (d.getTime() <= tMax) {
      boundaries.push(d.getTime());
      d.setDate(d.getDate() + 1);
    }
    return boundaries;
  }, [tMin, tMax]);

  const PADDLING_HOURS = [8, 10, 12, 14, 16, 18];
  const hourMarkers = useMemo(() => {
    if (tMax - tMin > 48 * ONE_HOUR) return [];
    const markers: { t: number; label: string }[] = [];
    const d = new Date(tMin);
    d.setHours(0, 0, 0, 0);
    d.setDate(d.getDate() - 1);
    while (d.getTime() <= tMax) {
      for (const hr of PADDLING_HOURS) {
        const t = new Date(d).setHours(hr, 0, 0, 0);
        if (t >= tMin && t <= tMax) {
          const suffix = hr < 12 ? "a" : "p";
          const h12 = hr <= 12 ? hr : hr - 12;
          markers.push({ t, label: `${h12}${suffix}` });
        }
      }
      d.setDate(d.getDate() + 1);
    }
    return markers;
  }, [tMin, tMax]);

  const pMinY = Math.min(yS(range.runnable_min), PAD.top + PLOT_H);
  const pMaxY = Math.max(yS(range.runnable_max), PAD.top);
  const sMinY = Math.min(yS(range.sweet_min), PAD.top + PLOT_H);
  const sMaxY = Math.max(yS(range.sweet_max), PAD.top);
  const nowX = xS(nowT);

  return (
    <div
      ref={containerRef}
      className="chart"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onWheel={onWheel}
    >
      <svg className="chart__svg" width={width} height={H}>
        <rect
          x={PAD.left}
          y={pMaxY}
          width={PLOT_W}
          height={pMinY - pMaxY}
          fill="#56E8C7"
          opacity={0.08}
        />
        <rect
          x={PAD.left}
          y={sMaxY}
          width={PLOT_W}
          height={sMinY - sMaxY}
          fill="#E8C556"
          opacity={0.18}
        />

        {dayBoundaries.map((t, i) => {
          const x = xS(t);
          const label = new Date(t).toLocaleDateString([], { weekday: "short" });
          return (
            <Fragment key={`d${i}`}>
              <line
                x1={x}
                y1={PAD.top}
                x2={x}
                y2={PAD.top + PLOT_H}
                stroke="rgba(255,255,255,0.1)"
                strokeWidth={1}
              />
              <text
                x={x + 5}
                y={PAD.top + 14}
                fill="rgba(255,255,255,0.2)"
                fontSize={11}
                fontWeight={600}
              >
                {label}
              </text>
            </Fragment>
          );
        })}

        {hourMarkers.map(({ t, label }, i) => {
          const x = xS(t);
          return (
            <Fragment key={`h${i}`}>
              <line
                x1={x}
                y1={PAD.top}
                x2={x}
                y2={PAD.top + PLOT_H}
                stroke="rgba(255,255,255,0.07)"
                strokeWidth={1}
                strokeDasharray="3,5"
              />
              <text x={x + 4} y={PAD.top + 14} fill="rgba(255,255,255,0.18)" fontSize={10}>
                {label}
              </text>
            </Fragment>
          );
        })}

        {yTicks.map((v, i) => (
          <line
            key={`yg${i}`}
            x1={PAD.left}
            y1={yS(v)}
            x2={width - PAD.right}
            y2={yS(v)}
            stroke="#1e2b28"
            strokeWidth={1}
          />
        ))}

        {nowX >= PAD.left && nowX <= width - PAD.right && (
          <line
            x1={nowX}
            y1={PAD.top}
            x2={nowX}
            y2={PAD.top + PLOT_H}
            stroke="rgba(255,255,255,0.2)"
            strokeWidth={1.5}
          />
        )}

        {visHist.length > 1 && (
          <path
            d={toPath(visHist)}
            stroke={COLORS.blue}
            strokeWidth={2.5}
            fill="none"
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        )}

        {visFcast.length > 1 && (
          <path
            d={toPath(visFcast)}
            stroke={COLORS.red}
            strokeWidth={2.5}
            fill="none"
            strokeDasharray="5,5"
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        )}

        {yTicks.map((v, i) => (
          <text key={`yl${i}`} x={PAD.left + 6} y={yS(v) - 5} fill="#ffffff" fontSize={13}>
            {v.toLocaleString()}
          </text>
        ))}

        {xTicks.map((t, i) => {
          const x = xS(t);
          if (x < 24 || x > width - 24) return null;
          const d = new Date(t);
          const hr = d.getHours();
          const label =
            hr === 0
              ? d.toLocaleDateString([], { weekday: "short" })
              : `${hr % 12 || 12}${hr < 12 ? "a" : "p"}`;
          return (
            <text
              key={`xl${i}`}
              x={x}
              y={PAD.top + PLOT_H + 22}
              fill="#888"
              fontSize={13}
              textAnchor="middle"
            >
              {label}
            </text>
          );
        })}
      </svg>

      <div className="chart__range-bar">
        {RANGE_OPTS.map((opt) => {
          const active = activeRange === opt.label && !zoomOverride;
          return (
            <button
              key={opt.label}
              className={`chart__range-btn${active ? " chart__range-btn--active" : ""}`}
              onClick={() => {
                setActiveRange(opt.label);
                setZoomOverride(null);
              }}
            >
              {opt.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
