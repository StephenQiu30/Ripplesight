"use client";

import { createContext, useContext, type ReactNode } from "react";

const IdentitySessionContext =
  createContext<HotKeyAPI.IdentitySessionView | null>(null);

export function IdentitySessionProvider({
  children,
  session,
}: {
  children: ReactNode;
  session: HotKeyAPI.IdentitySessionView | null;
}) {
  return (
    <IdentitySessionContext.Provider value={session}>
      {children}
    </IdentitySessionContext.Provider>
  );
}

export function useIdentitySession() {
  return useContext(IdentitySessionContext);
}
