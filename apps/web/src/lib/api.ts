/**
 * @file api.ts
 * @description Axios-based API client for structural ide.
 * Automatically injects active JWT token from Zustand store and intercept
 * 401 Unauthorized to purge expired session contexts.
 */

import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";
import { useAuthStore } from "@/stores/authStore";

/**
 * Standardized type-safe API error response schema.
 */
export interface ApiError {
  status: number;
  detail: string;
}

export const apiClient = axios.create({
  headers: {
    "Content-Type": "application/json",
  },
});

// ── Request Interceptor: Dynamic Token Injection ──────────────────────────────

apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = useAuthStore.getState().token;
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error: unknown) => {
    return Promise.reject(error);
  }
);

// ── Response Interceptor: Error Normalization & Session Expirations ───────────

apiClient.interceptors.response.use(
  (response) => {
    return response;
  },
  (error: AxiosError<{ detail?: string }>) => {
    const status = error.response?.status || 500;

    // Automatic session clearance on 401 Unauthorized (session expired)
    if (status === 401) {
      useAuthStore.getState().clearAuth();
    }

    // Process backend error payload
    let detail = "An unexpected network error occurred.";
    if (error.response?.data?.detail) {
      detail = error.response.data.detail;
    } else if (error.message) {
      detail = error.message;
    }

    const apiError: ApiError = {
      status,
      detail,
    };

    return Promise.reject(apiError);
  }
);
