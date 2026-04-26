import { notFound, redirect } from "next/navigation";
import { ApiError, fetchAssignment } from "@/lib/api";

type Params = { token: string };

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
