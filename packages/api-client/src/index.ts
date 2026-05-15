export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

const TRAILING_SLASH_RE = /\/$/;

export interface CallApiConfig {
  baseUrl: string;
  getAuthHeader?: () => Promise<Record<string, string>>;
}

export type CallApi = <T>(path: string, init?: RequestInit) => Promise<T>;

export function createCallApi(config: CallApiConfig): CallApi {
  return async function callApi<T>(
    path: string,
    init?: RequestInit
  ): Promise<T> {
    const url = `${config.baseUrl.replace(TRAILING_SLASH_RE, "")}${path}`;
    const auth = config.getAuthHeader ? await config.getAuthHeader() : {};
    const res = await fetch(url, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...auth,
        ...(init?.headers ?? {}),
      },
      cache: "no-store",
    });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = await res.json();
        if (typeof body?.detail === "string") {
          detail = body.detail;
        }
      } catch {
        /* fall through */
      }
      throw new ApiError(detail, res.status);
    }
    if (res.status === 204) {
      return undefined as T;
    }
    return (await res.json()) as T;
  };
}
