"use client";

/**
 * @file page.tsx (reset-password)
 * @description Extracts token from query params and processes password resets.
 */

import { useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { apiClient, ApiError } from "@/lib/api";
import { toast } from "sonner";
import {
  Lock,
  RefreshCw,
  KeyRound,
  CheckCircle2,
  ArrowRight,
} from "lucide-react";
import { ResetPasswordPayload } from "@/types/auth";

// Form validation schemas ensuring password matches and is secure
const resetSchema = z
  .object({
    password: z.string().min(8, "Security key must be at least 8 characters."),
    confirmPassword: z.string().min(8, "Please confirm security key."),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: "Security keys do not match. Please verify inputs.",
    path: ["confirmPassword"],
  });

type ResetFormValues = z.infer<typeof resetSchema>;

function ResetPasswordContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token");

  const [isLoading, setIsLoading] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);

  // Hook form setup
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ResetFormValues>({
    resolver: zodResolver(resetSchema),
  });

  /**
   * Submit reset request to backend.
   */
  const onResetSubmit = async (data: ResetFormValues) => {
    if (!token) {
      toast.error("Security token is missing from the URL. Override aborted.");
      return;
    }

    setIsLoading(true);
    try {
      const payload: ResetPasswordPayload = {
        token,
        password: data.password,
      };

      await apiClient.post<void>("/api/auth/reset-password", payload);

      setIsSuccess(true);
      toast.success("Security key updated successfully!");
    } catch (err: unknown) {
      const apiErr = err as ApiError;
      toast.error(
        apiErr.detail ||
          "Unable to reset security credentials. The token may have expired.",
      );
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="w-full max-w-md bg-card/45 backdrop-blur-md border border-border rounded-xl p-8 shadow-2xl relative z-10 animate-fade-in-up">
      {/* Onboarding Header */}
      <div className="flex flex-col items-center mb-8">
        <div className="w-12 h-12 bg-primary/10 border border-primary/20 rounded-lg flex items-center justify-center mb-3 glow-blue">
          <KeyRound className="w-6 h-6 text-primary" />
        </div>
        <h1 className="text-xl font-bold font-sans tracking-wide text-foreground">
          Override Security Key
        </h1>
        <p className="text-muted-foreground text-xs font-mono mt-1 text-center leading-relaxed">
          {isSuccess
            ? "Credentials updated successfully."
            : "Enter a new secure password display credentials."}
        </p>
      </div>

      {isSuccess ? (
        /* ── Screen: Reset Complete Success ── */
        <div className="space-y-6">
          <div className="flex flex-col items-center">
            <div className="w-16 h-16 bg-success/10 border border-success/20 rounded-full flex items-center justify-center mb-4">
              <CheckCircle2 className="w-10 h-10 text-success" />
            </div>
            <p className="text-muted-foreground text-xs font-mono text-center leading-relaxed">
              Your password key has been updated successfully. You may now
              return to the login screen and authenticate.
            </p>
          </div>

          <button
            type="button"
            onClick={() => router.push("/login")}
            className="w-full bg-primary hover:bg-primary/90 text-white rounded-lg py-2.5 text-sm font-semibold flex items-center justify-center space-x-2 transition-all cursor-pointer shadow-lg active:scale-[0.98]"
          >
            <span>Proceed to Login Screen</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      ) : (
        /* ── Screen: Form Input ── */
        <form onSubmit={handleSubmit(onResetSubmit)} className="space-y-5">
          {/* New password input */}
          <div className="space-y-1.5">
            <label className="text-xs font-mono text-muted-foreground uppercase tracking-wider block">
              New Password Key
            </label>
            <div className="relative">
              <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-muted-foreground pointer-events-none">
                <Lock className="w-4 h-4" />
              </span>
              <input
                type="password"
                disabled={isLoading || !token}
                placeholder="••••••••"
                className="w-full bg-secondary/35 border border-border focus:border-primary/50 focus:ring-1 focus:ring-primary/30 rounded-lg pl-10 pr-4 py-2.5 text-sm text-foreground outline-none transition-all placeholder:text-muted-foreground/45"
                {...register("password")}
              />
            </div>
            {errors.password && (
              <span className="text-destructive text-xs font-mono block mt-1">
                {errors.password.message}
              </span>
            )}
          </div>

          {/* Confirm new password */}
          <div className="space-y-1.5">
            <label className="text-xs font-mono text-muted-foreground uppercase tracking-wider block">
              Confirm Password Key
            </label>
            <div className="relative">
              <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-muted-foreground pointer-events-none">
                <Lock className="w-4 h-4" />
              </span>
              <input
                type="password"
                disabled={isLoading || !token}
                placeholder="••••••••"
                className="w-full bg-secondary/35 border border-border focus:border-primary/50 focus:ring-1 focus:ring-primary/30 rounded-lg pl-10 pr-4 py-2.5 text-sm text-foreground outline-none transition-all placeholder:text-muted-foreground/45"
                {...register("confirmPassword")}
              />
            </div>
            {errors.confirmPassword && (
              <span className="text-destructive text-xs font-mono block mt-1">
                {errors.confirmPassword.message}
              </span>
            )}
          </div>

          {/* Submit reset */}
          <button
            type="submit"
            disabled={isLoading || !token}
            className="w-full bg-primary hover:bg-primary/90 disabled:opacity-50 text-white rounded-lg py-2.5 text-sm font-semibold flex items-center justify-center space-x-2 transition-all cursor-pointer shadow-lg active:scale-[0.98]"
          >
            {isLoading ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <>
                <span>Commit Override Changes</span>
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>
        </form>
      )}
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <div className="relative min-h-screen bg-canvas-bg dot-grid flex items-center justify-center p-4 overflow-hidden">
      {/* Background ambient highlights */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-primary/5 rounded-full blur-[100px] pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-accent/5 rounded-full blur-[100px] pointer-events-none" />

      <Suspense
        fallback={
          <div className="w-full max-w-md bg-card/45 backdrop-blur-md border border-border rounded-xl p-8 flex items-center justify-center">
            <RefreshCw className="w-6 h-6 animate-spin text-primary" />
          </div>
        }
      >
        <ResetPasswordContent />
      </Suspense>
    </div>
  );
}
