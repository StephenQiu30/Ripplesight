import { fileURLToPath } from "node:url";
import { ESLint } from "eslint";
import { describe, expect, it } from "vitest";

const eslint = new ESLint({
  cwd: fileURLToPath(new URL("../..", import.meta.url)),
});

async function check(code: string, filePath = "src/app/example/page.tsx") {
  const [result] = await eslint.lintText(code, { filePath });
  return result.messages.filter(
    (message) => message.ruleId === "design-system/conventions",
  );
}

describe("design system conventions", () => {
  it.each([
    '<Content className="space-y-4" />',
    '<Content className={cn("flex", active && "md:space-x-2")} />',
    '<Content className={cn({ "bg-blue-500": active })} />',
    '<Content className="dark:bg-muted" />',
    '<Content className="text-[#123456]" />',
    '<Content className={`flex ${active ? "gap-2" : "gap-4"}`} />',
  ])("rejects inconsistent call-site styling: %s", async (jsx) => {
    expect(await check(`export const Example = () => ${jsx};`)).toHaveLength(1);
  });

  it("accepts semantic tokens and conditional layout classes", async () => {
    expect(
      await check(
        'export const Example = () => <Content className={cn("flex bg-muted text-muted-foreground", active && "gap-2")} />;',
      ),
    ).toEqual([]);
  });

  it("checks mapped items through expressions and aliased imports", async () => {
    const imports =
      'import { SelectContent as Popup, SelectGroup as Group, SelectItem as Option } from "@/components/ui/select";';
    expect(
      await check(
        `${imports} export const Example = () => <Popup>{items.map(item => <Option value={item.id}>{item.name}</Option>)}</Popup>;`,
      ),
    ).toHaveLength(1);
    expect(
      await check(
        `${imports} export const Example = () => <Popup><Group>{items.map(item => <Option value={item.id}>{item.name}</Option>)}</Group></Popup>;`,
      ),
    ).toEqual([]);
  });

  it("accepts composition where a wrapper owns the group", async () => {
    expect(
      await check(
        'import { SelectContent, SelectGroup, SelectItem } from "@/components/ui/select"; const Choice = ({children}) => <SelectContent><SelectGroup>{children}</SelectGroup></SelectContent>; export const Example = () => <Choice><SelectItem value="a">A</SelectItem></Choice>;',
      ),
    ).toEqual([]);
  });

  it("checks menu labels and tab triggers without changing unrelated names", async () => {
    expect(
      await check(
        'import { DropdownMenuContent, DropdownMenuLabel } from "@/components/ui/dropdown-menu"; export const Example = () => <DropdownMenuContent><DropdownMenuLabel>Account</DropdownMenuLabel></DropdownMenuContent>;',
      ),
    ).toHaveLength(1);
    expect(
      await check(
        'import { Tabs, TabsTrigger } from "@/components/ui/tabs"; export const Example = () => <Tabs><TabsTrigger value="a">A</TabsTrigger></Tabs>;',
      ),
    ).toHaveLength(1);
    expect(
      await check(
        'import { SelectContent, SelectItem } from "other-library"; export const Example = () => <SelectContent><SelectItem /></SelectContent>;',
      ),
    ).toEqual([]);
  });

  it("requires button icon markers through asChild and rejects icon sizing", async () => {
    const imports =
      'import { Search as SearchIcon } from "lucide-react"; import { Button } from "@/components/ui/button";';
    expect(
      await check(
        `${imports} export const Example = () => <Button asChild><Link href="/"><SearchIcon /></Link></Button>;`,
      ),
    ).toHaveLength(1);
    expect(
      await check(
        `${imports} export const Example = () => <Button><SearchIcon data-icon="inline-start" className="size-4" /></Button>;`,
      ),
    ).toHaveLength(1);
    expect(
      await check(
        `${imports} export const Example = () => <Button><SearchIcon data-icon="inline-start" />Search</Button>;`,
      ),
    ).toEqual([]);
  });

  it("leaves upstream primitives and tests outside call-site restrictions", async () => {
    const code =
      'export const Example = () => <div className="dark:bg-muted space-y-2" />;';
    expect(await check(code, "src/components/ui/example.tsx")).toEqual([]);
    expect(await check(code, "tests/components/example.test.tsx")).toEqual([]);
  });

  it("allows standalone illustrations whose container does not own icon sizing", async () => {
    expect(
      await check(
        'import { CheckIcon } from "lucide-react"; import { Item } from "@/components/ui/item"; export const Example = () => <Item><UI.Content><CheckIcon className="size-4" /></UI.Content></Item>;',
      ),
    ).toEqual([]);
  });
});
