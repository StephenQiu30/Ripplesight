import * as UI from "@/components/ui/content";
import type { ReactNode } from "react";

import { LoginBrandStory } from "./login-brand-story";

export function LoginExperience({ children }: { children: ReactNode }) {
  return (
    <UI.Content className="grid flex-1 items-center gap-12 py-4 lg:grid-cols-2 lg:gap-20 xl:gap-28">
      <LoginBrandStory />
      {children}
    </UI.Content>
  );
}
