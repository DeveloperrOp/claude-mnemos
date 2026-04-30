import slugifyLib from "@sindresorhus/slugify";

const MAX_LEN = 64;

/**
 * Derive a project slug from a display name.
 *
 * Output matches the backend PROJECT_NAME_PATTERN: ^[a-z0-9][a-z0-9_-]{0,63}$
 *
 * - empty input → empty output
 * - transliterates Unicode (Cyrillic etc.) via @sindresorhus/slugify
 * - normalises to lowercase, "-" separator
 * - truncates to 64 chars
 * - if result doesn't start with [a-z0-9], strips leading separator chars
 */
export function deriveSlug(input: string): string {
  if (!input.trim()) return "";
  let slug = slugifyLib(input, { lowercase: true, separator: "-" });
  // Strip leading non-alphanumeric (rare edge case).
  slug = slug.replace(/^[^a-z0-9]+/, "");
  // Truncate, then strip trailing "-" again (might be left after cut).
  slug = slug.slice(0, MAX_LEN).replace(/[-_]+$/, "");
  return slug;
}
