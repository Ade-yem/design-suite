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
  Eye,
  EyeOff,
} from "lucide-react";
import { GoogleSsoButton } from "@/components/auth/GoogleSsoButton";
import { PRODUCT_NAME } from "@/lib/brand";
import {
  AuthResponse,
  LoginResponse,
  UserProfile,
  TwoFactorVerifyPayload,
  is2faChallenge,
} from "@/types/auth";

// Seconds between allowed code resends.
const RESEND_COOLDOWN = 60;

// Form input validations using Zod schemas
const loginSchema = z.object({
  email: z.email("Please enter a valid email address."),
  password: z.string().min(8, "Password must be at least 8 characters."),
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
  const [showPassword, setShowPassword] = useState(false);
  const [otpCode, setOtpCode] = useState("");
  const [countdown, setCountdown] = useState(300); // 5 minutes in seconds
  const [codeExpired, setCodeExpired] = useState(false);
  const [resendCooldown, setResendCooldown] = useState(0);
  const [isResending, setIsResending] = useState(false);

  // The credentials that triggered the 2FA challenge, retained in memory only
  // (never persisted) so we can re-request a fresh code without sending the user
  // back to the start.
  const [pendingCredentials, setPendingCredentials] =
    useState<LoginFormValues | null>(null);

  // React Hook Form registration
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
  });

  // 2FA expiration countdown effect. Timer/expiry resets happen in the event
  // handlers that open or refresh the challenge, not here.
  useEffect(() => {
    if (!is2faRequired) return;
    const timer = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          clearInterval(timer);
          // Keep the engineer on the verification screen — don't discard the
          // login. They can request a fresh code from here.
          setCodeExpired(true);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [is2faRequired]);

  // Resend cooldown ticker.
  useEffect(() => {
    if (resendCooldown <= 0) return;
    const timer = setInterval(() => {
      setResendCooldown((prev) => (prev <= 1 ? 0 : prev - 1));
    }, 1000);
    return () => clearInterval(timer);
  }, [resendCooldown]);

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
        setPendingCredentials(data);
        setCountdown(300);
        setCodeExpired(false);
        set2faChallenge(response.data.user_id, response.data.email);
        toast.info("We emailed you a 6-digit code.");
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

      toast.success("Verified. Taking you to your workspace…");
      router.push("/");
    } catch (err: unknown) {
      const apiErr = err as ApiError;
      toast.error(getFriendlyErrorMessage(apiErr.detail));
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Request a fresh 2FA code. The code is minted by the login endpoint, so we
   * re-submit the retained credentials. Rate-limited by a cooldown.
   */
  const handleResendCode = async () => {
    if (resendCooldown > 0 || isResending) return;
    const creds = pendingCredentials;
    if (!creds) {
      toast.error("Please sign in again to receive a new code.");
      clearAuth();
      return;
    }

    setIsResending(true);
    try {
      const formData = new URLSearchParams();
      formData.append("username", creds.email);
      formData.append("password", creds.password);

      await apiClient.post<AuthResponse>("/api/auth/jwt/login", formData, {
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
      });

      setOtpCode("");
      setCountdown(300);
      setCodeExpired(false);
      setResendCooldown(RESEND_COOLDOWN);
      toast.success("We sent you a new code.");
    } catch (err: unknown) {
      const apiErr = err as ApiError;
      toast.error(getFriendlyErrorMessage(apiErr.detail));
    } finally {
      setIsResending(false);
    }
  };

  /** Abandon the 2FA challenge and return to the credentials screen. */
  const handleCancel2fa = () => {
    setPendingCredentials(null);
    setCodeExpired(false);
    clearAuth();
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
            {is2faRequired ? "Check your email" : PRODUCT_NAME}
          </h1>
          <p className="text-muted-foreground text-xs font-mono mt-1 text-center">
            {is2faRequired
              ? `Enter the code we sent to ${pendingEmail}`
              : "Sign in to continue."}
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
                  Forgot password?
                </a>
              </div>
              <div className="relative">
                <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-muted-foreground pointer-events-none">
                  <Lock className="w-4 h-4" />
                </span>
                <input
                  type={showPassword ? "text" : "password"}
                  disabled={isLoading}
                  placeholder="••••••••"
                  className="w-full bg-secondary/35 border border-border focus:border-primary/50 focus:ring-1 focus:ring-primary/30 rounded-lg pl-10 pr-10 py-2.5 text-sm text-foreground outline-none transition-all placeholder:text-muted-foreground/45"
                  {...register("password")}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute inset-y-0 right-0 pr-3 flex items-center text-muted-foreground hover:text-foreground transition-colors"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  tabIndex={-1}
                >
                  {showPassword ? (
                    <EyeOff className="w-4 h-4" />
                  ) : (
                    <Eye className="w-4 h-4" />
                  )}
                </button>
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
                New to {PRODUCT_NAME}?{" "}
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
                  Check your email
                </span>
              </div>
              <p className="text-muted-foreground text-[11px] leading-relaxed font-sans">
                We emailed you a 6-digit code. Enter it below to finish signing in.
              </p>
            </div>

            {/* OTP numeric input */}
            <div className="space-y-2">
              <label className="text-xs font-mono text-muted-foreground uppercase tracking-wider block text-center">
                Enter 6-digit code
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

              {/* Expiry status + resend */}
              <div className="flex justify-between items-center text-[10px] font-mono px-1 mt-1">
                {codeExpired ? (
                  <span className="text-destructive font-bold">
                    Code expired — resend to get a new one.
                  </span>
                ) : (
                  <span className="text-muted-foreground">
                    Code expires in{" "}
                    <span className="text-primary font-bold">
                      {Math.floor(countdown / 60)}:
                      {(countdown % 60).toString().padStart(2, "0")}
                    </span>
                  </span>
                )}
                <button
                  type="button"
                  onClick={handleResendCode}
                  disabled={resendCooldown > 0 || isResending}
                  className="text-primary/80 hover:text-primary hover:underline disabled:text-muted-foreground/50 disabled:no-underline transition-colors"
                >
                  {isResending
                    ? "Sending…"
                    : resendCooldown > 0
                      ? `Resend in ${resendCooldown}s`
                      : "Resend code"}
                </button>
              </div>
            </div>

            {/* Submit Verification OTP */}
            <button
              type="submit"
              disabled={isLoading || otpCode.length !== 6 || codeExpired}
              className="w-full bg-primary hover:bg-primary/90 disabled:opacity-50 text-white rounded-lg py-2.5 text-sm font-semibold flex items-center justify-center space-x-2 transition-all cursor-pointer shadow-lg active:scale-[0.98]"
            >
              {isLoading ? (
                <RefreshCw className="w-4 h-4 animate-spin" />
              ) : (
                <>
                  <span>Verify</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>

            {/* Cancel / Fallback button */}
            <button
              type="button"
              onClick={handleCancel2fa}
              disabled={isLoading}
              className="w-full bg-transparent hover:bg-secondary/20 text-muted-foreground hover:text-foreground rounded-lg py-2 text-xs font-mono transition-all cursor-pointer"
            >
              Use a different account
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
