interface RegionFilterProps {
  countries: { id: string; name: string }[];
  value: string;
  onChange: (regionId: string) => void;
}

export default function RegionFilter({ countries, value, onChange }: RegionFilterProps) {
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
      }}
    >
      <option value="">全部地区</option>
      {countries.map((c) => (
        <option key={c.id} value={c.id}>
          {c.name}
        </option>
      ))}
    </select>
  );
}
