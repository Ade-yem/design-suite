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

/**
 * Maps system error code strings to highly polished, user-friendly, descriptive messages.
 * Prevents raw system or database error codes from leaking to the UI.
 *
 * @param detail The raw detail string from the API error response.
 * @returns A friendly, human-readable error message.
 */
export function getFriendlyErrorMessage(detail: string): string {
  if (!detail) {
    return "An unexpected error occurred. Please try again.";
  }

  const errorMap: Record<string, string> = {
    // Registration errors
    REGISTER_USER_ALREADY_EXISTS: "This email address is already associated with an active account. Please log in instead or use a different email.",
    REGISTER_INVALID_PASSWORD: "The password provided is too weak or does not meet security requirements.",
    
    // Login and 2FA errors
    EMAIL_NOT_VERIFIED: "Your email address has not been verified yet. Please check your inbox or spam folder for the verification link.",
    LOGIN_BAD_CREDENTIALS: "Incorrect email address or password. Please verify your credentials and try again.",
    BAD_CREDENTIALS: "Incorrect credentials. Please verify your details and try again.",
    USER_INACTIVE: "Your account is currently inactive or has been deactivated. Please contact support for assistance.",
    LOGIN_USER_INACTIVE: "This account has been deactivated. Please contact support.",
    USER_NOT_FOUND: "No active profile matches this identifier. Please verify the entered email address.",
    INVALID_OR_EXPIRED_CODE: "The 2FA verification PIN code is invalid or has expired. Please log in again to request a new code.",
    
    // OAuth errors
    OAUTH_USER_ALREADY_EXISTS: "This external account is already linked to a different user. Please sign in using your original method.",
    OAUTH_NOT_AVAILABLE_EMAIL: "The authentication provider did not return a valid email address. Please check your account settings.",
    OAUTH_INVALID_STATE: "The login session state is invalid. Please restart the login process.",
    
    // General / Fallbacks
    GATE_NOT_PASSED: "You must complete the previous step before proceeding.",
    MEMBER_NOT_FOUND: "The requested structural member could not be found.",
    PROJECT_NOT_FOUND: "The requested project could not be found.",
    FILE_PARSE_ERROR: "Failed to parse the uploaded file. Please ensure it is a valid, uncorrupted DXF or PDF document.",
    UNSUPPORTED_FILE: "Unsupported file format. Please upload a valid DXF or PDF file.",
    FILE_TOO_LARGE: "The uploaded file exceeds the maximum allowed size limit.",
  };

  return errorMap[detail] || detail;
}

