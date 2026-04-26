export default function DonePage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-4 px-6 text-center animate-reveal">
      <p className="eyebrow-label">Submitted</p>
      <h1 className="font-semibold text-3xl">Thanks.</h1>
      <p className="text-muted-foreground text-sm">
        Your assessment has been submitted. The Revenue Institute team will be
        in touch with next steps.
      </p>
      <p className="text-muted-foreground/60 text-xs">
        You can close this window.
      </p>
    </main>
  );
}
