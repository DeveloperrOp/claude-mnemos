import { z } from "zod";

export const ProjectMapEntrySchema = z.object({
  name: z.string(),
  display_name: z.string().nullable().default(null),
  vault_root: z.string(),
  cwd_patterns: z.array(z.string()),
});
export type ProjectMapEntry = z.infer<typeof ProjectMapEntrySchema>;
