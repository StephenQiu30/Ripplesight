"use client";
import { Button } from "@/components/ui/button";
export function EditionPrint() {
  return (
    <Button
      variant="outline"
      className="print:hidden"
      onClick={() => window.print()}
    >
      打印这份刊物
    </Button>
  );
}
