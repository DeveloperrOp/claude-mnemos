import { z } from "zod";

export const ProjectMapEntrySchema = z.object({
  name: z.string(),
  vault_root: z.string(),
  cwd_patterns: z.array(z.string()),
});
export type ProjectMapEntry = z.infer<typeof ProjectMapEntrySchema>;
