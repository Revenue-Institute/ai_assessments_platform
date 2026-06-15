export function NoticeView({ title, body }: { title: string; body: string }) {
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-3 px-6 text-center">
      <h1 className="font-semibold text-2xl">{title}</h1>
      <p className="text-muted-foreground text-sm">{body}</p>
    </main>
  );
}
