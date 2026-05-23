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

  // Wait for BOTH React mount AND Zustand's persist hydration from localStorage.
  // Zustand v5 persist is asynchronous even with synchronous storage — if we
  // render children before hasHydrated(), the request interceptor reads a null
  // token and requests go out without Authorization headers.
  const [isReady, setIsReady] = useState(
    () => typeof window !== "undefined" && useAuthStore.persist?.hasHydrated?.() || false
  );

  useEffect(() => {
    if (isReady) return;
    if (typeof window === "undefined") return;
    if (!useAuthStore.persist) {
      setIsReady(true);
      return;
    }
    const unsub = useAuthStore.persist.onFinishHydration(() => setIsReady(true));
    // In case hydration already finished between the useState initializer and this effect
    if (useAuthStore.persist.hasHydrated?.()) setIsReady(true);
    return unsub;
  }, [isReady]);

  const isPublicRoute =
    pathname === "/login" ||
    pathname === "/register" ||
    pathname === "/verify" ||
    pathname === "/verify-pending" ||
    pathname === "/forgot-password" ||
    pathname === "/reset-password";

  useEffect(() => {
    if (!isReady) return;
    if (!isAuthenticated && !isPublicRoute) {
      router.push("/login");
    } else if (isAuthenticated && isPublicRoute) {
      router.push("/");
    }
  }, [isAuthenticated, isPublicRoute, router, isReady]);

  // Show spinner while the store is hydrating, or while a redirect is imminent.
  // Never render children until auth state is definitively known and correct.
  const redirectPending = isReady && (
    (!isAuthenticated && !isPublicRoute) ||
    (isAuthenticated && isPublicRoute)
  );

  if (!isReady || redirectPending) {
    return (
      <div className="min-h-screen bg-canvas-bg flex items-center justify-center">
        <div className="flex flex-col items-center space-y-4">
          <div className="w-12 h-12 border-2 border-primary border-t-transparent rounded-full animate-spin glow-blue" />
          <p className="text-muted-foreground text-sm font-mono tracking-wider">
            LOADING ENVIRONMENT...
          </p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
