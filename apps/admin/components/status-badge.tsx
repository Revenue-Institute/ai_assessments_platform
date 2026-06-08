export function StatusBadge({ status }: { status: string }) {
  const tone =
    status === "published"
      ? "bg-primary/20 text-primary"
      : status === "archived"
        ? "bg-muted text-muted-foreground"
        : "bg-warning/20 text-warning";

  return (
    <span className={`rounded px-2 py-0.5 font-medium text-xs ${tone}`}>
      {status}
    </span>
  );
}
