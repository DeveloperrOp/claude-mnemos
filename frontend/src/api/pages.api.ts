import { apiClient } from "./client";
import {
  PageBacklinksResponseSchema,
  PageDetailSchema,
  PageListResponseSchema,
  type PageDetail,
} from "@/types/WikiPage";

// Encode each path segment individually to preserve "/" separators while
// handling filenames that contain spaces, "?", "#", "&", "+" etc.
function encodePath(p: string): string {
  return p.split("/").map(encodeURIComponent).join("/");
}

export async function listPages(project: string): Promise<string[]> {
  const r = await apiClient.get(`/pages/${encodeURIComponent(project)}`);
  return PageListResponseSchema.parse(r.data).pages;
}

export async function getPage(
  project: string,
  pageRef: string,
): Promise<PageDetail> {
  const r = await apiClient.get(
    `/pages/${encodeURIComponent(project)}/${encodePath(pageRef)}`,
  );
  return PageDetailSchema.parse(r.data);
}

export async function getPageBacklinks(
  project: string,
  pageRef: string,
): Promise<string[]> {
  const r = await apiClient.get(
    `/pages/${encodeURIComponent(project)}/${encodePath(pageRef)}/backlinks`,
  );
  return PageBacklinksResponseSchema.parse(r.data).backlinks;
}
