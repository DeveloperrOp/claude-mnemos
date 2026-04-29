import { z } from "zod";

export const ClaudeCliAuthSchema = z.object({
  installed: z.boolean(),
  authenticated: z.boolean(),
  binary_path: z.string().nullable().default(null),
});
export type ClaudeCliAuth = z.infer<typeof ClaudeCliAuthSchema>;
