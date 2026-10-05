import * as UI from "@/components/ui/content";
import Image from "next/image";

export function LoginBrandStory() {
  return (
    <UI.Content
      as="aside"
      className="relative hidden min-h-144 lg:block"
      aria-label="知微见澜"
    >
      <UI.Content className="relative z-10">
        <UI.Text className="text-muted-foreground mb-6 text-sm tracking-widest">
          RIPPLESIGHT
        </UI.Text>
        <UI.Heading
          level={2}
          className="text-5xl leading-tight font-semibold tracking-tight xl:text-7xl"
        >
          从一点线索，
          <UI.TextBreak />
          看见层层变化。
        </UI.Heading>
        <UI.Text className="text-muted-foreground mt-6 text-xl leading-relaxed">
          你的关注，自有回响。
        </UI.Text>
      </UI.Content>
      <Image
        src="/brand/login-ripple.png"
        alt=""
        aria-hidden="true"
        width={1717}
        height={916}
        sizes="(min-width: 1280px) 960px, 800px"
        loading="eager"
        className="pointer-events-none absolute top-40 left-1/2 h-auto w-200 max-w-none -translate-x-1/2 xl:w-240 dark:invert"
      />
    </UI.Content>
  );
}
