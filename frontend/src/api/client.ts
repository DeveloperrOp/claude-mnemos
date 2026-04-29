import axios from "axios";

const baseURL = (import.meta.env.VITE_DAEMON_BASE_URL ?? "") as string;

export const apiClient = axios.create({
  baseURL,
  timeout: 5000,
});
