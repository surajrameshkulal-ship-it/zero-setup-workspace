"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, clearToken } from "@/lib/api";

export function useApiResource<T>(loader: () => Promise<T>) {
  const router = useRouter();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  // Guard so an expired/missing token triggers at most one redirect, never a retry loop.
  const redirectingRef = useRef(false);

  const reload = useCallback(() => {
    setIsLoading(true);
    setError(null);
    return loader()
      .then((result) => {
        setData(result);
        return result;
      })
      .catch((caught: unknown) => {
        // Unauthenticated/expired session: clear the token and send the user to
        // the login page exactly once. Do not surface a raw 401 or retry.
        if (caught instanceof ApiError && caught.status === 401) {
          if (!redirectingRef.current) {
            redirectingRef.current = true;
            clearToken();
            router.replace("/login");
          }
          return;
        }
        const message = caught instanceof Error ? caught.message : "Request failed";
        setError(message);
        throw caught;
      })
      .finally(() => setIsLoading(false));
  }, [loader, router]);

  useEffect(() => {
    reload().catch(() => undefined);
  }, [reload]);

  return { data, error, isLoading, reload };
}
