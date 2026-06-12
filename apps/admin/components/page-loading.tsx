export function PageLoading() {
  return (
    <div className="flex flex-1 flex-col gap-4 p-4 pt-0 animate-pulse">
      <div className="h-16 rounded-xl bg-muted/40" />
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div className="h-14 rounded-xl bg-muted/40" key={i} />
        ))}
      </div>
      <div className="h-48 rounded-xl bg-muted/40" />
      <div className="h-32 rounded-xl bg-muted/40" />
    </div>
  );
}
