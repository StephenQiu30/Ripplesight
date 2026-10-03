"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { LogOutIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { deleteIdentitySession } from "@/api/identity";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { authErrorMessage } from "./auth-error";
import { useIdentitySession } from "./session-context";
import { UserAvatar } from "./user-avatar";

export function AccountMenu() {
  const session = useIdentitySession();
  const router = useRouter();
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

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="navigation" aria-label="账户菜单">
          <UserAvatar user={session.user} className="size-7" />
          <span className="hidden max-w-24 truncate lg:inline">
            {session.user.username}
          </span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="max-w-64 min-w-44">
        <DropdownMenuLabel className="truncate">
          {session.user.username}
        </DropdownMenuLabel>
        <DropdownMenuGroup>
          <DropdownMenuItem asChild>
            <Link href="/account">账户设置</Link>
          </DropdownMenuItem>
          <DropdownMenuItem
            disabled={busy}
            onSelect={(event) => {
              event.preventDefault();
              void logout();
            }}
          >
            <LogOutIcon />
            {busy ? "正在退出…" : "退出登录"}
          </DropdownMenuItem>
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
