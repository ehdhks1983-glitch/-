import { useAuth } from "@/store/auth";
import type {
  ActivationListItem,
  BulkIssueResponse,
  License,
  LicenseDetail,
  LicenseIssueResponse,
  Page,
  PlanType,
  Product,
  ProductWithSecret,
  StatsSummary,
  TokenResponse,
  User,
} from "@/lib/types";

const BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";

export class ApiError extends Error {
  code: string;
  status: number;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

function buildHeaders(init: RequestInit, token: string | null): Headers {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return headers;
}

async function rawFetch(
  path: string,
  init: RequestInit,
  token: string | null
): Promise<Response> {
  return fetch(`${BASE}${path}`, { ...init, headers: buildHeaders(init, token) });
}

async function parse<T>(res: Response): Promise<T> {
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    if (res.status === 401) useAuth.getState().logout();
    throw new ApiError(
      res.status,
      data?.error_code ?? "error",
      data?.message ?? res.statusText
    );
  }
  return data as T;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const { accessToken, refreshToken, setAccessToken } = useAuth.getState();
  let res = await rawFetch(path, init, accessToken);

  if (res.status === 401 && refreshToken && !path.startsWith("/auth/")) {
    const refreshed = await rawFetch(
      "/auth/refresh",
      { method: "POST", body: JSON.stringify({ refresh_token: refreshToken }) },
      null
    );
    if (refreshed.ok) {
      const data = (await refreshed.json()) as { access_token: string };
      setAccessToken(data.access_token);
      res = await rawFetch(path, init, data.access_token);
    }
  }
  return parse<T>(res);
}

function jsonBody(value: unknown): string {
  return JSON.stringify(value);
}

export interface IssuePayload {
  product_id: number;
  plan_type: PlanType;
  duration_days?: number | null;
  customer_name?: string | null;
  customer_contact?: string | null;
  memo?: string | null;
  max_hwid_count?: number | null;
}

export interface LicenseFilters {
  product_id?: number;
  status?: string;
  search?: string;
  page?: number;
  page_size?: number;
}

function query(params: Record<string, unknown>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export const api = {
  // auth
  login: (email: string, password: string) =>
    request<TokenResponse>("/auth/login", {
      method: "POST",
      body: jsonBody({ email, password }),
    }),
  me: () => request<User>("/auth/me"),

  // products
  listProducts: (includeInactive = false) =>
    request<Product[]>(`/products${query({ include_inactive: includeInactive })}`),
  getProduct: (id: number) => request<ProductWithSecret>(`/products/${id}`),
  createProduct: (body: {
    code: string;
    name: string;
    prefix: string;
    description?: string | null;
    max_hwid_count?: number;
  }) =>
    request<ProductWithSecret>("/products", {
      method: "POST",
      body: jsonBody(body),
    }),
  rotateSecret: (id: number) =>
    request<ProductWithSecret>(`/products/${id}/rotate-secret`, { method: "POST" }),

  // licenses
  listLicenses: (filters: LicenseFilters = {}) =>
    request<Page<License>>(`/licenses${query(filters as Record<string, unknown>)}`),
  getLicense: (id: number) => request<LicenseDetail>(`/licenses/${id}`),
  issueLicense: (body: IssuePayload) =>
    request<LicenseIssueResponse>("/licenses/issue", {
      method: "POST",
      body: jsonBody(body),
    }),
  issueBulk: (body: IssuePayload & { count: number }) =>
    request<BulkIssueResponse>("/licenses/issue-bulk", {
      method: "POST",
      body: jsonBody(body),
    }),
  revokeLicense: (id: number) =>
    request<License>(`/licenses/${id}/revoke`, { method: "POST" }),
  extendLicense: (id: number, days: number) =>
    request<License>(`/licenses/${id}/extend`, {
      method: "POST",
      body: jsonBody({ days }),
    }),
  updateMemo: (id: number, memo: string | null) =>
    request<License>(`/licenses/${id}`, {
      method: "PATCH",
      body: jsonBody({ memo }),
    }),
  releaseHwid: (licenseId: number, activationId: number) =>
    request<{ ok: boolean }>(
      `/licenses/${licenseId}/activations/${activationId}`,
      { method: "DELETE" }
    ),

  // activations
  listActivations: (conflictsOnly = false, page = 1, pageSize = 100) =>
    request<Page<ActivationListItem>>(
      `/activations${query({ conflicts_only: conflictsOnly, page, page_size: pageSize })}`
    ),

  // stats
  statsSummary: () => request<StatsSummary>("/stats/summary"),

  // users
  listUsers: () => request<User[]>("/users"),
  createUser: (body: {
    email: string;
    password: string;
    name?: string | null;
    role: string;
  }) => request<User>("/users", { method: "POST", body: jsonBody(body) }),
  updateUser: (
    id: number,
    body: { name?: string; role?: string; is_active?: boolean; password?: string }
  ) => request<User>(`/users/${id}`, { method: "PATCH", body: jsonBody(body) }),
};

/** Bulk issue as CSV blob (separate from JSON request flow). */
export async function issueBulkCsv(body: IssuePayload & { count: number }): Promise<Blob> {
  const { accessToken } = useAuth.getState();
  const res = await rawFetch(
    "/licenses/issue-bulk?format=csv",
    { method: "POST", body: jsonBody(body) },
    accessToken
  );
  if (!res.ok) throw new ApiError(res.status, "error", "CSV 발급 실패");
  return res.blob();
}
