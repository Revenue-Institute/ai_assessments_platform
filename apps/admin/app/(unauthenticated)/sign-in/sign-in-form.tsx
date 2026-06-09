"use client";

import { AlertBanner } from "@/components/alert-banner";
import { SubmitButton } from "@/components/submit-button";

export function SignInForm({
  action,
  error,
  next,
}: {
  action: (formData: FormData) => Promise<void>;
  error?: string;
  next?: string;
}) {
  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="font-semibold text-2xl">Sign in</h1>
        <p className="text-muted-foreground text-sm">
          Internal access only. Use your Revenue Institute email.
        </p>
      </header>

      <form action={action} className="space-y-3">
        <input name="next" type="hidden" value={next ?? ""} />
        <div className="space-y-1">
          <label className="text-sm" htmlFor="email">
            Email
          </label>
          <input
            autoComplete="email"
            autoFocus
            className="w-full rounded border border-border bg-transparent px-3 py-2 text-sm focus:border-primary focus:outline-none"
            id="email"
            name="email"
            required
            type="email"
          />
        </div>
        <div className="space-y-1">
          <label className="text-sm" htmlFor="password">
            Password
          </label>
          <input
            autoComplete="current-password"
            className="w-full rounded border border-border bg-transparent px-3 py-2 text-sm focus:border-primary focus:outline-none"
            id="password"
            name="password"
            required
            type="password"
          />
        </div>
        <AlertBanner>{error}</AlertBanner>
        <SubmitButton pendingLabel="Signing in...">Sign in</SubmitButton>
      </form>

      <p className="text-muted-foreground text-xs">
        Account access is provisioned by an admin in the Supabase dashboard.
      </p>
    </div>
  );
}
