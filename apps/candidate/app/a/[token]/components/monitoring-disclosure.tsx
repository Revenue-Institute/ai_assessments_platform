export function MonitoringDisclosure() {
  return (
    <section
      aria-labelledby="monitor-heading"
      className="space-y-3 rounded border border-border bg-card p-5 text-sm leading-6"
    >
      <h2 className="font-medium text-base" id="monitor-heading">
        During this session we monitor:
      </h2>
      <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
        <li>Tab focus, fullscreen state, and window size changes</li>
        <li>Copy, cut, and paste attempts outside the code editor</li>
        <li>Time spent active on each question</li>
      </ul>
      <p className="text-muted-foreground">
        The assessment runs in fullscreen. You will be asked to enter fullscreen
        on the next screen and we log any exits. Your answers are saved to your
        record; we review every submission before sending final results.
      </p>
    </section>
  );
}
