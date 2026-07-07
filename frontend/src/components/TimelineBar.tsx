import { useState, useRef, useEffect } from "react";

interface TimelineBarProps {
  minYear: number;
  maxYear: number;
  currentYear: number;
  onChange: (year: number) => void;
}

export default function TimelineBar({ minYear, maxYear, currentYear, onChange }: TimelineBarProps) {
  const [playing, setPlaying] = useState(false);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current !== null) {
        window.clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, []);

  const togglePlay = () => {
    if (playing) {
      if (timerRef.current !== null) {
        window.clearInterval(timerRef.current);
        timerRef.current = null;
      }
      setPlaying(false);
      return;
    }
    setPlaying(true);
    onChange(minYear);
    let current = minYear;
    timerRef.current = window.setInterval(() => {
      current++;
      if (current > maxYear) {
        if (timerRef.current !== null) {
          window.clearInterval(timerRef.current);
          timerRef.current = null;
        }
        setPlaying(false);
        current = maxYear;
      }
      onChange(current);
    }, 800);
  };

  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 12,
      padding: "8px 20px", background: "#ffffff",
      borderTop: "1px solid #d7dfdd", flexShrink: 0,
    }}>
      <span style={{ fontSize: 12, color: "#64748b", whiteSpace: "nowrap" }}>时间轴</span>
      <span style={{ fontSize: 14, fontWeight: 700, color: "#0f766e", minWidth: 40, textAlign: "center" }}>
        {currentYear}
      </span>
      <input
        type="range"
        min={minYear}
        max={maxYear}
        step={1}
        value={currentYear}
        onChange={(e) => onChange(parseInt(e.target.value))}
        style={{ flex: 1, maxWidth: 500, height: 4, accentColor: "#0f766e" }}
      />
      <button
        onClick={togglePlay}
        style={{
          padding: "4px 12px", background: "#f4f7f6",
          border: "1px solid #d7dfdd", borderRadius: 8,
          color: "#172026", fontSize: 13, cursor: "pointer",
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