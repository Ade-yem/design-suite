/**
 * @file authStore.ts
 * @description Production-grade Zustand authentication store with local storage persistence.
 * Tracks user context, security challenges (like 2FA), loading, and error states.
 */

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

import { UserProfile, OrganisationInfo as OrganisationContext } from "@/types/auth";

/**
 * Zustand authentication store state schema.
 */
interface AuthState {
  // Authentication properties
  user: UserProfile | null;
  token: string | null;
  organisation: OrganisationContext | null;
  isAuthenticated: boolean;

  // Transient state for multi-stage (2FA) login challenge
  is2faRequired: boolean;
  pendingUserId: string | null;
  pendingEmail: string | null;

  // UX states
  isLoading: boolean;
  error: string | null;
}

/**
 * Actions supported by the authentication store.
 */
interface AuthActions {
  /**
   * Set authentication state upon successful login or verification.
   * Also sets cookie for server-side / client-side consistency.
   */
  setAuth: (
    user: UserProfile,
    token: string,
    organisation: OrganisationContext | null
  ) => void;

  /**
   * Flag state that a 2FA OTP code verification challenge is required.
   */
  set2faChallenge: (userId: string, email: string) => void;

  /**
   * Clear all active sessions and stored tokens (Logout).
   */
  clearAuth: () => void;

  /**
   * Set general authentication loading states.
   */
  setLoading: (isLoading: boolean) => void;

  /**
   * Set general authentication error message.
   */
  setError: (error: string | null) => void;
}

export type AuthStore = AuthState & AuthActions;

const initialStoreState: AuthState = {
  user: null,
  token: null,
  organisation: null,
  isAuthenticated: false,
  is2faRequired: false,
  pendingUserId: null,
  pendingEmail: null,
  isLoading: false,
  error: null,
};

export const useAuthStore = create<AuthStore>()(
  persist(
    (set) => ({
      ...initialStoreState,

      setAuth: (user, token, organisation) => {
        set({
          user,
          token,
          organisation,
          isAuthenticated: true,
          is2faRequired: false,
          pendingUserId: null,
          pendingEmail: null,
          error: null,
        });
      },

      set2faChallenge: (userId, email) => {
        set({
          is2faRequired: true,
          pendingUserId: userId,
          pendingEmail: email,
          isAuthenticated: false,
          user: null,
          token: null,
          organisation: null,
          error: null,
        });
      },

      clearAuth: () => {
        set({
          ...initialStoreState,
        });
      },

      setLoading: (isLoading) => set({ isLoading }),

      setError: (error) => set({ error }),
    }),
    {
      name: "copilot-auth-session",
      storage: createJSONStorage(() => localStorage),
      // Only persist authentication properties, leave transient UX states out of localStorage
      partialize: (state) => ({
        user: state.user,
        token: state.token,
        organisation: state.organisation,
        isAuthenticated: state.isAuthenticated,
        is2faRequired: state.is2faRequired,
        pendingUserId: state.pendingUserId,
        pendingEmail: state.pendingEmail,
      }),
    }
  )
);
