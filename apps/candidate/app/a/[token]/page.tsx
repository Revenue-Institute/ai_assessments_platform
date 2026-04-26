import { headers } from "next/headers";
import { notFound, redirect } from "next/navigation";
import { ApiError, fetchAssignment, postConsent } from "@/lib/api";

type Params = { token: string };
type SearchParams = Promise<{ error?: string }>;

export default async function CandidateLandingPage({
  params,
  searchParams,
}: {
  params: Promise<Params>;
  searchParams: SearchParams;
}) {
  const { token } = await params;
  const { error: consentError } = await searchParams;
  if (!token || token.length < 16) {
    notFound();
  }

  let assignment: Awaited<ReturnType<typeof fetchAssignment>>;
  try {
    assignment = await fetchAssignment(token);
  } catch (error) {
    if (error instanceof ApiError) {
      return (
        <ErrorView
          status={error.status}
          message={error.message}
          token={token}
        />
      );
    }
    throw error;
  }

  if (assignment.status === "in_progress") {
    redirect(`/a/${token}/in-progress`);
  }

  if (assignment.status === "completed") {
    return (
      <NoticeView
        title="Already submitted"
        body="This assessment has already been submitted. Thanks for completing it."
      />
    );
  }

  async function handleConsent() {
    "use server";
    const headerStore = await headers();
    const forwardedIp =
      headerStore.get("x-forwarded-for") ??
      headerStore.get("x-real-ip") ??
      undefined;
    try {
      await postConsent(token, forwardedIp ?? undefined);
    } catch (error) {
      if (error instanceof ApiError) {
        redirect(`/a/${token}?error=${encodeURIComponent(error.message)}`);
      }
      throw error;
    }
    redirect(`/a/${token}/in-progress`);
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 px-6 py-12">
      <header className="space-y-2">
        <p className="text-emerald-300/70 text-xs uppercase tracking-widest">
          Revenue Institute
        </p>
        <h1 className="font-semibold text-3xl">{assignment.module.title}</h1>
        <p className="text-emerald-100/70 text-sm">
          {assignment.module.description}
        </p>
      </header>

      <dl className="grid grid-cols-2 gap-3 rounded-lg border border-emerald-900/60 bg-emerald-950/40 p-5 text-sm">
        <div>
          <dt className="text-emerald-300/60 text-xs uppercase tracking-wide">
            Candidate
          </dt>
          <dd className="font-medium">{assignment.subject.full_name}</dd>
        </div>
        <div>
          <dt className="text-emerald-300/60 text-xs uppercase tracking-wide">
            Time limit
          </dt>
          <dd className="font-medium">
            {assignment.module.target_duration_minutes} minutes
          </dd>
        </div>
        <div>
          <dt className="text-emerald-300/60 text-xs uppercase tracking-wide">
            Questions
          </dt>
          <dd className="font-medium">{assignment.module.question_count}</dd>
        </div>
        <div>
          <dt className="text-emerald-300/60 text-xs uppercase tracking-wide">
            Link expires
          </dt>
          <dd className="font-medium">
            {new Date(assignment.expires_at).toLocaleString()}
          </dd>
        </div>
      </dl>

      <section className="space-y-3 rounded-lg border border-emerald-900/60 bg-emerald-950/40 p-5 text-sm leading-6">
        <p className="font-medium">During this session we monitor:</p>
        <ul className="list-disc space-y-1 pl-5 text-emerald-100/80">
          <li>Tab focus, fullscreen state, and window size changes</li>
          <li>Copy, cut, and paste attempts outside the code editor</li>
          <li>Time spent active on each question</li>
        </ul>
        <p className="text-emerald-100/60">
          Raw answers are stored permanently. AI scores them against a rubric
          and a human reviewer may re-score before final results are issued.
        </p>
      </section>

      {consentError && (
        <p className="rounded border border-red-900/50 bg-red-950/30 px-3 py-2 text-red-200 text-sm">
          {consentError}
        </p>
      )}

      <form action={handleConsent}>
        <button
          className="w-full rounded bg-emerald-500 px-3 py-3 font-medium text-emerald-950 hover:bg-emerald-400"
          type="submit"
        >
          I understand and consent to begin
        </button>
      </form>
    </main>
  );
}

function NoticeView({ title, body }: { title: string; body: string }) {
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-3 px-6 text-center">
      <h1 className="font-semibold text-2xl">{title}</h1>
      <p className="text-emerald-100/70 text-sm">{body}</p>
    </main>
  );
}

function ErrorView({
  status,
  message,
  token,
}: {
  status: number;
  message: string;
  token: string;
}) {
  const headline =
    status === 410
      ? "Link expired"
      : status === 404
        ? "Link not recognized"
        : "Something went wrong";
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-3 px-6 text-center">
      <h1 className="font-semibold text-2xl">{headline}</h1>
      <p className="text-emerald-100/70 text-sm">{message}</p>
      <p className="text-emerald-100/40 text-xs">
        Reference: <code>{token.slice(0, 8)}…</code>
      </p>
    </main>
  );
}

