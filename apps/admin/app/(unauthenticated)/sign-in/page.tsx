import { redirect } from "next/navigation";

import { signIn } from "./actions";
import { SignInForm } from "./sign-in-form";

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

  return <SignInForm action={handleSignIn} error={error} next={next} />;
}
