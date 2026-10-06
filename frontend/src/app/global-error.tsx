"use client";
import * as UI from "@/components/ui/content";

import { RotateCcwIcon } from "lucide-react";

import { PageState } from "@/components/system/page-state";
import { Button } from "@/components/ui/button";
import { BasicLayout } from "@/layout/basic-layout";
import { layoutFontClassName } from "@/layout/layout-fonts";

import "./globals.css";

type GlobalErrorProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function GlobalError({ reset }: GlobalErrorProps) {
  return (
    <UI.DocumentRoot lang="zh-CN" className={layoutFontClassName}>
      <UI.DocumentBody className="overflow-hidden print:overflow-visible">
        <BasicLayout>
          <PageState
            state="error"
            eyebrow="应用恢复"
            title="知微见澜暂时无法显示。"
            description="请重新加载应用。错误详情不会显示在公开页面中。"
            action={
              <Button type="button" onClick={reset} size="lg">
                重新加载
                <RotateCcwIcon data-icon="inline-end" />
              </Button>
            }
          />
        </BasicLayout>
      </UI.DocumentBody>
    </UI.DocumentRoot>
  );
}
