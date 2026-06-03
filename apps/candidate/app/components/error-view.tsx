export function ErrorView({
  status,
  message,
  token,
  headline: headlineOverride,
}: {
  status: number;
  message: string;
  token?: string;
  headline?: string;
}) {
  let headline = headlineOverride ?? "Something went wrong";
  if (!headlineOverride) {
    if (status === 410) headline = "Link expired";
    else if (status === 404) headline = "Link not recognized";
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-3 px-6 text-center">
      <h1 className="font-semibold text-2xl">{headline}</h1>
      <p className="text-muted-foreground text-sm">{message}</p>
      {token && (
        <p className="text-muted-foreground/60 text-xs">
          Reference: <code>{token.slice(0, 8)}…</code>
        </p>
      )}
    </main>
  );
}
