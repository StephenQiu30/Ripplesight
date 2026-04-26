"use client";

import * as TabsPrimitive from "@radix-ui/react-tabs";
import * as React from "react";
import { cn } from "@/lib/utils";

export const Tabs = TabsPrimitive.Root;

export const TabsList = React.forwardRef<React.ElementRef<typeof TabsPrimitive.List>, React.ComponentPropsWithoutRef<typeof TabsPrimitive.List>>(
  ({ className, ...props }, ref) => <TabsPrimitive.List className={cn("inline-flex min-h-11 items-center rounded-lg bg-muted p-1", className)} ref={ref} {...props} />
);
TabsList.displayName = TabsPrimitive.List.displayName;

export const TabsTrigger = React.forwardRef<React.ElementRef<typeof TabsPrimitive.Trigger>, React.ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>>(
  ({ className, ...props }, ref) => (
    <TabsPrimitive.Trigger
      className={cn("inline-flex min-h-9 items-center justify-center rounded-md px-3 py-1.5 text-sm font-semibold text-muted-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring data-[state=active]:bg-card data-[state=active]:text-foreground data-[state=active]:shadow-sm", className)}
      ref={ref}
      {...props}
    />
  )
);
TabsTrigger.displayName = TabsPrimitive.Trigger.displayName;

export const TabsContent = React.forwardRef<React.ElementRef<typeof TabsPrimitive.Content>, React.ComponentPropsWithoutRef<typeof TabsPrimitive.Content>>(
  ({ className, ...props }, ref) => <TabsPrimitive.Content className={cn("mt-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring", className)} ref={ref} {...props} />
);
TabsContent.displayName = TabsPrimitive.Content.displayName;
