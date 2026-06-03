import { notFound, redirect } from "next/navigation";
import { ApiError, fetchAssignment } from "@/lib/api";
import { ErrorView } from "@/app/components/error-view";

interface Params {
  token: string;
}

export default async function InProgressGate({
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
    if (assignment.status === "in_progress") {
      redirect(`/a/${token}/q/0`);
    }
    if (assignment.status === "completed") {
      redirect(`/a/${token}/done`);
    }
    redirect(`/a/${token}`);
  } catch (error) {
    if (error instanceof ApiError) {
      return <ErrorView message={error.message} status={error.status} />;
    }
    throw error;
  }
}
