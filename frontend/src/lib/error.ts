import axios from "axios";

/**
 * Pull a human-readable message out of an axios error.
 *
 * Backend convention (post-v0.0.37): all HTTPException raises include
 *   { detail: { error: "<machine_code>", message: "<Russian sentence>" } }
 * so the frontend toast shows something the user can act on, not just
 * "Request failed with status code 500".
 */
export function extractApiError(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail;
    // Preferred shape (v0.0.37+): `{ message: "..." }`
    if (detail && typeof detail === "object" && typeof detail.message === "string") {
      return detail.message;
    }
    // Old shape: plain string detail
    if (typeof detail === "string") return detail;
    // Last resort: the underlying object's `error` machine code
    if (detail && typeof detail === "object" && typeof detail.error === "string") {
      return detail.error;
    }
    return err.message;
  }
  if (err instanceof Error) return err.message;
  return String(err);
}
