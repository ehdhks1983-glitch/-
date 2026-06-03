import { Badge } from "@/components/ui/badge";
import type { LicenseStatus } from "@/lib/types";
import { STATUS_LABELS } from "@/lib/utils";

export function StatusBadge({ status }: { status: LicenseStatus }) {
  const variant =
    status === "active" ? "success" : status === "revoked" ? "destructive" : "secondary";
  return <Badge variant={variant}>{STATUS_LABELS[status]}</Badge>;
}
