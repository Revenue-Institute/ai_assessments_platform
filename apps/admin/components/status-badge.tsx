export function StatusBadge({ status }: { status: string }) {
  const tones: Record<string, string> = {
    published: "bg-primary/20 text-primary",
    archived: "bg-muted text-muted-foreground",
  };
  const tone = tones[status] ?? "bg-warning/20 text-warning";

  return (
    <span className={`rounded px-2 py-0.5 font-medium text-xs ${tone}`}>
      {status}
    </span>
  );
}
