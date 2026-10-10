"use client";

import { Content, Text } from "@/components/ui/content";
import { UserAvatar } from "./user-avatar";

export function accountDisplayName(user: HotKeyAPI.IdentityUserView) {
  return /^user_[a-f\d]{32}$/i.test(user.username) ? "我的账户" : user.username;
}

export function UserSummary({
  user,
  detailed = false,
  collapsible = false,
}: {
  user: HotKeyAPI.IdentityUserView;
  detailed?: boolean;
  collapsible?: boolean;
}) {
  const name = accountDisplayName(user);
  return (
    <Content className="flex min-w-0 items-center gap-3">
      <Content aria-hidden="true" className="shrink-0">
        <UserAvatar user={user} className="size-8" />
      </Content>
      <Content
        className={
          collapsible
            ? "flex min-w-0 flex-1 flex-col text-left group-data-[collapsible=icon]:hidden"
            : "flex min-w-0 flex-1 flex-col text-left"
        }
      >
        <Text
          as="strong"
          size="sm"
          className={detailed ? "break-all" : "truncate"}
        >
          {name}
        </Text>
        <Text
          as="span"
          size="xs"
          tone="muted"
          className={detailed ? "break-all" : "truncate"}
        >
          {user.email ?? (detailed ? "尚未绑定邮箱" : "个人工作台")}
        </Text>
      </Content>
    </Content>
  );
}
