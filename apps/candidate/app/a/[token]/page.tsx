import { headers } from "next/headers";
import { notFound, redirect } from "next/navigation";
import { ApiError, fetchAssignment, postConsent } from "@/lib/api";
import { ErrorView } from "@/app/components/error-view";
import { NoticeView } from "@/app/components/notice-view";
import { AssignmentCard } from "./components/assignment-card";
import { ConsentForm } from "./components/consent-form";
import { MonitoringDisclosure } from "./components/monitoring-disclosure";

interface Params {
  token: string;
}
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
      return <ErrorView message={error.message} status={error.status} token={token} />;
    }
    throw error;
  }

  if (assignment.status === "in_progress") {
    redirect(`/a/${token}/in-progress`);
  }

  if (assignment.status === "completed") {
    return (
      <NoticeView
        body="This assessment has already been submitted. Thanks for completing it."
        title="Already submitted"
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
    <main className="mx-auto flex min-h-screen max-w-2xl animate-reveal flex-col gap-6 px-6 py-12">
      <header className="space-y-2">
        <p className="eyebrow-label">Revenue Institute</p>
        <h1 className="font-semibold text-3xl">{assignment.module.title}</h1>
        <p className="text-muted-foreground text-sm">
          {assignment.module.description}
        </p>
      </header>

      <AssignmentCard assignment={assignment} />
      <MonitoringDisclosure />
      <ConsentForm action={handleConsent} error={consentError} />
    </main>
  );
}
