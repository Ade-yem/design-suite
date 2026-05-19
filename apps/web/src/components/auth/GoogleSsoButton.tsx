"use client";

/**
 * @file GoogleSsoButton.tsx
 * @description Reusable, glassmorphic Google Single-Sign-On authorization button.
 * Encapsulates the API call to retrieve the authorization URL and performs the browser redirect.
 */

import { useState } from "react";
import { apiClient } from "@/lib/api";
import { Google } from "@/components/icon/google";
import { RefreshCw } from "lucide-react";
import { toast } from "sonner";

interface GoogleSsoButtonProps {
  /**
   * Label text to be shown inside the button.
   * @default "Continue with Google Account"
   */
  label?: string;
  /**
   * External loading state or flag to disable interactions.
   * @default false
   */
  disabled?: boolean;
}

export function GoogleSsoButton({
  label = "Continue with Google Account",
  disabled = false,
}: GoogleSsoButtonProps) {
  const [isRedirecting, setIsRedirecting] = useState(false);

  /**
   * Contacts the FastAPI backend to retrieve the secure Google authorize URL and
   * redirects the user's browser context to initialize the OAuth flow.
   */
  const handleGoogleSso = async () => {
    setIsRedirecting(true);
    try {
      const authResponse = await apiClient.get<{ authorization_url: string }>(
        "/api/auth/google/authorize"
      );
      window.location.href = authResponse.data.authorization_url;
    } catch (err: unknown) {
      console.error("Google SSO redirection failed:", err);
      toast.error(
        "Failed to initiate Google Single Sign-On. Please check your internet connection or try again."
      );
      setIsRedirecting(false);
    }
  };

  return (
    <button
      type="button"
      onClick={handleGoogleSso}
      disabled={disabled || isRedirecting}
      className="w-full bg-secondary/20 hover:bg-secondary/45 border border-border text-foreground rounded-lg py-2.5 text-sm font-medium flex items-center justify-center space-x-2 transition-all cursor-pointer active:scale-[0.98] disabled:opacity-50"
    >
      {isRedirecting ? (
        <RefreshCw className="w-4 h-4 animate-spin text-primary" />
      ) : (
        <Google className="w-4 h-4 text-primary" />
      )}
      <span>{isRedirecting ? "Connecting with Google..." : label}</span>
    </button>
  );
}
