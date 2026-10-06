import * as UI from "@/components/ui/content";
import type { ReactNode } from "react";

import { LoginBrandStory } from "./login-brand-story";

export function LoginExperience({ children }: { children: ReactNode }) {
  return (
    <UI.Content className="grid min-w-0 gap-6 lg:flex-1 lg:grid-cols-2 lg:items-center lg:gap-16">
      <LoginBrandStory />
      {children}
    </UI.Content>
  );
}
