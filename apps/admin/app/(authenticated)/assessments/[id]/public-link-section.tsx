import { SubmitButton } from "@/components/submit-button";
import type { PublicLinkView } from "@/lib/api";

import { CopyButton } from "../../components/copy-button";
import {
  disablePublicLinkAction,
  enablePublicLinkAction,
  rotatePublicLinkAction,
} from "../actions";

const secondaryButton =
  "rounded border border-border/50 bg-background px-3 py-2 text-sm hover:bg-muted";

export function PublicLinkSection({
  id,
  link,
  status,
}: {
  id: string;
  link: PublicLinkView | null;
  status: string;
}) {
  const enable = enablePublicLinkAction.bind(null, id);
  const disable = disablePublicLinkAction.bind(null, id);
  const rotate = rotatePublicLinkAction.bind(null, id);

  return (
    <section className="space-y-3 rounded-xl border border-border/50 bg-muted/30 p-4">
      <div>
        <h2 className="font-semibold text-sm">Public enrollment link</h2>
        <p className="text-muted-foreground text-xs">
          Share one link. Candidates enter their name and email to start, so you
          do not have to add candidates and assignments by hand.
        </p>
      </div>

      {link ? (
        <>
          <div className="flex items-center gap-2">
            <input
              className="w-full rounded border border-border/60 bg-background px-3 py-2 font-mono text-xs"
              readOnly
              value={link.url}
            />
            <CopyButton label="Copy link" value={link.url} />
          </div>

          <div className="flex flex-wrap items-center gap-4 text-muted-foreground text-xs">
            <span>
              {link.uses_count} registration{link.uses_count === 1 ? "" : "s"}
            </span>
            {link.max_uses != null && <span>Cap: {link.max_uses}</span>}
            <span>
              Assignment deadline: {link.assignment_expires_in_days} days
            </span>
          </div>

          {status !== "published" && (
            <p className="rounded border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-amber-700 text-xs dark:text-amber-400">
              Publish this assessment so candidates can enroll through the link.
            </p>
          )}

          <div className="flex flex-wrap gap-2">
            <form action={rotate}>
              <SubmitButton
                className={secondaryButton}
                pendingLabel="Rotating..."
              >
                Rotate link
              </SubmitButton>
            </form>
            <form action={disable}>
              <SubmitButton
                className={secondaryButton}
                pendingLabel="Disabling..."
              >
                Disable
              </SubmitButton>
            </form>
          </div>
        </>
      ) : (
        <form action={enable}>
          <SubmitButton
            className="btn-primary text-sm"
            pendingLabel="Enabling..."
          >
            Enable public link
          </SubmitButton>
        </form>
      )}
    </section>
  );
}
