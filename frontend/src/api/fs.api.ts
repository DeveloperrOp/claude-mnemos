import axios from "axios";
import {
  FsBrowseSchema,
  FsDrivesSchema,
  FsHomeSchema,
  FsMkdirResponseSchema,
  type FsBrowse,
  type FsDrives,
  type FsHome,
  type FsMkdirResponse,
} from "@/types/Fs";

export async function getHome(): Promise<FsHome> {
  const { data } = await axios.get("/fs/home");
  return FsHomeSchema.parse(data);
}

export async function browseDirectory(
  path: string,
  opts?: { includeFiles?: boolean },
): Promise<FsBrowse> {
  const params: Record<string, string | boolean> = { path };
  if (opts?.includeFiles) params.include_files = true;
  const { data } = await axios.get("/fs/browse", { params });
  return FsBrowseSchema.parse(data);
}

export async function listDrives(): Promise<FsDrives> {
  const { data } = await axios.get("/fs/drives");
  return FsDrivesSchema.parse(data);
}

export async function mkdir(path: string): Promise<FsMkdirResponse> {
  const { data } = await axios.post("/fs/mkdir", { path });
  return FsMkdirResponseSchema.parse(data);
}
