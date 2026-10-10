"use client";
import * as UI from "@/components/ui/content";

import { usePathname, useRouter } from "next/navigation";
import {
  EyeIcon,
  FileTextIcon,
  LayoutDashboardIcon,
  LogOutIcon,
  SettingsIcon,
  ChevronsUpDownIcon,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { deleteIdentitySession } from "@/api/identity";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { authErrorMessage } from "./auth-error";
import { useIdentitySession } from "./session-context";
import { UserAvatar } from "./user-avatar";
import { accountDisplayName, UserSummary } from "./user-summary";
import { MenuNavigation } from "@/components/navigation/menu-navigation";

export function AccountMenu({ compact = false }: { compact?: boolean }) {
  const session = useIdentitySession();
  const router = useRouter();
  const pathname = usePathname() ?? "/";
  const [busy, setBusy] = useState(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  if (!session) return null;

  async function logout() {
    if (busy) return;
    setBusy(true);
    try {
      await deleteIdentitySession();
      if (!mounted.current) return;
      router.replace("/");
      router.refresh();
    } catch (failure) {
      if (mounted.current)
        toast.error(authErrorMessage(failure, "退出失败，请重试。"));
    } finally {
      if (mounted.current) setBusy(false);
    }
  }

  const destinations = [
    { href: "/workspace", label: "我的工作台", icon: LayoutDashboardIcon },
    { href: "/topics", label: "我的关注", icon: EyeIcon },
    { href: "/reports", label: "我的报告", icon: FileTextIcon },
    { href: "/account", label: "账户设置", icon: SettingsIcon },
  ];
  const current = destinations.find(
    ({ href }) => pathname === href || pathname.startsWith(`${href}/`),
  )?.href;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size={compact ? "icon-lg" : "account"}
          aria-label="账户菜单"
          title={accountDisplayName(session.user)}
          className={compact ? "size-11" : undefined}
        >
          {compact ? (
            <UserAvatar user={session.user} className="size-8" />
          ) : (
            <>
              <UI.Content className="min-w-0 flex-1">
                <UserSummary user={session.user} collapsible />
              </UI.Content>
              <ChevronsUpDownIcon
                aria-hidden="true"
                data-icon="inline-end"
                className="group-data-[collapsible=icon]:hidden"
              />
            </>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        side={compact ? "bottom" : "top"}
        align={compact ? "end" : "start"}
        sideOffset={8}
        collisionPadding={16}
        variant="navigation"
        aria-label="账户菜单"
      >
        <UI.Content className="flex flex-col gap-3 px-3 py-3">
          <UserSummary user={session.user} detailed />
          {accountDisplayName(session.user) !== session.user.username && (
            <UI.Content className="flex min-w-0 flex-col gap-1">
              <UI.Text size="xs" tone="muted">
                用户名
              </UI.Text>
              <UI.Text size="xs" className="break-all">
                {session.user.username}
              </UI.Text>
            </UI.Content>
          )}
        </UI.Content>
        <DropdownMenuSeparator />
        <MenuNavigation
          label="个人空间"
          items={destinations}
          current={current}
        />
        <DropdownMenuSeparator />
        <DropdownMenuGroup aria-label="会话">
          <DropdownMenuItem
            disabled={busy}
            onSelect={(event) => {
              event.preventDefault();
              void logout();
            }}
          >
            <LogOutIcon aria-hidden="true" />
            {busy ? "正在退出…" : "退出登录"}
          </DropdownMenuItem>
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
