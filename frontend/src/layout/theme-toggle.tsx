"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { MonitorIcon, MoonIcon, SunIcon } from "lucide-react";
import { toast } from "sonner";

import {
  LOCAL_CHANGE,
  applyTheme,
  saveTheme,
  themePreference,
  type Theme,
} from "@/components/publication/local-state";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const themes = [
  { value: "light", label: "浅色", icon: SunIcon },
  { value: "dark", label: "深色", icon: MoonIcon },
  { value: "auto", label: "跟随系统", icon: MonitorIcon },
] as const;

const ThemeContext = createContext<{
  theme: Theme;
  changeTheme: (theme: Theme) => void;
} | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>("auto");

  useEffect(() => {
    const update = () => {
      try {
        setTheme(themePreference(localStorage));
      } catch {
        /* Keep the current theme when browser storage is unavailable. */
      }
    };
    const frame = requestAnimationFrame(update);
    window.addEventListener("storage", update);
    window.addEventListener(LOCAL_CHANGE, update);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("storage", update);
      window.removeEventListener(LOCAL_CHANGE, update);
    };
  }, []);

  useEffect(() => {
    const update = () => applyTheme(theme);
    update();
    const media = matchMedia("(prefers-color-scheme: dark)");
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, [theme]);

  function changeTheme(value: Theme) {
    setTheme(value);
    try {
      saveTheme(value);
    } catch {
      applyTheme(value);
      toast.error("主题已应用，但本机存储不可用，未保存偏好。");
    }
  }

  return (
    <ThemeContext.Provider value={{ theme, changeTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function ThemeToggle() {
  const context = useContext(ThemeContext);
  if (!context) throw new Error("ThemeToggle requires ThemeProvider");
  const { theme, changeTheme } = context;
  const current = themes.find((option) => option.value === theme)!;
  const Icon = current.icon;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="size-11 md:size-8"
          aria-label={`切换主题（当前：${current.label}）`}
        >
          <Icon data-icon="inline-start" aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-40" aria-label="主题">
        <DropdownMenuGroup>
          <DropdownMenuLabel>主题</DropdownMenuLabel>
          <DropdownMenuRadioGroup
            value={theme}
            onValueChange={(value) => {
              if (value === "light" || value === "dark" || value === "auto")
                changeTheme(value);
            }}
          >
            {themes.map(({ value, label, icon: OptionIcon }) => (
              <DropdownMenuRadioItem
                key={value}
                value={value}
                className="min-h-11 md:min-h-8"
              >
                <OptionIcon aria-hidden="true" />
                {label}
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
