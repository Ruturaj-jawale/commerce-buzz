type StatusCardProps = {
  label: string;
  value: string;
};

export function StatusCard({ label, value }: StatusCardProps) {
  return (
    <div className="card">
      <p className="label">{label}</p>
      <p className="value">{value}</p>
    </div>
  );
}