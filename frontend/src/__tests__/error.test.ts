import { describe, it, expect } from "vitest";
import { AxiosError, AxiosHeaders } from "axios";
import { extractApiError } from "../lib/error";

describe("extractApiError", () => {
  it("returns response.data.detail for axios error with detail", () => {
    const err = new AxiosError(
      "Request failed",
      "ERR_BAD_REQUEST",
      undefined,
      undefined,
      {
        status: 400,
        statusText: "Bad Request",
        data: { detail: "Snapshot already exists" },
        headers: {},
        config: { headers: new AxiosHeaders() },
      },
    );
    expect(extractApiError(err)).toBe("Snapshot already exists");
  });

  it("falls back to err.message for axios error without detail", () => {
    const err = new AxiosError("Network Error");
    expect(extractApiError(err)).toBe("Network Error");
  });

  it("returns Error.message for plain Error", () => {
    expect(extractApiError(new Error("boom"))).toBe("boom");
  });

  it("stringifies unknown values", () => {
    expect(extractApiError("oops")).toBe("oops");
    expect(extractApiError(42)).toBe("42");
  });
});
