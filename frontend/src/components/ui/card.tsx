import * as React from "react";
import { cn } from "cn";
import { Slot } from "radix-ui";

function Card({
  className,
  size = "default",
  variant = "default",
  ...props
}: React.ComponentProps<"div"> & {
  size?: "default" | "sm" | "reading" | "auth";
  variant?: "default" | "muted" | "inverse";
}) {
  return (
    <div
      data-slot="card"
      data-size={size}
      data-variant={variant}
      className={cn(
        "group/card bg-card text-card-foreground flex flex-col gap-(--card-spacing) overflow-hidden rounded-xl py-(--card-spacing) text-sm [--card-spacing:--spacing(4)] has-data-[slot=card-footer]:pb-0 has-[>img:first-child]:pt-0 data-[size=sm]:[--card-spacing:--spacing(3)] data-[size=sm]:has-data-[slot=card-footer]:pb-0 *:[img:first-child]:rounded-t-xl *:[img:last-child]:rounded-b-xl",
        variant === "muted" && "bg-muted",
        size === "reading" && "[--card-spacing:--spacing(5)]",
        size === "auth" &&
          "rounded-2xl [--card-spacing:--spacing(6)] sm:[--card-spacing:--spacing(9)]",
        variant === "inverse" && "bg-primary text-primary-foreground",
        className,
      )}
      {...props}
    />
  );
}

function CardHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-header"
      className={cn(
        "group/card-header @container/card-header grid auto-rows-min items-start gap-1 rounded-t-xl px-(--card-spacing) has-data-[slot=card-action]:grid-cols-[1fr_auto] has-data-[slot=card-description]:grid-rows-[auto_auto] [.border-b]:pb-(--card-spacing)",
        className,
      )}
      {...props}
    />
  );
}

function CardTitle({
  className,
  asChild = false,
  size = "default",
  ...props
}: React.ComponentProps<"div"> & {
  asChild?: boolean;
  size?: "default" | "section" | "post" | "form" | "sidebar";
}) {
  const Comp = asChild ? Slot.Root : "div";
  return (
    <Comp
      data-slot="card-title"
      className={cn(
        "font-heading text-base leading-snug font-medium group-data-[size=sm]/card:text-sm",
        size === "section" && "text-xl font-semibold",
        size === "form" && "text-[22px] leading-7 font-semibold",
        size === "sidebar" && "text-sm leading-6 font-semibold",
        size === "post" && "text-lg leading-7 font-semibold sm:text-xl",
        className,
      )}
      {...props}
    />
  );
}

function CardDescription({
  className,
  size = "default",
  ...props
}: React.ComponentProps<"div"> & { size?: "default" | "reading" | "caption" }) {
  return (
    <div
      data-slot="card-description"
      className={cn(
        "text-muted-foreground text-sm",
        size === "reading" && "text-base leading-6",
        size === "caption" && "text-[13px] leading-[18px]",
        className,
      )}
      {...props}
    />
  );
}

function CardAction({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-action"
      className={cn(
        "col-start-2 row-span-2 row-start-1 self-start justify-self-end",
        className,
      )}
      {...props}
    />
  );
}

function CardContent({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-content"
      className={cn("px-(--card-spacing)", className)}
      {...props}
    />
  );
}

function CardFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-footer"
      className={cn(
        "flex items-center px-(--card-spacing) pb-(--card-spacing)",
        className,
      )}
      {...props}
    />
  );
}

export {
  CardFooter,
  Card,
  CardHeader,
  CardTitle,
  CardAction,
  CardDescription,
  CardContent,
};
