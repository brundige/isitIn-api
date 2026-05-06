export const API_BASE = import.meta.env.DEV
  ? "http://192.168.0.173:8000"
  : "https://api.brundigital.io";

export const COLORS = {
  bg:          "#0d1514",
  card:        "#161f1d",
  cardBorder:  "#2a3832",
  blue:        "#56E8C7",
  green:       "#E8C556",
  orange:      "#E8A656",
  red:         "#E8A656",
  yellow:      "#E8C556",
  textPrimary: "#ddf2ee",
  textMuted:   "#678593",
};

export const STATUS_COLOR: Record<string, string> = {
  "SWEET SPOT": COLORS.green,
  "RUNNABLE":   COLORS.blue,
  "TOO LOW":    "#678593",
  "TOO HIGH":   COLORS.orange,
};

export const STATUS_EMOJI: Record<string, string> = {
  "SWEET SPOT": "🛶",
  "RUNNABLE":   "✅",
  "TOO LOW":    "🪨",
  "TOO HIGH":   "🌊",
};
