"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { LogOutIcon, UserRoundIcon } from "lucide-react";
import { useState } from "react";

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

export function AccountMenu() {
  const session = useIdentitySession();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (!session) return null;

  async function logout() {
    setBusy(true);
    setError("");
    try {
      await deleteIdentitySession();
      router.replace("/");
      router.refresh();
    } catch (failure) {
      setError(authErrorMessage(failure, "退出失败，请重试。"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="navigation" aria-label="账户菜单">
          <UserRoundIcon />
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
        {error && (
          <p role="alert" className="text-destructive px-2 py-2 text-xs">
            {error}
          </p>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
