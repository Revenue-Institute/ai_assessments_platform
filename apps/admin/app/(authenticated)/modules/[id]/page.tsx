import { notFound, redirect } from "next/navigation";
import {
  ApiError,
  archiveModule,
  getModule,
  publishModule,
} from "@/lib/api";
import { Header } from "../../components/header";

export const dynamic = "force-dynamic";

type Params = Promise<{ id: string }>;
type SearchParams = Promise<{ error?: string; ok?: string }>;

export default async function ModuleDetailPage({
  params,
  searchParams,
}: {
  params: Params;
  searchParams: SearchParams;
}) {
  const { id } = await params;
  const { error, ok } = await searchParams;

  let detail: Awaited<ReturnType<typeof getModule>>;
  try {
    detail = await getModule(id);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  async function publish(): Promise<void> {
    "use server";
    try {
      await publishModule(id);
      redirect(`/modules/${id}?ok=${encodeURIComponent("Published.")}`);
    } catch (e) {
      if (e instanceof ApiError) {
        redirect(`/modules/${id}?error=${encodeURIComponent(e.message)}`);
      }
      throw e;
    }
  }

  async function archive(): Promise<void> {
    "use server";
    try {
      await archiveModule(id);
      redirect(`/modules/${id}?ok=${encodeURIComponent("Archived.")}`);
    } catch (e) {
      if (e instanceof ApiError) {
        redirect(`/modules/${id}?error=${encodeURIComponent(e.message)}`);
      }
      throw e;
    }
  }

  return (
    <>
      <Header page={detail.title} pages={["Modules"]} />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        {(error || ok) && (
          <p
            className={`rounded px-3 py-2 text-sm ${
              error
                ? "border border-red-900/50 bg-red-950/30 text-red-200"
                : "border border-emerald-900/50 bg-emerald-950/30 text-emerald-200"
            }`}
          >
            {error || ok}
          </p>
        )}

        <section className="grid grid-cols-2 gap-4 rounded-xl border border-border/50 bg-muted/30 p-4">
          <Stat label="Status" value={detail.status} />
          <Stat label="Slug" value={detail.slug} />
          <Stat label="Domain" value={detail.domain} />
          <Stat label="Difficulty" value={detail.difficulty} />
          <Stat label="Duration" value={`${detail.target_duration_minutes} min`} />
          <Stat label="Questions" value={String(detail.question_count)} />
        </section>

        {detail.description && (
          <section className="rounded-xl border border-border/50 bg-muted/20 p-4 text-sm">
            {detail.description}
          </section>
        )}

        <section className="rounded-xl border border-border/50 bg-muted/20 p-4">
          <h2 className="mb-2 font-medium text-sm">Questions</h2>
          {detail.questions.length === 0 ? (
            <p className="text-muted-foreground text-sm">
              No questions yet. Use the seed script (
              <code className="rounded bg-muted px-1">bun --filter api seed</code>
              ) or wait for the Phase 2 generator.
            </p>
          ) : (
            <ol className="space-y-2 text-sm">
              {detail.questions.map((q, i) => (
                <li className="rounded border border-border/40 bg-background/30 p-3" key={q.id}>
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-medium">
                      {i + 1}. {q.type}
                    </p>
                    <p className="text-muted-foreground text-xs">
                      {q.max_points} pts
                    </p>
                  </div>
                  <p className="mt-1 line-clamp-2 text-muted-foreground text-xs">
                    {q.prompt_template}
                  </p>
                </li>
              ))}
            </ol>
          )}
        </section>

        <section className="flex gap-2">
          {detail.status === "draft" && (
            <form action={publish}>
              <button
                className="rounded bg-emerald-500 px-3 py-2 text-emerald-950 text-sm hover:bg-emerald-400"
                type="submit"
              >
                Publish
              </button>
            </form>
          )}
          {detail.status !== "archived" && (
            <form action={archive}>
              <button
                className="rounded border border-border/50 bg-background px-3 py-2 text-sm hover:bg-muted"
                type="submit"
              >
                Archive
              </button>
            </form>
          )}
        </section>
      </div>
    </>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-muted-foreground text-xs uppercase tracking-wide">
        {label}
      </p>
      <p className="font-medium text-sm">{value}</p>
    </div>
  );
}
