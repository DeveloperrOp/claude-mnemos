import { z } from "zod";

export const TrayStatusSchema = z.object({
  platform: z.enum(["windows", "macos", "linux", "unsupported"]),
  autostart_enabled: z.boolean(),
  autostart_path: z.string().nullable().default(null),
  tray_running: z.boolean().default(false),
  tray_pid: z.number().int().nullable().default(null),
  daemon_pid: z.number().int().nullable().default(null),
});
export type TrayStatus = z.infer<typeof TrayStatusSchema>;

export const InstallResultSchema = z.object({
  installed: z.boolean(),
});
export type InstallResult = z.infer<typeof InstallResultSchema>;
