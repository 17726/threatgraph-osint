export interface GraphLegendItem {
  name: string;
  color: string;
}

interface GraphLegendProps {
  items: GraphLegendItem[];
  value: string | null;
  onChange: (value: string | null) => void;
}

export default function GraphLegend({ items, value, onChange }: GraphLegendProps) {
  return (
    <div className="graph-legend" role="group" aria-label="实体类型筛选">
      <button
        type="button"
        className={value === null ? "active" : ""}
        aria-label="显示全部类型"
        aria-pressed={value === null}
        onClick={() => onChange(null)}
      >
        全部
      </button>
      {items.map((item) => (
        <button
          key={item.name}
          type="button"
          className={value === item.name ? "active" : ""}
          aria-label={`筛选类型 ${item.name}`}
          aria-pressed={value === item.name}
          onClick={() => onChange(item.name)}
        >
          <span
            className="graph-legend-dot"
            style={{ background: item.color }}
            aria-hidden="true"
          />
          {item.name}
        </button>
      ))}
    </div>
  );
}
