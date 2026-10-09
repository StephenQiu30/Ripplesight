"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { Content, Text } from "@/components/ui/content";
import { Spinner } from "@/components/ui/spinner";

const LoadingContext = createContext<(() => () => void) | null>(null);

export function GlobalLoadingProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState(0);
  const register = useCallback(() => {
    setPending((count) => count + 1);
    return () => setPending((count) => count - 1);
  }, []);

  return (
    <LoadingContext.Provider value={register}>
      {children}
      <Text
        role="status"
        aria-label="全局加载状态"
        aria-atomic="true"
        className="sr-only"
      >
        {pending > 0 ? "正在加载，请稍候。" : ""}
      </Text>
      {pending > 0 && (
        <Content
          data-slot="global-loading-indicator"
          aria-hidden="true"
          className="pointer-events-none fixed right-6 bottom-20 z-50 md:bottom-6"
        >
          <Spinner className="size-5" />
        </Content>
      )}
    </LoadingContext.Provider>
  );
}

/** Loading boundaries and transitions share one indicator, even when concurrent. */
export function LoadingSignal({ active = true }: { active?: boolean }) {
  const register = useContext(LoadingContext);
  useEffect(() => {
    if (active) return register?.();
  }, [active, register]);
  return null;
}
