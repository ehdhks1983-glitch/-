export type Role = "admin" | "staff";
export type PlanType = "trial_7" | "monthly_30" | "unlimited" | "custom";
export type LicenseStatus = "active" | "revoked" | "expired";

export interface User {
  id: number;
  email: string;
  name: string | null;
  role: Role;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface Product {
  id: number;
  code: string;
  name: string;
  prefix: string;
  description: string | null;
  is_active: boolean;
  max_hwid_count: number;
  created_at: string;
}

export interface ProductWithSecret extends Product {
  secret_key: string;
}

export interface License {
  id: number;
  key_prefix: string;
  product_id: number;
  product_code: string | null;
  plan_type: PlanType;
  duration_days: number | null;
  issued_at: string;
  expires_at: string | null;
  status: LicenseStatus;
  customer_name: string | null;
  customer_contact: string | null;
  memo: string | null;
  hwid_used: number;
  hwid_max: number;
  issued_by_user_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface Activation {
  id: number;
  hwid: string;
  activated_at: string;
  last_seen_at: string;
  ip_address: string | null;
  client_version: string | null;
  is_active: boolean;
}

export interface LicenseDetail extends License {
  activations: Activation[];
}

export interface LicenseIssueResponse {
  license_id: number;
  raw_key: string;
  key_prefix: string;
  product_id: number;
  plan_type: PlanType;
  expires_at: string | null;
}

export interface BulkIssueResponse {
  count: number;
  keys: LicenseIssueResponse[];
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface ProductDistribution {
  product_id: number;
  product_code: string;
  product_name: string;
  active_count: number;
}

export interface StatsSummary {
  total_active: number;
  expiring_soon: number;
  issued_today: number;
  active_hwids: number;
  by_product: ProductDistribution[];
}

export interface ActivationListItem {
  id: number;
  license_id: number;
  license_key_prefix: string;
  product_id: number;
  product_code: string | null;
  hwid: string;
  activated_at: string;
  last_seen_at: string;
  ip_address: string | null;
  client_version: string | null;
  is_active: boolean;
  is_conflict: boolean;
}

export type AuditEventType =
  | "issue"
  | "verify_success"
  | "verify_fail"
  | "revoke"
  | "extend"
  | "hwid_register"
  | "hwid_conflict"
  | "hwid_release"
  | "login";

export interface AuditLog {
  id: number;
  event_type: AuditEventType;
  user_id: number | null;
  hwid: string | null;
  ip_address: string | null;
  detail: Record<string, unknown> | null;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}
