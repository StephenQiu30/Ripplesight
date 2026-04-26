"use client";

import * as ToastPrimitive from "@radix-ui/react-toast";
import { X } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/utils";

export const ToastProvider = ToastPrimitive.Provider;
export const ToastViewport = React.forwardRef<React.ElementRef<typeof ToastPrimitive.Viewport>, React.ComponentPropsWithoutRef<typeof ToastPrimitive.Viewport>>(
  ({ className, ...props }, ref) => <ToastPrimitive.Viewport className={cn("fixed bottom-4 right-4 z-50 grid w-[calc(100%-2rem)] max-w-sm gap-2", className)} ref={ref} {...props} />
);
ToastViewport.displayName = ToastPrimitive.Viewport.displayName;

export const Toast = React.forwardRef<React.ElementRef<typeof ToastPrimitive.Root>, React.ComponentPropsWithoutRef<typeof ToastPrimitive.Root>>(
  ({ className, ...props }, ref) => <ToastPrimitive.Root className={cn("rounded-lg border border-border bg-card p-4 text-card-foreground shadow-lg", className)} ref={ref} {...props} />
);
Toast.displayName = ToastPrimitive.Root.displayName;

export const ToastTitle = React.forwardRef<React.ElementRef<typeof ToastPrimitive.Title>, React.ComponentPropsWithoutRef<typeof ToastPrimitive.Title>>(
  ({ className, ...props }, ref) => <ToastPrimitive.Title className={cn("text-sm font-semibold", className)} ref={ref} {...props} />
);
ToastTitle.displayName = ToastPrimitive.Title.displayName;

export const ToastDescription = React.forwardRef<React.ElementRef<typeof ToastPrimitive.Description>, React.ComponentPropsWithoutRef<typeof ToastPrimitive.Description>>(
  ({ className, ...props }, ref) => <ToastPrimitive.Description className={cn("mt-1 text-sm text-muted-foreground", className)} ref={ref} {...props} />
);
ToastDescription.displayName = ToastPrimitive.Description.displayName;

export const ToastClose = React.forwardRef<React.ElementRef<typeof ToastPrimitive.Close>, React.ComponentPropsWithoutRef<typeof ToastPrimitive.Close>>(
  ({ className, ...props }, ref) => (
    <ToastPrimitive.Close className={cn("absolute right-2 top-2 rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground", className)} ref={ref} {...props}>
      <X className="h-4 w-4" />
    </ToastPrimitive.Close>
  )
);
ToastClose.displayName = ToastPrimitive.Close.displayName;
