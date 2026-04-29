export function pagePathSegments(p: string): string {
  return p.split("/").map(encodeURIComponent).join("/");
}

export function pageHref(project: string, pagePath: string): string {
  return `/project/${encodeURIComponent(project)}/pages/${pagePathSegments(pagePath)}`;
}
