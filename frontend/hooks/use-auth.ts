"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { clearToken, getMe, getStoredToken, storeToken } from "@/lib/api";
import type { User } from "@/types/api";

export function useAuth({ requireAuth = true }: { requireAuth?: boolean } = {}) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const token = getStoredToken();
    if (!token) {
      setIsLoading(false);
      if (requireAuth) {
        router.replace("/login");
      }
      return;
    }

    getMe()
      .then(setUser)
      .catch(() => {
        clearToken();
        if (requireAuth) {
          router.replace("/login");
        }
      })
      .finally(() => setIsLoading(false));
  }, [requireAuth, router]);

  function signIn(token: string, nextUser: User) {
    storeToken(token);
    setUser(nextUser);
  }

  function signOut() {
    clearToken();
    setUser(null);
    router.replace("/login");
  }

  return { user, isLoading, signIn, signOut };
}
