import { ApiError } from "@repo/api-client";
import { redirect } from "next/navigation";

export type ActionResult = { ok: true } | { ok: false; error: string };

/** Server-action wrapper: returns ActionResult on ApiError; rethrows
 * everything else (including Next's redirect sentinel). */
export async function runApiAction(
  fn: () => Promise<unknown>
): Promise<ActionResult> {
  try {
    await fn();
    return { ok: true };
  } catch (e) {
    if (e instanceof ApiError) {
      return { ok: false, error: e.message };
    }
    throw e;
  }
}

/** Page data loader: returns data + error string. Rethrows non-ApiError so
 * the framework's error boundary still fires for unexpected failures. */
export async function loadOrApiError<T>(
  fn: () => Promise<T>
): Promise<{ data: T | null; error: string | null }> {
  try {
    return { data: await fn(), error: null };
  } catch (e) {
    if (e instanceof ApiError) {
      return { data: null, error: e.message };
    }
    throw e;
  }
}

/** Redirect-on-result server-action helper. Always navigates: to
 * `${basePath}?ok=<successMessage>` on success or
 * `${basePath}?error=<message>` on ApiError. Non-ApiErrors propagate.
 * `successMessage` can be a function of the resolved value when the message
 * needs to include data from the response. */
export async function redirectOnApi<T>(
  fn: () => Promise<T>,
  basePath: string,
  successMessage: string | ((result: T) => string)
): Promise<never> {
  let result: T;
  try {
    result = await fn();
  } catch (e) {
    if (e instanceof ApiError) {
      redirect(`${basePath}?error=${encodeURIComponent(e.message)}`);
    }
    throw e;
  }
  const msg =
    typeof successMessage === "function"
      ? successMessage(result)
      : successMessage;
  redirect(`${basePath}?ok=${encodeURIComponent(msg)}`);
}
