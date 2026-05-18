/**
 * @file auth.ts
 * @description Master TypeScript type definitions for all frontend authentication
 * request payloads and response models matching our FastAPI schemas.
 */

/**
 * Tenant organisation information associated with a user profile.
 */
export interface OrganisationInfo {
  id: string;
  name: string;
  slug: string;
}

/**
 * Structural User Profile response returned by GET /users/me.
 */
export interface UserProfile {
  id: string;
  email: string;
  is_active: boolean;
  is_superuser: boolean;
  is_verified: boolean;
  full_name: string | null;
  role: "engineer" | "admin" | "viewer";
  organisation_id: string | null;
  organisation: OrganisationInfo | null;
}

/**
 * Standard bearer token issued on successful login / verification.
 */
export interface LoginResponse {
  access_token: string;
  token_type: string;
}

/**
 * Custom 2FA challenge response issued by our custom login router.
 */
export interface Login2faChallengeResponse {
  status: "two_factor_required";
  user_id: string;
  email: string;
}

/**
 * Unified return type of credentials login endpoint.
 */
export type AuthResponse = LoginResponse | Login2faChallengeResponse;

/**
 * Type-guard to check if an auth response is a 2FA PIN challenge.
 */
export function is2faChallenge(response: AuthResponse): response is Login2faChallengeResponse {
  return (response as Login2faChallengeResponse).status === "two_factor_required";
}

// ── Request Payloads ─────────────────────────────────────────────────────────

/**
 * Payload expected by POST /auth/jwt/two-factor-verify.
 */
export interface TwoFactorVerifyPayload {
  user_id: string;
  code: string;
}

/**
 * Payload expected by POST /auth/register.
 */
export interface RegisterPayload {
  email: string;
  password: string;
  full_name: string | null;
}

/**
 * Payload expected by POST /auth/request-verify-token.
 */
export interface RequestVerifyTokenPayload {
  email: string;
}

/**
 * Payload expected by POST /auth/verify.
 */
export interface VerifyPayload {
  token: string;
}

/**
 * Payload expected by POST /auth/forgot-password.
 */
export interface ForgotPasswordPayload {
  email: string;
}

/**
 * Payload expected by POST /auth/reset-password.
 */
export interface ResetPasswordPayload {
  token: string;
  password: string;
}
