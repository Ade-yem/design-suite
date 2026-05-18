"use client";

/**
 * @file page.tsx (register)
 * @description Glassmorphic registration form that hits /auth/register
 * and automatically manages verification transitions.
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { apiClient, ApiError } from "@/lib/api";
import { toast, Toaster } from "sonner";
import { UserPlus, User, Mail, Lock, RefreshCw, ArrowRight } from "lucide-react";
import { RegisterPayload, UserProfile } from "@/types/auth";

// Form validation schemas
const registerSchema = z.object({
  fullName: z.string().min(2, "Full display name must be at least 2 characters."),
  email: z.string().email("Please enter a valid active email address."),
  password: z.string().min(8, "Security key must be at least 8 characters long."),
});

type RegisterFormValues = z.infer<typeof registerSchema>;

export default function RegisterPage() {
  const router = useRouter();
  const [isLoading, setIsLoading] = useState(false);

  // Hook-form settings
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<RegisterFormValues>({
    resolver: zodResolver(registerSchema),
  });

  /**
   * Submit registration to backend FastAPI auth.
   */
  const onRegisterSubmit = async (data: RegisterFormValues) => {
    setIsLoading(true);
    try {
      const payload: RegisterPayload = {
        email: data.email,
        password: data.password,
        full_name: data.fullName,
      };

      await apiClient.post<UserProfile>("/auth/register", payload);

      toast.success("Account successfully initialized!");
      
      // Redirect user to verify-pending page
      router.push(`/verify-pending?email=${encodeURIComponent(data.email)}`);
    } catch (err: unknown) {
      const apiErr = err as ApiError;
      toast.error(apiErr.detail || "Registration failed. This email may already be linked to an active profile.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="relative min-h-screen bg-canvas-bg dot-grid flex items-center justify-center p-4 overflow-hidden">
      <Toaster position="top-right" theme="dark" closeButton richColors />
      
      {/* Dynamic graphic highlights */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-primary/5 rounded-full blur-[100px] pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-accent/5 rounded-full blur-[100px] pointer-events-none" />

      {/* Main Glassmorphic Card */}
      <div className="w-full max-w-md bg-card/45 backdrop-blur-md border border-border rounded-xl p-8 shadow-2xl relative z-10 animate-fade-in-up">
        
        {/* Onboarding Profile Head */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-12 h-12 bg-primary/10 border border-primary/20 rounded-lg flex items-center justify-center mb-3 glow-blue">
            <UserPlus className="w-6 h-6 text-primary" />
          </div>
          <h1 className="text-xl font-bold font-sans tracking-wide text-foreground">
            Initialize Profile
          </h1>
          <p className="text-muted-foreground text-xs font-mono mt-1 text-center">
            Sign up to unlock automated calculations and AI structural drafts.
          </p>
        </div>

        {/* Credentials Form */}
        <form onSubmit={handleSubmit(onRegisterSubmit)} className="space-y-5">
          
          {/* Full Name field */}
          <div className="space-y-1.5">
            <label className="text-xs font-mono text-muted-foreground uppercase tracking-wider block">
              Professional Display Name
            </label>
            <div className="relative">
              <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-muted-foreground pointer-events-none">
                <User className="w-4 h-4" />
              </span>
              <input
                type="text"
                disabled={isLoading}
                placeholder="Engineer John Doe"
                className="w-full bg-secondary/35 border border-border focus:border-primary/50 focus:ring-1 focus:ring-primary/30 rounded-lg pl-10 pr-4 py-2.5 text-sm text-foreground outline-none transition-all placeholder:text-muted-foreground/45"
                {...register("fullName")}
              />
            </div>
            {errors.fullName && (
              <span className="text-destructive text-xs font-mono block mt-1">
                {errors.fullName.message}
              </span>
            )}
          </div>

          {/* Email field */}
          <div className="space-y-1.5">
            <label className="text-xs font-mono text-muted-foreground uppercase tracking-wider block">
              Corporate Email ID
            </label>
            <div className="relative">
              <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-muted-foreground pointer-events-none">
                <Mail className="w-4 h-4" />
              </span>
              <input
                type="email"
                disabled={isLoading}
                placeholder="engineer@firm.com"
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
            <label className="text-xs font-mono text-muted-foreground uppercase tracking-wider block">
              Master Access Key (Password)
            </label>
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

          {/* Submit Trigger */}
          <button
            type="submit"
            disabled={isLoading}
            className="w-full bg-primary hover:bg-primary/90 disabled:opacity-50 text-white rounded-lg py-2.5 text-sm font-semibold flex items-center justify-center space-x-2 transition-all cursor-pointer shadow-lg active:scale-[0.98]"
          >
            {isLoading ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <>
                <span>Configure Environment</span>
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>

          {/* Navigation Footer */}
          <div className="text-center mt-6">
            <span className="text-xs text-muted-foreground font-sans">
              Already have an active profile?{" "}
              <a
                href="/login"
                className="text-primary hover:underline font-semibold"
              >
                Log In
              </a>
            </span>
          </div>
        </form>
      </div>
    </div>
  );
}
