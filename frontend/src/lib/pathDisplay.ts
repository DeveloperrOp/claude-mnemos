export function lastSegment(p: string): string {
  return p.replace(/[\\/]+$/, "").split(/[\\/]/).slice(-1)[0] ?? p;
}

export function humanize(name: string): string {
  return name
    .replace(/[-_]+/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(" ");
}
