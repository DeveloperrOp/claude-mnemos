import axios from "axios";
import {
  FsBrowseSchema,
  FsHomeSchema,
  FsMkdirResponseSchema,
  type FsBrowse,
  type FsHome,
  type FsMkdirResponse,
} from "@/types/Fs";

export async function getHome(): Promise<FsHome> {
  const { data } = await axios.get("/fs/home");
  return FsHomeSchema.parse(data);
}

export async function browseDirectory(path: string): Promise<FsBrowse> {
  const { data } = await axios.get("/fs/browse", { params: { path } });
  return FsBrowseSchema.parse(data);
}

export async function mkdir(path: string): Promise<FsMkdirResponse> {
  const { data } = await axios.post("/fs/mkdir", { path });
  return FsMkdirResponseSchema.parse(data);
}
