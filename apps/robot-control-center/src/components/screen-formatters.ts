export function formatMoment(value: string | null | undefined) {
  if (!value) {
    return "awaiting runtime payload";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString("en-GB", {
    hour12: false,
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function toneFromVerdict(verdict: string) {
  if (["block", "unsafe", "fail", "rejected", "unresolved", "disconnected"].includes(verdict)) {
    return "danger" as const;
  }
  if (["watch", "warn", "caution", "partially filled"].includes(verdict)) {
    return "warn" as const;
  }
  return "good" as const;
}

export function toneFromSeverity(severity: string) {
  if (["critical", "danger", "unsafe", "block", "fail", "unresolved"].includes(severity)) {
    return "danger" as const;
  }
  if (["warn", "warning", "caution"].includes(severity)) {
    return "warn" as const;
  }
  return "info" as const;
}

export function toneFromPipelineStatus(status: string) {
  if (status === "fail") {
    return "danger" as const;
  }
  if (status === "warn") {
    return "warn" as const;
  }
  if (status === "pass") {
    return "good" as const;
  }
  return "info" as const;
}

export function toneFromGuardStatus(status: string) {
  if (status === "block") {
    return "danger" as const;
  }
  if (status === "warn") {
    return "warn" as const;
  }
  if (status === "ok") {
    return "good" as const;
  }
  return "info" as const;
}

export function formatOptionalNumber(value: number | null | undefined, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "Unavailable";
  }
  return new Intl.NumberFormat("en-GB", {
    maximumFractionDigits: digits,
  }).format(value);
}
