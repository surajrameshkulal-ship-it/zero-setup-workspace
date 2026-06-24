"use client";

import { useCallback, useEffect, useState } from "react";

export function useApiResource<T>(loader: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const reload = useCallback(() => {
    setIsLoading(true);
    setError(null);
    return loader()
      .then((result) => {
        setData(result);
        return result;
      })
      .catch((caught: unknown) => {
        const message = caught instanceof Error ? caught.message : "Request failed";
        setError(message);
        throw caught;
      })
      .finally(() => setIsLoading(false));
  }, [loader]);

  useEffect(() => {
    reload().catch(() => undefined);
  }, [reload]);

  return { data, error, isLoading, reload };
}
