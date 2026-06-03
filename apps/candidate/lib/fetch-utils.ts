export async function safeJson(
  res: Response
): Promise<{ detail?: string } | null> {
  try {
    return (await res.json()) as { detail?: string };
  } catch {
    return null;
  }
}
