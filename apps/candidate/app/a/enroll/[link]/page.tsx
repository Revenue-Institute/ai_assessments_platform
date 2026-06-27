import { headers } from "next/headers";
import { notFound, redirect } from "next/navigation";
import { NoticeView } from "@/app/components/notice-view";
import { ApiError, fetchPublicAssessment, registerPublic } from "@/lib/api";
import { EnrollForm } from "./enroll-form";

interface Params {
  link: string;
}
type SearchParams = Promise<{ error?: string }>;

function durationLabel(minutes: number): string {
  if (minutes <= 0) {
    return "Self-paced";
  }
  return `About ${minutes} min`;
}

export default async function EnrollPage({
  params,
  searchParams,
}: {
  params: Promise<Params>;
  searchParams: SearchParams;
}) {
  const { link } = await params;
  const { error } = await searchParams;
  if (!link || link.length < 8) {
    notFound();
  }

  let assessment: Awaited<ReturnType<typeof fetchPublicAssessment>>;
  try {
    assessment = await fetchPublicAssessment(link);
  } catch (e) {
    if (e instanceof ApiError) {
      return <NoticeView body={e.message} title="Link unavailable" />;
    }
    throw e;
  }

  async function register(formData: FormData) {
    "use server";
    const fullName = String(formData.get("full_name") ?? "").trim();
    const email = String(formData.get("email") ?? "").trim();
    const consent = formData.get("consent") === "on";
    const back = (message: string) =>
      redirect(`/a/enroll/${link}?error=${encodeURIComponent(message)}`);

    if (!(fullName && email)) {
      back("Please enter your name and email.");
    }
    if (!consent) {
      back("Please agree to begin the assessment.");
    }

    const headerStore = await headers();
    const forwardedIp =
      headerStore.get("x-forwarded-for") ??
      headerStore.get("x-real-ip") ??
      undefined;

    let result: Awaited<ReturnType<typeof registerPublic>>;
    try {
      result = await registerPublic(
        link,
        { full_name: fullName, email, consent },
        forwardedIp ?? undefined
      );
    } catch (e) {
      if (e instanceof ApiError) {
        back(e.message);
        return;
      }
      throw e;
    }
    redirect(`/a/${result.token}`);
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-xl animate-reveal flex-col justify-center gap-6 px-6 py-12">
      <header className="space-y-2">
        <p className="eyebrow-label">Revenue Institute</p>
        <h1 className="font-semibold text-3xl">{assessment.title}</h1>
        {assessment.description && (
          <p className="text-muted-foreground text-sm">
            {assessment.description}
          </p>
        )}
      </header>

      <dl className="grid grid-cols-3 gap-3 rounded-xl border border-border/50 bg-muted/20 p-4 text-center">
        <div>
          <dt className="text-muted-foreground text-xs">Modules</dt>
          <dd className="font-semibold text-lg">{assessment.module_count}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground text-xs">Questions</dt>
          <dd className="font-semibold text-lg">{assessment.question_count}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground text-xs">Time</dt>
          <dd className="font-semibold text-lg">
            {durationLabel(assessment.total_duration_minutes)}
          </dd>
        </div>
      </dl>

      <section className="space-y-4 rounded-xl border border-border/50 bg-muted/20 p-4">
        <p className="text-muted-foreground text-sm">
          Enter your details to begin. We use your email only to send your
          assessment link so you can resume if needed.
        </p>
        <EnrollForm action={register} error={error} />
      </section>
    </main>
  );
}
