import { useEffect, useState } from "react";

interface TimelineBarProps {
  minYear: number;
  maxYear: number;
  currentYear: number;
  onChange: (year: number) => void;
}

export default function TimelineBar({ minYear, maxYear, currentYear, onChange }: TimelineBarProps) {
  const [playing, setPlaying] = useState(false);

  const togglePlay = () => {
    if (playing) {
      setPlaying(false);
    } else {
      if (currentYear >= maxYear) {
        onChange(minYear);
      }
      setPlaying(true);
    }
  };

  useEffect(() => {
    if (!playing) return;

    const timer = window.setInterval(() => {
      if (currentYear >= maxYear) {
        setPlaying(false);
      } else {
        onChange(currentYear + 1);
      }
    }, 800);

    return () => window.clearInterval(timer);
  }, [playing, currentYear, maxYear, onChange]);

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: "8px 20px",
        background: "#ffffff",
        borderTop: "1px solid #d7dfdd",
        flexShrink: 0,
      }}
    >
      <span style={{ fontSize: 12, color: "#64748b", whiteSpace: "nowrap" }}>时间轴</span>
      <span
        style={{
          fontSize: 14,
          fontWeight: 700,
          color: "#0f766e",
          minWidth: 40,
          textAlign: "center",
        }}
      >
        {currentYear}
      </span>
      <input
        type="range"
        min={minYear}
        max={maxYear}
        step={1}
        value={currentYear}
        onChange={(e) => onChange(parseInt(e.target.value, 10))}
        style={{ flex: 1, maxWidth: 500, height: 4, accentColor: "#0f766e" }}
      />
      <button
        onClick={togglePlay}
        style={{
          padding: "4px 12px",
          background: "#f4f7f6",
          border: "1px solid #d7dfdd",
          borderRadius: 8,
          color: "#172026",
          fontSize: 13,
          cursor: "pointer",
        }}
      >
        {playing ? "⏸" : "▶"}
      </button>
      <span style={{ fontSize: 12, color: "#64748b", whiteSpace: "nowrap" }}>
        {minYear} - {maxYear}
      </span>
    </div>
  );
}
