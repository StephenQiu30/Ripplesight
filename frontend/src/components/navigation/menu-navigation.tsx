"use client";

import type { LucideIcon } from "lucide-react";
import { AuthLink } from "@/components/auth/auth-link";
import {
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
} from "@/components/ui/dropdown-menu";

export type MenuDestination = {
  href: string;
  label: string;
  icon: LucideIcon;
};

// Both account and site navigation use the same accessible link rows.
export function MenuNavigation({
  label,
  items,
  current,
}: {
  label: string;
  items: MenuDestination[];
  current?: string;
}) {
  return (
    <DropdownMenuGroup aria-label={label}>
      <DropdownMenuLabel>{label}</DropdownMenuLabel>
      {items.map(({ href, label: title, icon: Icon }) => (
        <DropdownMenuItem key={href} asChild>
          <AuthLink
            href={href}
            aria-current={current === href ? "page" : undefined}
          >
            <Icon aria-hidden="true" />
            {title}
          </AuthLink>
        </DropdownMenuItem>
      ))}
    </DropdownMenuGroup>
  );
}
