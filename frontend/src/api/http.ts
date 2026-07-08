/**
 * axios instance + envelope unwrapping.
 *
 * Every request auto-injects `X-User` from authStore.
 * Successful envelopes ({success:true}) unwrap `data.data` directly;
 * business failures throw `EnvelopeError` — network errors throw `NetworkError`.
 */
import axios, { AxiosInstance, AxiosResponse } from "axios";

import { useAuthStore } from "@/store/authStore";

export class EnvelopeError extends Error {
  code: string;
  detail: Record<string, unknown>;
  constructor(code: string, message: string, detail: Record<string, unknown> = {}) {
    super(message);
    this.name = "EnvelopeError";
    this.code = code;
    this.detail = detail;
  }
}

export class NetworkError extends Error {
  status?: number;
  constructor(message: string, status?: number) {
    super(message);
    this.name = "NetworkError";
    this.status = status;
  }
}

export interface Envelope<T> {
  success: boolean;
  data: T;
  message: string;
}

const http: AxiosInstance = axios.create({
  baseURL: "",
  timeout: 15_000,
});

http.interceptors.request.use((config) => {
  const user = useAuthStore.getState().user;
  if (user) {
    config.headers = config.headers ?? {};
    (config.headers as Record<string, string>)["X-User"] = user;
  }
  return config;
});

http.interceptors.response.use(
  (res: AxiosResponse<Envelope<unknown>>) => {
    const body = res.data;
    if (!body || typeof body !== "object" || !("success" in body)) {
      throw new NetworkError("malformed response (missing envelope)", res.status);
    }
    if (!body.success) {
      const errData = body.data as { code?: string; detail?: Record<string, unknown> } | undefined;
      throw new EnvelopeError(
        errData?.code ?? "INTERNAL_UNKNOWN",
        body.message || "unknown error",
        errData?.detail ?? {},
      );
    }
    // Rewrite res.data so callers get the unwrapped payload directly.
    (res as AxiosResponse<unknown>).data = body.data;
    return res;
  },
  (err) => {
    throw new NetworkError(err.message ?? "network error", err.response?.status);
  },
);

export async function apiGet<T>(url: string, params?: Record<string, unknown>): Promise<T> {
  const res = await http.get<T>(url, { params });
  return res.data;
}

export async function apiPost<T>(url: string, body?: unknown): Promise<T> {
  const res = await http.post<T>(url, body);
  return res.data;
}

export async function apiPatch<T>(url: string, body?: unknown): Promise<T> {
  const res = await http.patch<T>(url, body);
  return res.data;
}

export async function apiDelete<T>(url: string): Promise<T> {
  const res = await http.delete<T>(url);
  return res.data;
}

export default http;
