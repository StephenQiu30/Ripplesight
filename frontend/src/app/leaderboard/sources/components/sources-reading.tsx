import Link from "next/link";

import { RunStamp, SourceStatus } from "@/components/leaderboard/reading-parts";
import { Badge } from "@/components/ui/badge";

export function SourcesReading({ data }: { data: HotKeyAPI.SourcesView }) {
  return (
    <main className="mx-auto max-w-6xl space-y-10 px-5 py-12 sm:px-8">
      <header className="max-w-3xl space-y-4">
        <p className="text-muted-foreground text-sm">模型榜</p>
        <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">
          评测来源与覆盖
        </h1>
        <p className="text-muted-foreground leading-7">
          查看各项证据的运营方、用途与固定预算。注册来源不等于本轮已经采集，交叉参考和系统任务不重复计票。
        </p>
        <RunStamp run={data.run} />
        <p className="text-muted-foreground text-xs leading-6">
          来源说明来自 AIHOT 2026-09-26
          固定注册表；成绩和证据时间以具体发布轮次为准。
        </p>
      </header>
      {data.groups.map((group) => (
        <section key={group.key} className="space-y-5">
          <div className="space-y-2">
            <h2 className="text-xl font-medium">{group.name}</h2>
            <p className="text-muted-foreground text-sm">{group.blurb}</p>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            {group.sources.map((source) => (
              <article
                key={source.key}
                className="bg-muted/40 space-y-3 rounded-xl p-5"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <Link
                    className="font-medium hover:underline"
                    href={`/leaderboard/sources/${source.key}`}
                  >
                    {source.name}
                  </Link>
                  <SourceStatus source={source} />
                </div>
                <p className="text-muted-foreground text-sm leading-6">
                  {source.description}
                </p>
                <p className="text-sm">
                  {source.operator} · 预算{" "}
                  <span className="font-mono">
                    {(source.weight * 100).toFixed(1)}%
                  </span>
                </p>
                <Badge variant="secondary">
                  {source.collected ? "本轮有证据" : "本轮无证据"}
                </Badge>
              </article>
            ))}
          </div>
        </section>
      ))}
    </main>
  );
}
