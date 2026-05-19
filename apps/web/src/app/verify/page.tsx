"use client";

/**
 * @file page.tsx (verify)
 * @description Extracts token from query params and submits it to /auth/verify,
 * displaying success transitions and login routes.
 */

import { useState, useEffect, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { apiClient, ApiError } from "@/lib/api";
import { toast, Toaster } from "sonner";
import { CheckCircle2, XCircle, RefreshCw, LogIn, ShieldAlert } from "lucide-react";
import { VerifyPayload, UserProfile } from "@/types/auth";

function VerifyContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token");

  const [status, setStatus] = useState<"verifying" | "success" | "failed">("verifying");
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    if (!token) {
      setStatus("failed");
      setErrorMessage("No verification activation token was found in the URL. Please verify your verification link.");
      return;
    }

    const triggerVerification = async () => {
      try {
        const payload: VerifyPayload = { token };
        await apiClient.post<UserProfile>("/api/auth/verify", payload);
        setStatus("success");
        toast.success("Email verification successful!");
      } catch (err: unknown) {
        const apiErr = err as ApiError;
        setStatus("failed");
        setErrorMessage(apiErr.detail || "The verification token is invalid or has expired. Please request a new activation link.");
        toast.error("Verification failed.");
      }
    };

    triggerVerification();
  }, [token]);

  return (
    <div className="w-full max-w-md bg-card/45 backdrop-blur-md border border-border rounded-xl p-8 shadow-2xl relative z-10 animate-fade-in-up">
      <Toaster position="top-right" theme="dark" closeButton richColors />

      {/* ── Status: Verifying ── */}
      {status === "verifying" && (
        <div className="flex flex-col items-center py-6">
          <div className="w-16 h-16 bg-primary/10 border border-primary/20 rounded-full flex items-center justify-center mb-6 glow-blue animate-pulse">
            <RefreshCw className="w-8 h-8 text-primary animate-spin" />
          </div>
          <h1 className="text-xl font-bold font-sans tracking-wide text-foreground">
            Verifying Credentials
          </h1>
          <p className="text-muted-foreground text-xs font-mono mt-2 text-center">
            Validating security signature token. Please wait...
          </p>
        </div>
      )}

      {/* ── Status: Success ── */}
      {status === "success" && (
        <div className="space-y-6">
          <div className="flex flex-col items-center">
            <div className="w-16 h-16 bg-success/10 border border-success/20 rounded-full flex items-center justify-center mb-4">
              <CheckCircle2 className="w-10 h-10 text-success" />
            </div>
            <h1 className="text-xl font-bold font-sans tracking-wide text-foreground">
              Verification Granted
            </h1>
            <p className="text-muted-foreground text-xs font-mono mt-2 text-center leading-relaxed">
              Your professional email profile has been successfully confirmed. You may now initialize your workspace.
            </p>
          </div>

          <button
            type="button"
            onClick={() => router.push("/login")}
            className="w-full bg-primary hover:bg-primary/90 text-white rounded-lg py-2.5 text-sm font-semibold flex items-center justify-center space-x-2 transition-all cursor-pointer shadow-lg active:scale-[0.98]"
          >
            <LogIn className="w-4 h-4" />
            <span>Launch CAD Environment</span>
          </button>
        </div>
      )}

      {/* ── Status: Failed ── */}
      {status === "failed" && (
        <div className="space-y-6">
          <div className="flex flex-col items-center">
            <div className="w-16 h-16 bg-destructive/10 border border-destructive/20 rounded-full flex items-center justify-center mb-4">
              <XCircle className="w-10 h-10 text-destructive" />
            </div>
            <h1 className="text-xl font-bold font-sans tracking-wide text-foreground">
              Verification Rejected
            </h1>
            <p className="text-destructive text-[11px] font-mono mt-3 text-center bg-destructive/5 border border-destructive/15 rounded-lg p-3 w-full">
              {errorMessage}
            </p>
          </div>

          <div className="space-y-3">
            <button
              type="button"
              onClick={() => router.push("/register")}
              className="w-full bg-primary hover:bg-primary/90 text-white rounded-lg py-2.5 text-sm font-semibold flex items-center justify-center space-x-2 transition-all cursor-pointer shadow-lg active:scale-[0.98]"
            >
              <span>Back to Registration</span>
            </button>

            <button
              type="button"
              onClick={() => router.push("/login")}
              className="w-full bg-secondary/20 hover:bg-secondary/45 border border-border text-foreground rounded-lg py-2.5 text-sm font-medium flex items-center justify-center space-x-2 transition-all cursor-pointer active:scale-[0.98]"
            >
              <ShieldAlert className="w-4 h-4 text-primary" />
              <span>Back to Login</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function VerifyPage() {
  return (
    <div className="relative min-h-screen bg-canvas-bg dot-grid flex items-center justify-center p-4 overflow-hidden">
      {/* Visual background ambient glow highlights */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-primary/5 rounded-full blur-[100px] pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-accent/5 rounded-full blur-[100px] pointer-events-none" />
      
      <Suspense fallback={
        <div className="w-full max-w-md bg-card/45 backdrop-blur-md border border-border rounded-xl p-8 flex items-center justify-center">
          <RefreshCw className="w-6 h-6 animate-spin text-primary" />
        </div>
      }>
        <VerifyContent />
      </Suspense>
    </div>
  );
}
