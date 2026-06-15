"use client";

import { useTransition } from "react";

// window.location.assign forces a hard navigation so nginx can route /a/* to the candidate app (soft nav silently no-ops on single-host prod).
export function OpenAsCandidateButton({
  getUrl,
}: {
  getUrl: () => Promise<string>;
}) {
  const [pending, startTransition] = useTransition();

  function handleOpen() {
    startTransition(async () => {
      const url = await getUrl();
      window.location.assign(url);
    });
  }

  return (
    <button
      className="btn-primary text-sm"
      disabled={pending}
      onClick={handleOpen}
      type="button"
    >
      {pending ? "Opening..." : "Open as candidate"}
    </button>
  );
}
