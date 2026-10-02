import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty";

type PageStateProps = {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
};

export function PageState({
  eyebrow,
  title,
  description,
  action,
}: PageStateProps) {
  return (
    <div className="flex flex-1 items-center py-10">
      <Empty className="max-w-xl items-start p-0 text-left">
        <EmptyHeader className="max-w-xl items-start gap-4">
          <Badge variant="secondary">{eyebrow}</Badge>
          <EmptyTitle>
            <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">
              {title}
            </h1>
          </EmptyTitle>
          <EmptyDescription className="text-base leading-7">
            {description}
          </EmptyDescription>
        </EmptyHeader>
        {action ? (
          <EmptyContent className="mt-4 items-start">{action}</EmptyContent>
        ) : null}
      </Empty>
    </div>
  );
}
