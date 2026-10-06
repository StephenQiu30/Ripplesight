import { screen } from "@testing-library/react";
import { expect } from "vitest";

export function expectOnePageHeading() {
  expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
}
