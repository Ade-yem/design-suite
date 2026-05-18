"use client";

/**
 * @file page.tsx (verify-pending)
 * @description Informs the user that verification emails are dispatched,
 * with controls to trigger token resends via /auth/request-verify-token.
 */

import { useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { apiClient, ApiError } from "@/lib/api";
import { toast, Toaster } from "sonner";
import { Inbox, RefreshCw, LogIn, ArrowLeft } from "lucide-react";
import { RequestVerifyTokenPayload } from "@/types/auth";

function VerifyPendingContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const email = searchParams.get("email") || "your email address";
  
  const [isLoading, setIsLoading] = useState(false);
  const [cooldown, setCooldown] = useState(0);

  /**
   * Request backend to dispatch a new verification token.
   */
  const handleResendToken = async () => {
    if (cooldown > 0) return;
    
    setIsLoading(true);
    try {
      const payload: RequestVerifyTokenPayload = { email };
      await apiClient.post<void>("/auth/request-verify-token", payload);
      toast.success("Verification token successfully dispatched. Check inbox.");
      
      // Start a 60-second cooldown to prevent abuse
      setCooldown(60);
      const timer = setInterval(() => {
        setCooldown((prev) => {
          if (prev <= 1) {
            clearInterval(timer);
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
    } catch (err: unknown) {
      const apiErr = err as ApiError;
      toast.error(apiErr.detail || "Unable to dispatch verification token. Please verify email address.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="w-full max-w-md bg-card/45 backdrop-blur-md border border-border rounded-xl p-8 shadow-2xl relative z-10 animate-fade-in-up">
      <Toaster position="top-right" theme="dark" closeButton richColors />

      {/* Inbox visual illustration */}
      <div className="flex flex-col items-center mb-8">
        <div className="w-16 h-16 bg-primary/10 border border-primary/20 rounded-full flex items-center justify-center mb-4 glow-blue">
          <Inbox className="w-8 h-8 text-primary" />
        </div>
        <h1 className="text-xl font-bold font-sans tracking-wide text-foreground">
          Check Your Inbox
        </h1>
        <p className="text-muted-foreground text-xs font-mono mt-2 text-center leading-relaxed">
          We sent a verification link to: <br />
          <span className="text-foreground font-bold">{email}</span>
        </p>
      </div>

      <div className="space-y-4">
        {/* Resend Action */}
        <button
          type="button"
          onClick={handleResendToken}
          disabled={isLoading || cooldown > 0}
          className="w-full bg-primary hover:bg-primary/90 disabled:opacity-50 text-white rounded-lg py-2.5 text-sm font-semibold flex items-center justify-center space-x-2 transition-all cursor-pointer shadow-lg active:scale-[0.98]"
        >
          {isLoading ? (
            <RefreshCw className="w-4 h-4 animate-spin" />
          ) : (
            <span>
              {cooldown > 0 ? `Resend Available in ${cooldown}s` : "Resend Verification Email"}
            </span>
          )}
        </button>

        {/* Back to Login */}
        <button
          type="button"
          onClick={() => router.push("/login")}
          className="w-full bg-secondary/20 hover:bg-secondary/45 border border-border text-foreground rounded-lg py-2.5 text-sm font-medium flex items-center justify-center space-x-2 transition-all cursor-pointer active:scale-[0.98]"
        >
          <LogIn className="w-4 h-4 text-primary" />
          <span>Return to Login Screen</span>
        </button>
      </div>

      {/* Footer support context */}
      <div className="mt-8 text-center border-t border-border/50 pt-6">
        <a
          href="/register"
          className="text-xs font-mono text-muted-foreground hover:text-foreground flex items-center justify-center space-x-1.5 transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Register with a different address</span>
        </a>
      </div>
    </div>
  );
}

export default function VerifyPendingPage() {
  return (
    <div className="relative min-h-screen bg-canvas-bg dot-grid flex items-center justify-center p-4 overflow-hidden">
      {/* Background ambient highlights */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-primary/5 rounded-full blur-[100px] pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-accent/5 rounded-full blur-[100px] pointer-events-none" />
      
      <Suspense fallback={
        <div className="w-full max-w-md bg-card/45 backdrop-blur-md border border-border rounded-xl p-8 flex items-center justify-center">
          <RefreshCw className="w-6 h-6 animate-spin text-primary" />
        </div>
      }>
        <VerifyPendingContent />
      </Suspense>
    </div>
  );
}
