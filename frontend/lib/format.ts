export function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "-";
  }
  return date.toLocaleString();
}

export function formatDate(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "-";
  }
  return date.toLocaleDateString();
}

export function formatScore(value: number | null | undefined): string {
  if (typeof value !== "number") {
    return "-";
  }
  return Number.isInteger(value) ? value.toString() : value.toFixed(1);
}

export function shortSha(value: string | null | undefined, length = 12): string {
  if (!value) {
    return "-";
  }
  return value.slice(0, length);
}
