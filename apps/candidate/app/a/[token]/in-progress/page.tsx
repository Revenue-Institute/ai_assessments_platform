import { notFound } from "next/navigation";
import { ApiError, fetchAssignment } from "@/lib/api";

type Params = { token: string };

export default async function InProgressPage({
  params,
}: {
  params: Promise<Params>;
}) {
  const { token } = await params;
  if (!token || token.length < 16) {
    notFound();
  }

  try {
    const assignment = await fetchAssignment(token);
    if (assignment.status !== "in_progress") {
      // If the assignment is back to pending or completed, send the user
      // to the landing page which knows how to handle each state.
      return (
        <main className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-3 px-6 text-center">
          <h1 className="font-semibold text-2xl">
            Status: {assignment.status}
          </h1>
          <p className="text-emerald-100/70 text-sm">
            <a className="underline" href={`/a/${token}`}>
              Return to the assessment landing page
            </a>
          </p>
        </main>
      );
    }

    const deadline = new Date(assignment.expires_at);

    return (
      <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 px-6 py-12">
        <header className="space-y-2">
          <p className="text-emerald-300/70 text-xs uppercase tracking-widest">
            Assessment in progress
          </p>
          <h1 className="font-semibold text-3xl">
            {assignment.module.title}
          </h1>
          <p className="text-emerald-100/70 text-sm">
            Candidate: {assignment.subject.full_name}
          </p>
        </header>

        <section className="rounded-lg border border-emerald-900/60 bg-emerald-950/40 p-5 text-sm">
          <h2 className="font-medium">Question runner is wiring up.</h2>
          <p className="mt-1 text-emerald-100/70">
            The randomizer, server-authoritative timer, and per-type renderers
            (mcq, code, n8n, notebook, diagram, sql) ship in Phase 1. The
            consent step has been recorded and the assignment is now in
            progress on the server.
          </p>
          <dl className="mt-4 grid grid-cols-2 gap-3 text-emerald-100/80">
            <div>
              <dt className="text-emerald-300/60 text-xs uppercase tracking-wide">
                Questions
              </dt>
              <dd>{assignment.module.question_count}</dd>
            </div>
            <div>
              <dt className="text-emerald-300/60 text-xs uppercase tracking-wide">
                Time limit
              </dt>
              <dd>{assignment.module.target_duration_minutes} min</dd>
            </div>
            <div className="col-span-2">
              <dt className="text-emerald-300/60 text-xs uppercase tracking-wide">
                Link expires
              </dt>
              <dd>{deadline.toLocaleString()}</dd>
            </div>
          </dl>
        </section>
      </main>
    );
  } catch (error) {
    if (error instanceof ApiError) {
      return (
        <main className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-3 px-6 text-center">
          <h1 className="font-semibold text-2xl">
            {error.status === 410 ? "Link expired" : "Something went wrong"}
          </h1>
          <p className="text-emerald-100/70 text-sm">{error.message}</p>
        </main>
      );
    }
    throw error;
  }
}
