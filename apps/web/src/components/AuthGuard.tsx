"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useAuthStore } from "@/stores/authStore";

interface AuthGuardProps {
  children: React.ReactNode;
}

export function AuthGuard({ children }: AuthGuardProps) {
  const { isAuthenticated } = useAuthStore();
  const router = useRouter();
  const pathname = usePathname();
  const [isHydrated, setIsHydrated] = useState(false);

  useEffect(() => {
    setIsHydrated(true);
  }, []);

  useEffect(() => {
    if (!isHydrated) return;

    const isPublicRoute =
      pathname === "/login" ||
      pathname === "/register" ||
      pathname === "/verify" ||
      pathname === "/verify-pending" ||
      pathname === "/forgot-password" ||
      pathname === "/reset-password";

    if (!isAuthenticated && !isPublicRoute) {
      router.push("/login");
    } else if (isAuthenticated && isPublicRoute) {
      router.push("/");
    }
  }, [isAuthenticated, pathname, router, isHydrated]);

  // Show a dark elegant loading canvas background during transition/hydration to avoid flashes
  if (!isHydrated) {
    return (
      <div className="min-h-screen bg-canvas-bg flex items-center justify-center">
        <div className="flex flex-col items-center space-y-4">
          <div className="w-12 h-12 border-2 border-primary border-t-transparent rounded-full animate-spin glow-blue" />
          <p className="text-muted-foreground text-sm font-mono tracking-wider">LOADING ENVIRONMENT...</p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
