"use client";

import {
  createContext,
  useContext,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { LoginDialog } from "./login-dialog";

const LoginContext = createContext<((returnTo: string) => void) | null>(null);

export function LoginProvider({ children }: { children: ReactNode }) {
  const [target, setTarget] = useState<string | null>(null);
  const origin = useRef<HTMLElement | null>(null);
  return (
    <LoginContext.Provider
      value={(returnTo) => {
        origin.current =
          document.activeElement instanceof HTMLElement
            ? document.activeElement
            : null;
        setTarget(returnTo);
      }}
    >
      {children}
      <LoginDialog
        open={target !== null}
        returnTo={target ?? "/topics"}
        onClose={() => setTarget(null)}
        onAuthenticated={() => setTarget(null)}
        onRestoreFocus={() => origin.current?.focus({ preventScroll: true })}
      />
    </LoginContext.Provider>
  );
}

export function useLoginDialog() {
  return useContext(LoginContext);
}
