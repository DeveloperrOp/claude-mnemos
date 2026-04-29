import axios from "axios";
import {
  InstallResultSchema,
  TrayStatusSchema,
  type InstallResult,
  type TrayStatus,
} from "@/types/Tray";

export async function getTrayStatus(): Promise<TrayStatus> {
  const { data } = await axios.get("/tray/status");
  return TrayStatusSchema.parse(data);
}

export async function installTray(): Promise<InstallResult> {
  const { data } = await axios.post("/tray/install");
  return InstallResultSchema.parse(data);
}

export async function uninstallTray(): Promise<InstallResult> {
  const { data } = await axios.post("/tray/uninstall");
  return InstallResultSchema.parse(data);
}
