"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { useAuthStore } from "@/stores/authStore";
import { apiClient, ApiError, getFriendlyErrorMessage } from "@/lib/api";
import { toast, Toaster } from "sonner";
import {
  ShieldCheck,
  Mail,
  Lock,
  LogIn,
  ArrowRight,
  RefreshCw,
  KeyRound,
} from "lucide-react";
import { GoogleSsoButton } from "@/components/auth/GoogleSsoButton";
import {
  AuthResponse,
  LoginResponse,
  UserProfile,
  TwoFactorVerifyPayload,
  is2faChallenge,
} from "@/types/auth";

// Form input validations using Zod schemas
const loginSchema = z.object({
  email: z.email("Please enter a valid email address."),
  password: z.string().min(6, "Password must be at least 6 characters."),
});

type LoginFormValues = z.infer<typeof loginSchema>;

export default function LoginPage() {
  const router = useRouter();
  const {
    is2faRequired,
    pendingEmail,
    pendingUserId,
    setAuth,
    set2faChallenge,
    clearAuth,
  } = useAuthStore();

  const [isLoading, setIsLoading] = useState(false);
  const [otpCode, setOtpCode] = useState("");
  const [countdown, setCountdown] = useState(300); // 5 minutes in seconds

  // React Hook Form registration
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
  });

  // 2FA expiration countdown effect
  useEffect(() => {
    if (!is2faRequired) return;
    const timer = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          clearInterval(timer);
          toast.error("2FA session expired. Please attempt login again.");
          clearAuth();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [is2faRequired, clearAuth]);

  /**
   * Submits credentials to FastAPI backend to login.
   */
  const onCredentialsSubmit = async (data: LoginFormValues) => {
    setIsLoading(true);
    try {
      const formData = new URLSearchParams();
      formData.append("username", data.email);
      formData.append("password", data.password);

      const response = await apiClient.post<AuthResponse>(
        "/api/auth/jwt/login",
        formData,
        { headers: { "Content-Type": "application/x-www-form-urlencoded" } },
      );

      // Handle 2FA Challenge interception using type guard
      if (is2faChallenge(response.data)) {
        set2faChallenge(response.data.user_id, response.data.email);
        toast.info(
          "Stateful 2FA Required. We've dispatched a PIN code to your email.",
        );
        setIsLoading(false);
        return;
      }
      const token = response.data.access_token;

      // 2. Fetch logged-in user profile details
      toast.info("Login successful. We are taking you to your environment.");
      const userProfileResponse = await apiClient.get<UserProfile>(
        "/api/users/me",
        {
          headers: { Authorization: `Bearer ${token}` },
        },
      );

      // 3. Save to Zustand Auth Store
      setAuth(
        userProfileResponse.data,
        token,
        userProfileResponse.data.organisation,
      );

      toast.success("Welcome back! Loading your Workspace...");
      router.push("/");
    } catch (err: unknown) {
      const apiErr = err as ApiError;
      toast.error(getFriendlyErrorMessage(apiErr.detail));
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Verification submission for 2FA OTP codes.
   */
  const onOtpSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (otpCode.length !== 6) {
      toast.error("Please enter a complete 6-digit numeric PIN.");
      return;
    }

    if (!pendingUserId) {
      toast.error("Verification session ID is missing.");
      return;
    }

    setIsLoading(true);
    try {
      const payload: TwoFactorVerifyPayload = {
        user_id: pendingUserId,
        code: otpCode,
      };

      const response = await apiClient.post<LoginResponse>(
        "/api/auth/jwt/two-factor-verify",
        payload,
      );

      const token = response.data.access_token;

      // Fetch profile
      const userProfileResponse = await apiClient.get<UserProfile>(
        "/api/users/me",
        {
          headers: { Authorization: `Bearer ${token}` },
        },
      );

      setAuth(
        userProfileResponse.data,
        token,
        userProfileResponse.data.organisation,
      );

      toast.success("Two-Factor Verified! Entry Granted.");
      router.push("/");
    } catch (err: unknown) {
      const apiErr = err as ApiError;
      toast.error(getFriendlyErrorMessage(apiErr.detail));
    } finally {
      setIsLoading(false);
    }
  };



  return (
    <div className="relative min-h-screen bg-canvas-bg dot-grid flex items-center justify-center p-4 overflow-hidden">
      <Toaster position="top-right" theme="dark" closeButton richColors />

      {/* Visual background ambient glow highlights */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-primary/5 rounded-full blur-[100px] pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-accent/5 rounded-full blur-[100px] pointer-events-none" />

      {/* Main Container Card */}
      <div className="w-full max-w-md bg-card/45 backdrop-blur-md border border-border rounded-xl p-8 shadow-2xl relative z-10 animate-fade-in-up">
        {/* Header Profile */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-12 h-12 bg-primary/10 border border-primary/20 rounded-lg flex items-center justify-center mb-3 glow-blue">
            <ShieldCheck className="w-6 h-6 text-primary" />
          </div>
          <h1 className="text-xl font-bold font-sans tracking-wide text-foreground">
            {is2faRequired
              ? "Security Verification"
              : "Structural Design Copilot"}
          </h1>
          <p className="text-muted-foreground text-xs font-mono mt-1 text-center">
            {is2faRequired
              ? `Verification dispatch active for ${pendingEmail}`
              : "Enter credentials to access CAD environments."}
          </p>
        </div>

        {/* Dynamic Screen Routing */}
        {!is2faRequired ? (
          /* ── Standard Credentials Screen ── */
          <form
            onSubmit={handleSubmit(onCredentialsSubmit)}
            className="space-y-5"
          >
            {/* Email field */}
            <div className="space-y-1.5">
              <label className="text-xs font-mono text-muted-foreground uppercase tracking-wider block">
                Email
              </label>
              <div className="relative">
                <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-muted-foreground pointer-events-none">
                  <Mail className="w-4 h-4" />
                </span>
                <input
                  type="email"
                  disabled={isLoading}
                  placeholder="name@company.com"
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

            {/* Password field */}
            <div className="space-y-1.5">
              <div className="flex justify-between items-center">
                <label className="text-xs font-mono text-muted-foreground uppercase tracking-wider block">
                  Password
                </label>
                <a
                  href="/forgot-password"
                  className="text-xs font-mono text-primary/80 hover:text-primary transition-colors hover:underline"
                >
                  Forgot Key?
                </a>
              </div>
              <div className="relative">
                <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-muted-foreground pointer-events-none">
                  <Lock className="w-4 h-4" />
                </span>
                <input
                  type="password"
                  disabled={isLoading}
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

            {/* Core Sign-In Trigger */}
            <button
              type="submit"
              disabled={isLoading}
              className="w-full bg-primary hover:bg-primary/90 disabled:opacity-50 text-white rounded-lg py-2.5 text-sm font-semibold flex items-center justify-center space-x-2 transition-all cursor-pointer shadow-lg active:scale-[0.98]"
            >
              {isLoading ? (
                <RefreshCw className="w-4 h-4 animate-spin" />
              ) : (
                <>
                  <span>Login</span>
                  <LogIn className="w-4 h-4" />
                </>
              )}
            </button>

            {/* Divider */}
            <div className="relative my-6 flex items-center justify-center">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-border" />
              </div>
              <span className="relative z-10 px-3 bg-[#090d16] text-[10px] font-mono text-muted-foreground uppercase tracking-wider">
                OR
              </span>
            </div>

            {/* Google OAuth Button */}
            <GoogleSsoButton label="Continue with Google Account" disabled={isLoading} />

            {/* Footer Onboarding Routing */}
            <div className="text-center mt-6">
              <span className="text-xs text-muted-foreground font-sans">
                New to the Design Copilot?{" "}
                <a
                  href="/register"
                  className="text-primary hover:underline font-semibold"
                >
                  Create an Account
                </a>
              </span>
            </div>
          </form>
        ) : (
          /* ── Stateful 2FA Verification Screen ── */
          <form onSubmit={onOtpSubmit} className="space-y-6">
            {/* OTP description details */}
            <div className="bg-secondary/25 border border-border rounded-lg p-4 space-y-2">
              <div className="flex items-center space-x-2 text-primary">
                <KeyRound className="w-4 h-4" />
                <span className="text-xs font-mono font-bold uppercase tracking-wider">
                  Verification Key Required
                </span>
              </div>
              <p className="text-muted-foreground text-[11px] leading-relaxed font-sans">
                We have emailed a 6-digit verification code PIN. Please retrieve
                it to verify authentication profile.
              </p>
            </div>

            {/* OTP numeric input */}
            <div className="space-y-2">
              <label className="text-xs font-mono text-muted-foreground uppercase tracking-wider block text-center">
                Enter 6-Digit PIN Code
              </label>
              <input
                type="text"
                maxLength={6}
                value={otpCode}
                onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, ""))}
                disabled={isLoading}
                placeholder="0 0 0 0 0 0"
                className="w-full bg-secondary/35 border border-border focus:border-primary/50 text-center tracking-[0.75em] text-lg font-mono rounded-lg py-3 outline-none transition-all placeholder:text-muted-foreground/35"
              />

              {/* Cooldown timer visual indicator */}
              <div className="flex justify-between items-center text-[10px] font-mono text-muted-foreground px-1 mt-1">
                <span>Verification session expires in:</span>
                <span className="text-primary font-bold">
                  {Math.floor(countdown / 60)}:
                  {(countdown % 60).toString().padStart(2, "0")}
                </span>
              </div>
            </div>

            {/* Submit Verification OTP */}
            <button
              type="submit"
              disabled={isLoading || otpCode.length !== 6}
              className="w-full bg-primary hover:bg-primary/90 disabled:opacity-50 text-white rounded-lg py-2.5 text-sm font-semibold flex items-center justify-center space-x-2 transition-all cursor-pointer shadow-lg active:scale-[0.98]"
            >
              {isLoading ? (
                <RefreshCw className="w-4 h-4 animate-spin" />
              ) : (
                <>
                  <span>Verify and Open IDE</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>

            {/* Cancel / Fallback button */}
            <button
              type="button"
              onClick={clearAuth}
              disabled={isLoading}
              className="w-full bg-transparent hover:bg-secondary/20 text-muted-foreground hover:text-foreground rounded-lg py-2 text-xs font-mono transition-all cursor-pointer"
            >
              Back to Credentials Login
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
