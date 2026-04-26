import { createClient, type SupabaseClient } from "@supabase/supabase-js";

export type Database = Record<string, unknown>;

export type AssessmentsClient = SupabaseClient<Database>;

type ServerClientArgs = {
  url: string;
  serviceRoleKey: string;
};

export function createServerClient({
  url,
  serviceRoleKey,
}: ServerClientArgs): AssessmentsClient {
  return createClient<Database>(url, serviceRoleKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
}

type AnonClientArgs = {
  url: string;
  anonKey: string;
};

export function createAnonClient({
  url,
  anonKey,
}: AnonClientArgs): AssessmentsClient {
  return createClient<Database>(url, anonKey);
}
