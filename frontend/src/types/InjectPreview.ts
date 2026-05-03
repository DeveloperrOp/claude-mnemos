import { z } from "zod";

export const InjectPreviewPageSchema = z.object({
  path: z.string(),
  slug: z.string(),
  score: z.number(),
  included: z.boolean(),
});
export type InjectPreviewPage = z.infer<typeof InjectPreviewPageSchema>;

export const InjectPreviewSchema = z.object({
  tokens_estimate: z.number().int().nonnegative(),
  limit: z.number().int().positive(),
  ratio: z.number().nonnegative(),
  pages: z.array(InjectPreviewPageSchema),
  preview_text: z.string(),
  computed_at: z.string(),
});
export type InjectPreview = z.infer<typeof InjectPreviewSchema>;
