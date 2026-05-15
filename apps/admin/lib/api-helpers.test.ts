import { ApiError } from "@repo/api-client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { loadOrApiError, runApiAction } from "./api-helpers";

vi.mock("next/navigation", () => ({
  redirect: (url: string) => {
    throw new Error(`NEXT_REDIRECT:${url}`);
  },
}));

// Mock the admin env so api.ts can be imported without runtime validation.
vi.mock("@/env", () => ({
  env: { INTERNAL_API_URL: "http://api.test" },
}));

// Mock the supabase server client so authHeader returns a fixed bearer.
vi.mock("@/lib/supabase/server", () => ({
  createSupabaseServerClient: async () => ({
    auth: {
      getSession: async () => ({
        data: { session: { access_token: "test-token" } },
      }),
    },
  }),
}));

describe("runApiAction", () => {
  it("returns ok on success", async () => {
    const result = await runApiAction(() => Promise.resolve("anything"));
    expect(result).toEqual({ ok: true });
  });

  it("returns ok=false with the message on ApiError", async () => {
    const result = await runApiAction(() =>
      Promise.reject(new ApiError("Something broke", 422))
    );
    expect(result).toEqual({ ok: false, error: "Something broke" });
  });

  it("rethrows non-ApiError so framework error boundaries fire", async () => {
    const boom = new Error("unexpected");
    await expect(runApiAction(() => Promise.reject(boom))).rejects.toBe(boom);
  });
});

describe("loadOrApiError", () => {
  it("returns data on success", async () => {
    const result = await loadOrApiError(() => Promise.resolve([1, 2, 3]));
    expect(result).toEqual({ data: [1, 2, 3], error: null });
  });

  it("returns error string on ApiError", async () => {
    const result = await loadOrApiError(() =>
      Promise.reject(new ApiError("Backend down", 503))
    );
    expect(result).toEqual({ data: null, error: "Backend down" });
  });

  it("rethrows non-ApiError", async () => {
    const boom = new Error("boom");
    await expect(loadOrApiError(() => Promise.reject(boom))).rejects.toBe(boom);
  });
});

// API URL/shape coverage. Each call is verified by intercepting global.fetch
// and inspecting the request URL. Bodies are echoed back as JSON so the
// callApi helper's response decoder runs end-to-end.

interface CapturedRequest {
  body?: string;
  method: string;
  url: string;
}

function installFetchSpy(): { calls: CapturedRequest[] } {
  const calls: CapturedRequest[] = [];
  const spy = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    calls.push({
      method: (init?.method ?? "GET").toUpperCase(),
      url,
      body: typeof init?.body === "string" ? init.body : undefined,
    });
    return Promise.resolve(
      new Response("{}", {
        status: 200,
        headers: { "content-type": "application/json" },
      })
    );
  });
  vi.stubGlobal("fetch", spy);
  return { calls };
}

describe("admin lib/api request shapes", () => {
  let calls: CapturedRequest[];

  beforeEach(() => {
    ({ calls } = installFetchSpy());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("cohortHeatmap passes role, start_date, end_date in the query string", async () => {
    const { cohortHeatmap } = await import("./api");
    await cohortHeatmap({
      type: "candidate",
      role: "growth-manager",
      start_date: "2026-01-01",
      end_date: "2026-03-31",
      domain: "marketing",
      days: 90,
    });

    expect(calls).toHaveLength(1);
    const call = calls[0];
    if (!call) {
      throw new Error("expected exactly one fetch call");
    }
    expect(call.method).toBe("GET");
    const url = new URL(call.url);
    expect(url.pathname).toBe("/api/cohorts/heatmap");
    expect(url.searchParams.get("type")).toBe("candidate");
    expect(url.searchParams.get("role")).toBe("growth-manager");
    expect(url.searchParams.get("start_date")).toBe("2026-01-01");
    expect(url.searchParams.get("end_date")).toBe("2026-03-31");
    expect(url.searchParams.get("domain")).toBe("marketing");
    expect(url.searchParams.get("days")).toBe("90");
  });

  it("competencyDistribution sends subject_id and assignment_id in the query string", async () => {
    const { competencyDistribution } = await import("./api");
    await competencyDistribution({
      competency_id: "hubspot.workflows",
      subject_id: "subj-1",
      assignment_id: "asg-1",
      type: "employee",
    });

    expect(calls).toHaveLength(1);
    const call = calls[0];
    if (!call) {
      throw new Error("expected exactly one fetch call");
    }
    const url = new URL(call.url);
    expect(url.pathname).toBe("/api/cohorts/distribution");
    expect(url.searchParams.get("competency_id")).toBe("hubspot.workflows");
    expect(url.searchParams.get("subject_id")).toBe("subj-1");
    expect(url.searchParams.get("assignment_id")).toBe("asg-1");
    expect(url.searchParams.get("type")).toBe("employee");
  });

  it("getSeriesTrend uses /api/series/{id}/trend", async () => {
    const { getSeriesTrend } = await import("./api");
    await getSeriesTrend("series-42");

    expect(calls).toHaveLength(1);
    const call = calls[0];
    if (!call) {
      throw new Error("expected exactly one fetch call");
    }
    expect(call.method).toBe("GET");
    expect(call.url).toBe("http://api.test/api/series/series-42/trend");
  });

  it("listAdminUsers GETs /api/users", async () => {
    const { listAdminUsers } = await import("./api");
    await listAdminUsers();

    expect(calls).toHaveLength(1);
    const call = calls[0];
    if (!call) {
      throw new Error("expected exactly one fetch call");
    }
    expect(call.method).toBe("GET");
    expect(call.url).toBe("http://api.test/api/users");
  });

  it("patchAdminUser PATCHes /api/users/{id} with the new role", async () => {
    const { patchAdminUser } = await import("./api");
    await patchAdminUser("user-7", { role: "reviewer" });

    expect(calls).toHaveLength(1);
    const call = calls[0];
    if (!call) {
      throw new Error("expected exactly one fetch call");
    }
    expect(call.method).toBe("PATCH");
    expect(call.url).toBe("http://api.test/api/users/user-7");
    expect(call.body).toBe(JSON.stringify({ role: "reviewer" }));
  });

  it("generationRunEventsUrl returns the proxied SSE path", async () => {
    const { generationRunEventsUrl } = await import("./api");
    expect(generationRunEventsUrl("run-123")).toBe(
      "/api/generation-events?run_id=run-123"
    );
    expect(generationRunEventsUrl("run with spaces")).toBe(
      "/api/generation-events?run_id=run%20with%20spaces"
    );
  });
});
