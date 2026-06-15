export function PageLoading() {
  return (
    <div className="flex flex-1 animate-pulse flex-col gap-4 p-4 pt-0">
      <div className="h-16 rounded-xl bg-muted/40" />
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <div className="h-14 rounded-xl bg-muted/40" />
        <div className="h-14 rounded-xl bg-muted/40" />
        <div className="h-14 rounded-xl bg-muted/40" />
        <div className="h-14 rounded-xl bg-muted/40" />
      </div>
      <div className="h-48 rounded-xl bg-muted/40" />
      <div className="h-32 rounded-xl bg-muted/40" />
    </div>
  );
}
