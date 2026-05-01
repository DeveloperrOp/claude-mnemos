import axios from "axios";

// All daemon REST endpoints live under /api/*. We bake the prefix into the
// axios baseURL so call-sites stay path-relative (apiClient.get("/health")
// → request to /api/health). VITE_DAEMON_BASE_URL may already include /api
// when overriding for tests/staging — detect and avoid double-prefixing.
const envBase = (import.meta.env.VITE_DAEMON_BASE_URL ?? "") as string;
const baseURL = envBase.endsWith("/api") ? envBase : `${envBase}/api`;

export const apiClient = axios.create({
  baseURL,
  timeout: 5000,
});
