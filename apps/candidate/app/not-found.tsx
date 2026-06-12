export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-3 px-6 text-center">
      <h1 className="font-semibold text-2xl">Link not recognized</h1>
      <p className="text-muted-foreground text-sm">
        This assessment link does not exist or has already been used. Check your
        email for the correct link or contact your administrator.
      </p>
    </main>
  );
}
