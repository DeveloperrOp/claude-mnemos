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

export interface PatchResult {
  success: boolean;
  snapshot_path: string | null;
  activity_id: string;
}

export interface DeleteResult {
  success: boolean;
  snapshot_path: string | null;
  activity_id: string;
  trash_id: string;
}

export interface PagePatchBody {
  frontmatter?: Record<string, unknown>;
  body?: string;
  /** Version the editor loaded; server returns 409 if the file changed since. */
  base_version?: string;
}

export async function verifyPage(
  project: string,
  pageRef: string,
): Promise<PatchResult> {
  const r = await apiClient.post(
    `/pages/${encodeURIComponent(project)}/${encodePath(pageRef)}/verify`,
  );
  return r.data as PatchResult;
}

export async function deletePage(
  project: string,
  pageRef: string,
): Promise<DeleteResult> {
  const r = await apiClient.delete(
    `/pages/${encodeURIComponent(project)}/${encodePath(pageRef)}`,
  );
  return r.data as DeleteResult;
}

export async function patchPage(
  project: string,
  pageRef: string,
  body: PagePatchBody,
): Promise<PatchResult> {
  const r = await apiClient.patch(
    `/pages/${encodeURIComponent(project)}/${encodePath(pageRef)}`,
    body,
  );
  return r.data as PatchResult;
}
