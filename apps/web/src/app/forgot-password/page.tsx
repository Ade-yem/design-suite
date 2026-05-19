"use client";

/**
 * @file page.tsx (forgot-password)
 * @description Sleek email password recovery page. Intercepts backend-level
 * social account blocks (PASSWORD_RESET_NOT_ALLOWED_OAUTH_ONLY) to redirect users to Google SSO.
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { apiClient, ApiError } from "@/lib/api";
import { toast, Toaster } from "sonner";
import { KeyRound, Mail, RefreshCw, ArrowRight, ArrowLeft } from "lucide-react";
import { ForgotPasswordPayload } from "@/types/auth";
import { Google } from "@/components/icon/google";

// Form validation schemas
const forgotPasswordSchema = z.object({
  email: z.string().email("Please enter a valid active email address."),
});

type ForgotFormValues = z.infer<typeof forgotPasswordSchema>;

export default function ForgotPasswordPage() {
  const router = useRouter();
  const [isLoading, setIsLoading] = useState(false);
  const [isSent, setIsSent] = useState(false);
  const [oauthBlock, setOauthBlock] = useState(false);

  // Hook-form settings
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ForgotFormValues>({
    resolver: zodResolver(forgotPasswordSchema),
  });

  /**
   * Submit password reset request.
   */
  const onForgotSubmit = async (data: ForgotFormValues) => {
    setIsLoading(true);
    setOauthBlock(false);
    try {
      const payload: ForgotPasswordPayload = { email: data.email };
      await apiClient.post<void>("/api/auth/forgot-password", payload);
      setIsSent(true);
      toast.success("Security reset token dispatched!");
    } catch (err: unknown) {
      const apiErr = err as ApiError;

      // Intercept the security rule for Google OAuth users
      if (apiErr.detail === "PASSWORD_RESET_NOT_ALLOWED_OAUTH_ONLY") {
        setOauthBlock(true);
        toast.warning(
          "Access restricted. This profile uses Google Single-Sign-On.",
        );
      } else {
        // Standard user not found / not active fails silently or shows message
        // In highly secure setups, we can show success regardless, but standard works too.
        setIsSent(true);
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="relative min-h-screen bg-canvas-bg dot-grid flex items-center justify-center p-4 overflow-hidden">
      <Toaster position="top-right" theme="dark" closeButton richColors />

      {/* Background ambient highlights */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-primary/5 rounded-full blur-[100px] pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-accent/5 rounded-full blur-[100px] pointer-events-none" />

      {/* Main Glassmorphic Card */}
      <div className="w-full max-w-md bg-card/45 backdrop-blur-md border border-border rounded-xl p-8 shadow-2xl relative z-10 animate-fade-in-up">
        {/* Onboarding Header */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-12 h-12 bg-primary/10 border border-primary/20 rounded-lg flex items-center justify-center mb-3 glow-blue">
            <KeyRound className="w-6 h-6 text-primary" />
          </div>
          <h1 className="text-xl font-bold font-sans tracking-wide text-foreground">
            Recover Access Key
          </h1>
          <p className="text-muted-foreground text-xs font-mono mt-1 text-center leading-relaxed">
            {isSent
              ? "Check email inbox for reset parameters."
              : "Enter account ID to request a security override token."}
          </p>
        </div>

        {/* ── Screen: Social OAuth Block Warning ── */}
        {oauthBlock ? (
          <div className="space-y-6">
            <div className="bg-destructive/10 border border-destructive/25 rounded-lg p-4 space-y-3">
              <div className="flex items-center space-x-2 text-destructive">
                <Google className="w-5 h-5" />
                <span className="text-xs font-mono font-bold uppercase tracking-wider">
                  Social Account Bound
                </span>
              </div>
              <p className="text-muted-foreground text-xs leading-relaxed font-sans">
                This email is registered strictly using **Google
                Single-Sign-On**. Because Google manages authorization
                credentials for this profile, password recovery overrides are
                blocked.
              </p>
            </div>

            <button
              type="button"
              onClick={() => {
                const redirectUrl = `${window.location.origin}/auth/google/callback`;
                window.location.href = `/auth/google/authorize?redirect_uri=${encodeURIComponent(redirectUrl)}`;
              }}
              className="w-full bg-primary hover:bg-primary/90 text-white rounded-lg py-2.5 text-sm font-semibold flex items-center justify-center space-x-2 transition-all cursor-pointer shadow-lg active:scale-[0.98]"
            >
              <Google className="w-4 h-4" />
              <span>Sign In with Google</span>
            </button>

            <button
              type="button"
              onClick={() => router.push("/login")}
              className="w-full bg-secondary/20 hover:bg-secondary/45 border border-border text-foreground rounded-lg py-2 text-xs font-mono transition-all cursor-pointer"
            >
              Return to Login Screen
            </button>
          </div>
        ) : isSent ? (
          /* ── Screen: Token Dispatched Success ── */
          <div className="space-y-6">
            <div className="bg-secondary/25 border border-border rounded-lg p-4 space-y-2">
              <div className="flex items-center space-x-2 text-primary">
                <Mail className="w-4 h-4" />
                <span className="text-xs font-mono font-bold uppercase tracking-wider">
                  Reset Parameters Sent
                </span>
              </div>
              <p className="text-muted-foreground text-[11px] leading-relaxed font-sans">
                If the email matches an active profile, a secure link containing
                reset instructions has been dispatched. Links expire after 2
                hours.
              </p>
            </div>

            <button
              type="button"
              onClick={() => router.push("/login")}
              className="w-full bg-primary hover:bg-primary/90 text-white rounded-lg py-2.5 text-sm font-semibold flex items-center justify-center space-x-2 transition-all cursor-pointer shadow-lg active:scale-[0.98]"
            >
              <span>Back to Login</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        ) : (
          /* ── Screen: Request Credentials Email ── */
          <form onSubmit={handleSubmit(onForgotSubmit)} className="space-y-5">
            {/* Email input field */}
            <div className="space-y-1.5">
              <label className="text-xs font-mono text-muted-foreground uppercase tracking-wider block">
                Profile Email Address
              </label>
              <div className="relative">
                <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-muted-foreground pointer-events-none">
                  <Mail className="w-4 h-4" />
                </span>
                <input
                  type="email"
                  disabled={isLoading}
                  placeholder="mail@firm.com"
                  className="w-full bg-secondary/35 border border-border focus:border-primary/50 focus:ring-1 focus:ring-primary/30 rounded-lg pl-10 pr-4 py-2.5 text-sm text-foreground outline-none transition-all placeholder:text-muted-foreground/45"
                  {...register("email")}
                />
              </div>
              {errors.email && (
                <span className="text-destructive text-xs font-mono block mt-1">
                  {errors.email.message}
                </span>
              )}
            </div>

            {/* Submit request button */}
            <button
              type="submit"
              disabled={isLoading}
              className="w-full bg-primary hover:bg-primary/90 disabled:opacity-50 text-white rounded-lg py-2.5 text-sm font-semibold flex items-center justify-center space-x-2 transition-all cursor-pointer shadow-lg active:scale-[0.98]"
            >
              {isLoading ? (
                <RefreshCw className="w-4 h-4 animate-spin" />
              ) : (
                <>
                  <span>Dispatch Reset Key</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>

            {/* Footer Back Link */}
            <div className="text-center mt-6">
              <a
                href="/login"
                className="text-xs font-mono text-muted-foreground hover:text-foreground inline-flex items-center space-x-1.5 transition-colors"
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                <span>Return to Login</span>
              </a>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
