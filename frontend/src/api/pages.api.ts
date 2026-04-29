import { apiClient } from "./client";
import {
  PageBacklinksResponseSchema,
  PageDetailSchema,
  PageListResponseSchema,
  type PageDetail,
} from "@/types/WikiPage";

export async function listPages(project: string): Promise<string[]> {
  const r = await apiClient.get(`/pages/${encodeURIComponent(project)}`);
  return PageListResponseSchema.parse(r.data).pages;
}

export async function getPage(
  project: string,
  pageRef: string,
): Promise<PageDetail> {
  // pageRef can contain "/" — must NOT urlencode forward slashes
  // (FastAPI uses {page_ref:path} which matches multi-segment refs).
  const r = await apiClient.get(
    `/pages/${encodeURIComponent(project)}/${pageRef}`,
  );
  return PageDetailSchema.parse(r.data);
}

export async function getPageBacklinks(
  project: string,
  pageRef: string,
): Promise<string[]> {
  const r = await apiClient.get(
    `/pages/${encodeURIComponent(project)}/${pageRef}/backlinks`,
  );
  return PageBacklinksResponseSchema.parse(r.data).backlinks;
}
