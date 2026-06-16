export const NORSTAT_COMPLETE_URL = "https://webs.norstatsurveys.com/z/Complete";
export const NORSTAT_SCREENED_URL = "https://webs.norstatsurveys.com/z/Screened";
export const NORSTAT_QUOTA_FULL_URL = "https://webs.norstatsurveys.com/z/QuotaFull";
export const NORSTAT_QUALITY_URL = "https://webs.norstatsurveys.com/z/Quality";

export function normalizeNorstatPid(value: string | null | undefined): string | null {
  const trimmed = (value ?? "").trim();
  if (!trimmed) return null;
  return trimmed.replace(/[^A-Za-z0-9_-]/g, "").slice(0, 120) || null;
}

export function norstatUserId(pid: string | null | undefined, fallback: string): string {
  const normalized = normalizeNorstatPid(pid);
  return normalized ? `norstat-${normalized}` : fallback;
}

export function norstatRedirectUrl(status: "Complete" | "Screened" | "QuotaFull" | "Quality", pid?: string | null): string {
  const base =
    status === "Complete"
      ? NORSTAT_COMPLETE_URL
      : status === "Screened"
        ? NORSTAT_SCREENED_URL
        : status === "QuotaFull"
          ? NORSTAT_QUOTA_FULL_URL
          : NORSTAT_QUALITY_URL;
  // Norstat status links must be requested exactly as configured. Participant
  // linkage remains in ViewTube PostgreSQL; do not append pid/query parameters.
  void pid;
  return base;
}
