const KST_TIME_ZONE = "Asia/Seoul";

export function parseBackendTimestamp(value: string): number {
  if (!value) {
    return Number.NaN;
  }

  const hasExplicitTimezone = /(?:Z|[+-]\d{2}:\d{2})$/i.test(value);
  const normalized = hasExplicitTimezone ? value : `${value}Z`;
  return new Date(normalized).getTime();
}

export function formatKSTDateTime(
  value: string,
  options?: Intl.DateTimeFormatOptions
): string {
  return new Intl.DateTimeFormat("ko-KR", {
    timeZone: KST_TIME_ZONE,
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    ...options,
  }).format(parseBackendTimestamp(value));
}

export function formatKSTDate(value: string): string {
  return new Intl.DateTimeFormat("ko-KR", {
    timeZone: KST_TIME_ZONE,
    year: "numeric",
    month: "numeric",
    day: "numeric",
  }).format(parseBackendTimestamp(value));
}
