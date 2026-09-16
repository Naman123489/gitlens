"use client";

import * as React from "react";

import { ApiError } from "@/lib/api";

export interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
  setData: React.Dispatch<React.SetStateAction<T | null>>;
}

/**
 * Fetch-on-mount with reload and cancellation.
 *
 * State updates are skipped after unmount, so navigating away mid-request does
 * not warn or overwrite the next page's state.
 */
export function useAsync<T>(
  loader: () => Promise<T>,
  deps: React.DependencyList = [],
  options: { enabled?: boolean } = {},
): AsyncState<T> {
  const enabled = options.enabled ?? true;
  const [data, setData] = React.useState<T | null>(null);
  const [loading, setLoading] = React.useState(enabled);
  const [error, setError] = React.useState<string | null>(null);
  const [nonce, setNonce] = React.useState(0);

  const loaderRef = React.useRef(loader);
  loaderRef.current = loader;

  React.useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    let active = true;
    setLoading(true);
    setError(null);
    loaderRef
      .current()
      .then((result) => {
        if (active) setData(result);
      })
      .catch((caught: unknown) => {
        if (!active) return;
        setError(caught instanceof ApiError ? caught.message : "Something went wrong.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, nonce, ...deps]);

  const reload = React.useCallback(() => setNonce((value) => value + 1), []);

  return { data, loading, error, reload, setData };
}

/** Poll a value until `done` returns true. Used for analysis job progress. */
export function usePolling<T>(
  loader: () => Promise<T>,
  done: (value: T) => boolean,
  intervalMs = 2000,
  enabled = true,
) {
  const [data, setData] = React.useState<T | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const loaderRef = React.useRef(loader);
  loaderRef.current = loader;

  React.useEffect(() => {
    if (!enabled) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;

    const tick = async () => {
      try {
        const result = await loaderRef.current();
        if (!active) return;
        setData(result);
        setError(null);
        if (!done(result)) timer = setTimeout(tick, intervalMs);
      } catch (caught) {
        if (!active) return;
        setError(caught instanceof ApiError ? caught.message : "Polling failed.");
        timer = setTimeout(tick, intervalMs * 3);
      }
    };

    void tick();
    return () => {
      active = false;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, intervalMs]);

  return { data, error };
}
