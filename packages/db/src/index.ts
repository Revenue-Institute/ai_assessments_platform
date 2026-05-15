import { createClient, type SupabaseClient } from "@supabase/supabase-js";

export type Database = Record<string, unknown>;

export type AssessmentsClient = SupabaseClient<Database>;

interface ServerClientArgs {
  serviceRoleKey: string;
  url: string;
}

export function createServerClient({
  url,
  serviceRoleKey,
}: ServerClientArgs): AssessmentsClient {
  return createClient<Database>(url, serviceRoleKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
}

interface AnonClientArgs {
  anonKey: string;
  url: string;
}

export function createAnonClient({
  url,
  anonKey,
}: AnonClientArgs): AssessmentsClient {
  return createClient<Database>(url, anonKey);
}
