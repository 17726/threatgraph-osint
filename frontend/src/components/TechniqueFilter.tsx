interface TechniqueFilterProps {
  techniques: { id: string; name: string }[];
  value: string;
  onChange: (techniqueId: string) => void;
}

export default function TechniqueFilter({ techniques, value, onChange }: TechniqueFilterProps) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      style={{
        padding: "4px 8px",
        background: "#ffffff",
        border: "1px solid #d7dfdd",
        borderRadius: 6,
        color: "#172026",
        fontSize: 12,
        outline: "none",
        minWidth: 140,
      }}
    >
      <option value="">全部攻击类型</option>
      {techniques.map((t) => (
        <option key={t.id} value={t.id}>
          {t.name}
        </option>
      ))}
    </select>
  );
}
