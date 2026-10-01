import Link from "next/link";
import { ArrowRightIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

export type HomeInfoView = "guide" | "example";

type CapabilityOverviewProps = {
  view: HomeInfoView | null;
  onClose: () => void;
  onCloseAutoFocus: (event: Event) => void;
};

const steps = [
  ["选一件你在意的事", "填写名称和关键词，例如一个品牌、一款产品或一个话题。"],
  ["按你的习惯设置", "选择可用来源和更新频率，需要时再设置包含或排除条件。"],
  [
    "保存后，自由调整",
    "在「我的关注」里查看、修改或恢复关注。新建关注默认暂停。",
  ],
];

export function CapabilityOverview({
  view,
  onClose,
  onCloseAutoFocus,
}: CapabilityOverviewProps) {
  return (
    <Dialog open={view !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        className="max-h-svh overflow-y-auto"
        onCloseAutoFocus={onCloseAutoFocus}
      >
        <DialogHeader>
          <DialogTitle>
            {view === "guide"
              ? "简单设置，持续了解。"
              : "一个关注，整理一类变化。"}
          </DialogTitle>
          <DialogDescription>
            {view === "guide"
              ? "从关键词开始，按自己的节奏了解变化。"
              : "以「AI 开发工具」为例，先设置关注，再查看相关线索。"}
          </DialogDescription>
        </DialogHeader>
        {view === "guide" ? (
          <ol className="my-4 flex flex-col gap-6">
            {steps.map(([title, description], index) => (
              <li key={title} className="flex gap-4">
                <span className="text-muted-foreground font-mono text-xs">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <div>
                  <h3 className="font-medium">{title}</h3>
                  <p className="text-muted-foreground mt-2 leading-relaxed">
                    {description}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        ) : (
          <div className="my-4 flex flex-col gap-6">
            <dl className="flex flex-col gap-4">
              <div>
                <dt className="text-muted-foreground">关注关键词</dt>
                <dd className="mt-1">AI 编程 · Coding agent</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">更新频率</dt>
                <dd className="mt-1">每 30 分钟</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">可能关注的内容</dt>
                <dd className="mt-1">产品更新、发布记录与社区讨论。</dd>
              </div>
            </dl>
            <p className="text-muted-foreground text-xs leading-relaxed">
              内容仅为设置示例，实际来源以创建页的可用配置为准。
            </p>
          </div>
        )}
        <Button asChild size="hero">
          <Link href="/monitors/new">
            创建关注
            <ArrowRightIcon data-icon="inline-end" />
          </Link>
        </Button>
      </DialogContent>
    </Dialog>
  );
}
