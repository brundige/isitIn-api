import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { API_BASE } from "../config";
import "./RequestRiverModal.css";

interface Props {
  visible: boolean;
  onClose: () => void;
}

export default function RequestRiverModal({ visible, onClose }: Props) {
  const [riverName, setRiverName] = useState("");
  const [location, setLocation] = useState("");
  const [gaugeId, setGaugeId] = useState("");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!visible) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") handleClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  function reset() {
    setRiverName("");
    setLocation("");
    setGaugeId("");
    setNotes("");
    setSubmitting(false);
    setSubmitted(false);
    setError(null);
  }

  function handleClose() {
    reset();
    onClose();
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!riverName.trim()) {
      setError("River name is required.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/river-requests`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          river_name: riverName.trim(),
          location: location.trim(),
          gauge_id: gaugeId.trim(),
          notes: notes.trim(),
        }),
      });
      if (!res.ok) throw new Error("Server error");
      setSubmitted(true);
    } catch {
      setError("Failed to submit. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  if (!visible) return null;

  return createPortal(
    <div className="modal-overlay" onClick={handleClose}>
      <div className="modal-sheet" onClick={(e) => e.stopPropagation()}>
        <div className="modal-handle" />

        <div className="modal-header">
          <h2 className="modal-title">Request a River</h2>
          <button className="modal-close" onClick={handleClose} aria-label="Close">
            ✕
          </button>
        </div>

        {submitted ? (
          <div className="modal-success">
            <div className="modal-success__icon">🛶</div>
            <div className="modal-success__text">Request submitted!</div>
            <p className="modal-success__sub">
              Thanks — we'll review {riverName} and add it if we can get gauge data.
            </p>
            <button className="modal-submit" onClick={handleClose}>
              Done
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="modal-form">
            <label className="modal-label">
              River Name <span className="modal-required">*</span>
            </label>
            <input
              className="modal-input"
              placeholder="e.g. Ocoee River"
              value={riverName}
              onChange={(e) => setRiverName(e.target.value)}
              autoFocus
            />

            <label className="modal-label">Location / State</label>
            <input
              className="modal-input"
              placeholder="e.g. Tennessee"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
            />

            <label className="modal-label">USGS Gauge ID</label>
            <input
              className="modal-input"
              placeholder="e.g. 03530000 (optional)"
              value={gaugeId}
              onChange={(e) => setGaugeId(e.target.value)}
            />

            <label className="modal-label">Notes</label>
            <textarea
              className="modal-input modal-textarea"
              placeholder="Runnable range, sweet spot, any helpful info..."
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
            />

            {error && <div className="modal-error">{error}</div>}

            <button
              type="submit"
              className="modal-submit"
              disabled={submitting}
            >
              {submitting ? "Submitting..." : "Submit Request"}
            </button>
          </form>
        )}
      </div>
    </div>,
    document.body
  );
}
