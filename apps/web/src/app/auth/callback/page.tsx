"use client";

import { Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuthStore } from "@/stores/authStore";
import { apiClient } from "@/lib/api";
import { UserProfile } from "@/types/auth";
import { BlueprintIcon } from "@/components/BlueprintIcon";

function OAuthCallbackHandler() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { setAuth } = useAuthStore();

  useEffect(() => {
    const token = searchParams.get("token");
    const error = searchParams.get("error");

    if (error || !token) {
      router.replace("/login");
      return;
    }

    (async () => {
      try {
        const { data: profile } = await apiClient.get<UserProfile>(
          "/api/users/me",
          { headers: { Authorization: `Bearer ${token}` } },
        );
        setAuth(profile, token, profile.organisation);
        router.replace("/");
      } catch {
        router.replace("/login");
      }
    })();
  }, [searchParams, setAuth, router]);

  return (
    <div className="min-h-screen bg-canvas-bg dot-grid flex items-center justify-center">
      <div className="flex flex-col items-center space-x-4">
        <BlueprintIcon className="w-16 h-16" state="working" />
        <p className="text-muted-foreground font-mono text-sm">
          Logging you in...
        </p>
      </div>
    </div>
  );
}

export default function AuthCallbackPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-canvas-bg flex items-center justify-center">
          <p className="text-muted-foreground font-mono text-sm">Loading...</p>
        </div>
      }
    >
      <OAuthCallbackHandler />
    </Suspense>
  );
}
