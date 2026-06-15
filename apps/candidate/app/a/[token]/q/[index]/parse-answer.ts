import { redirect } from "next/navigation";

export function parseSubmittedAnswer(
  formData: FormData,
  token: string,
  idx: number
) {
  return (
    parseMultiSelectAnswer(formData, token, idx) ??
    parseScenarioAnswer(formData, token, idx) ??
    parseScalarAnswer(formData, token, idx)
  );
}

function parseMultiSelectAnswer(
  formData: FormData,
  token: string,
  idx: number
) {
  const checkedIndices = formData.getAll("answer_indices");
  if (checkedIndices.length === 0) {
    return null;
  }
  const ints = checkedIndices
    .map((v) => Number.parseInt(String(v), 10))
    .filter((n) => !Number.isNaN(n))
    .sort((a, b) => a - b);
  if (ints.length === 0) {
    redirectWithSubmitError(token, idx, "Please select at least one answer.");
  }
  return { selected_indices: ints };
}

function parseScenarioAnswer(formData: FormData, token: string, idx: number) {
  const responses: Record<string, string> = {};
  for (const [key, value] of formData.entries()) {
    if (key.startsWith("scenario_part:") && typeof value === "string") {
      responses[key.slice("scenario_part:".length)] = value.trim();
    }
  }
  if (Object.keys(responses).length === 0) {
    return null;
  }
  if (Object.values(responses).every((value) => value.length === 0)) {
    redirectWithSubmitError(token, idx, "Please provide an answer.");
  }
  return { responses };
}

function parseScalarAnswer(formData: FormData, token: string, idx: number) {
  const raw = formData.get("answer");
  if (typeof raw !== "string") {
    return raw;
  }
  const trimmed = raw.trim();
  if (trimmed.length === 0) {
    redirectWithSubmitError(token, idx, "Please provide an answer.");
  }
  if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
    try {
      return JSON.parse(trimmed) as unknown;
    } catch {
      return { text: trimmed };
    }
  }
  return parseLegacySelectedAnswer(formData, trimmed);
}

function parseLegacySelectedAnswer(formData: FormData, selected: string) {
  const selectedIndex = formData.get("answer_index");
  if (typeof selectedIndex !== "string" || selectedIndex.length === 0) {
    return { text: selected };
  }
  const parsedIndex = Number.parseInt(selectedIndex, 10);
  return Number.isNaN(parsedIndex)
    ? { selected }
    : { selected_index: parsedIndex, selected };
}

function redirectWithSubmitError(token: string, idx: number, message: string) {
  redirect(`/a/${token}/q/${idx}?error=${encodeURIComponent(message)}`);
}
