import type { ReactNode } from "react";
import { AppShell } from "./AppShell";

export function ConsoleLayout({ title, actions, children }: { title: string; actions?: ReactNode; children: ReactNode }) {
  return <AppShell actions={actions} title={title}>{children}</AppShell>;
}
