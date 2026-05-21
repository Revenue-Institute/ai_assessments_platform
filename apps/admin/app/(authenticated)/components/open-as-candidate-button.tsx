"use client";

import { useTransition } from "react";

// Single-host prod: admin and candidate share assessments.revenueinstitute.com.
// A server-action `redirect()` to /a/{token} therefore looks same-origin to
// Next's client router, which tries a soft router navigation instead of a
// full page load. The admin app has no /a/{token} route, so the click
// silently no-ops. Doing window.location.assign() here forces a hard
// navigation through nginx, which path-routes /a/* to the candidate.
export function OpenAsCandidateButton({
  getUrl,
}: {
  getUrl: () => Promise<string>;
}) {
  const [pending, startTransition] = useTransition();
  return (
    <button
      className="btn-primary text-sm"
      disabled={pending}
      onClick={() => {
        startTransition(async () => {
          const url = await getUrl();
          window.location.assign(url);
        });
      }}
      type="button"
    >
      {pending ? "Opening..." : "Open as candidate"}
    </button>
  );
}
