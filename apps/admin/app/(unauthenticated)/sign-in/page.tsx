import { redirect } from "next/navigation";
import { signIn } from "./actions";

type SearchParams = Promise<{ next?: string; error?: string }>;

export default async function SignInPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const { next, error } = await searchParams;

  async function handleSignIn(formData: FormData) {
    "use server";
    const result = await signIn(formData);
    if (result.ok) {
      redirect(result.next || "/");
    }
    redirect(
      `/sign-in?error=${encodeURIComponent(result.error)}${next ? `&next=${encodeURIComponent(next)}` : ""}`
    );
  }

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="font-semibold text-2xl">Sign in</h1>
        <p className="text-muted-foreground text-sm">
          Internal access only. Use your Revenue Institute email.
        </p>
      </header>

      <form action={handleSignIn} className="space-y-3">
        <input type="hidden" name="next" value={next ?? ""} />
        <div className="space-y-1">
          <label className="text-sm" htmlFor="email">
            Email
          </label>
          <input
            autoComplete="email"
            className="w-full rounded border border-emerald-900/50 bg-transparent px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
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
            className="w-full rounded border border-emerald-900/50 bg-transparent px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
            id="password"
            name="password"
            required
            type="password"
          />
        </div>
        {error && (
          <p className="rounded border border-red-900/50 bg-red-950/30 px-3 py-2 text-red-200 text-sm">
            {error}
          </p>
        )}
        <button
          className="w-full rounded bg-emerald-600 px-3 py-2 text-sm text-white hover:bg-emerald-500"
          type="submit"
        >
          Sign in
        </button>
      </form>

      <p className="text-muted-foreground text-xs">
        Account access is provisioned by an admin in the Supabase dashboard.
      </p>
    </div>
  );
}
