import { describe, expect, it } from "vitest";
import { formatBytes, formatStatus } from "@/lib/utils";

describe("utils", () => {
  it("formats bytes", () => {
    expect(formatBytes(500)).toBe("500 B");
    expect(formatBytes(2048)).toBe("2.0 KB");
  });

  it("formats status", () => {
    expect(formatStatus("ocr_complete")).toBe("Ocr Complete");
  });
});
