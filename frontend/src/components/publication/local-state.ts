// Browser-only state adapted from AIHOT local-state.ts at 035f7b7f (MIT).
// Upstream license: backend/app/publication/AIHOT-LICENSE. Store IDs, never copies of licensed text.
export const SAVED_KEY = "hotkey.publication.saved.v1";
export const READ_KEY = "hotkey.publication.read.v1";
const DATES_KEY = "hotkey.publication.saved-dates.v1";
const THEME_KEY = "hotkey.publication.theme.v1";
export const LOCAL_CHANGE = "hotkey-publication-local-change";
export const STARRED_LIMIT = 500;
export const READ_LIMIT = 5000;
export const IMPORT_MAX_CHARS = 2_000_000;
const UUID_PATTERN =
  /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
type Theme = "light" | "dark" | "auto";
export type LocalBundle = {
  version: 1;
  starred: { id: string; savedAt: string }[];
  read: string[];
  theme: Theme | null;
};
type Reader = Pick<Storage, "getItem">;
export function localIds(
  storage: Reader,
  key: string,
  limit: number,
): string[] {
  try {
    const value: unknown = JSON.parse(storage.getItem(key) ?? "[]");
    return Array.isArray(value)
      ? [
          ...new Set(
            value.filter(
              (id): id is string =>
                typeof id === "string" && UUID_PATTERN.test(id),
            ),
          ),
        ].slice(0, limit)
      : [];
  } catch {
    return [];
  }
}
export function savedIds(storage: Reader): string[] {
  return localIds(storage, SAVED_KEY, STARRED_LIMIT);
}
export function readIds(storage: Reader): string[] {
  return localIds(storage, READ_KEY, READ_LIMIT);
}
function requireReadable(storage: Reader, key: string) {
  const raw = storage.getItem(key);
  if (raw === null) return;
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    throw new Error("已有本机数据损坏，未覆盖；请先导出原始数据或明确清空。");
  }
  if (!Array.isArray(value))
    throw new Error("已有本机数据损坏，未覆盖；请先导出原始数据或明确清空。");
}
export function localReadingIssue(storage: Reader): string | null {
  try {
    requireReadable(storage, SAVED_KEY);
    requireReadable(storage, READ_KEY);
    return null;
  } catch (error) {
    return error instanceof Error ? error.message : "本机存储不可读取。";
  }
}
function notify() {
  window.dispatchEvent(new Event(LOCAL_CHANGE));
}
export function editLocalData<T>(change: () => T): Promise<T> {
  const locks = typeof navigator !== "undefined" ? navigator.locks : undefined;
  if (!locks) {
    try {
      return Promise.resolve(change());
    } catch (error) {
      return Promise.reject(error);
    }
  }
  let entered = false;
  return locks
    .request("hotkey:publication-local-data", () => {
      entered = true;
      return change();
    })
    .catch((error) => {
      if (entered) throw error;
      return change();
    });
}
export function toggleSaved(id: string): Promise<boolean> {
  return editLocalData(() => {
    if (!UUID_PATTERN.test(id)) throw new Error("无效条目编号。");
    requireReadable(localStorage, SAVED_KEY);
    const current = savedIds(localStorage);
    const exists = current.includes(id);
    const next = exists
      ? current.filter((entry) => entry !== id)
      : [id, ...current].slice(0, STARRED_LIMIT);
    localStorage.setItem(SAVED_KEY, JSON.stringify(next));
    try {
      const dates = JSON.parse(localStorage.getItem(DATES_KEY) ?? "{}");
      if (dates && typeof dates === "object" && !Array.isArray(dates)) {
        dates[id] = new Date().toISOString();
        localStorage.setItem(
          DATES_KEY,
          JSON.stringify(
            Object.fromEntries(
              next.map((entry) => [
                entry,
                dates[entry] ?? new Date().toISOString(),
              ]),
            ),
          ),
        );
      }
    } catch {
      /* An optional date failure does not undo successfully stored IDs. */
    }
    notify();
    return !exists;
  });
}
export function removeSaved(id: string): Promise<void> {
  return editLocalData(() => {
    requireReadable(localStorage, SAVED_KEY);
    localStorage.setItem(
      SAVED_KEY,
      JSON.stringify(savedIds(localStorage).filter((entry) => entry !== id)),
    );
    notify();
  });
}
export function markRead(id: string): Promise<void> {
  return editLocalData(() => {
    if (!UUID_PATTERN.test(id)) return;
    requireReadable(localStorage, READ_KEY);
    localStorage.setItem(
      READ_KEY,
      JSON.stringify(
        [id, ...readIds(localStorage).filter((entry) => entry !== id)].slice(
          0,
          READ_LIMIT,
        ),
      ),
    );
    notify();
  });
}
function displayableDate(value: unknown): value is string {
  if (typeof value !== "string" || !Number.isFinite(Date.parse(value)))
    return false;
  try {
    new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai" }).format(
      new Date(value),
    );
    return true;
  } catch {
    return false;
  }
}
export function exportLocalBundle(storage: Reader): LocalBundle {
  requireReadable(storage, SAVED_KEY);
  requireReadable(storage, READ_KEY);
  let dates: Record<string, unknown> = {};
  try {
    const raw: unknown = JSON.parse(storage.getItem(DATES_KEY) ?? "{}");
    if (raw && typeof raw === "object" && !Array.isArray(raw))
      dates = raw as Record<string, unknown>;
  } catch {
    /* Legacy dates can be absent. */
  }
  const theme = storage.getItem(THEME_KEY);
  return {
    version: 1,
    starred: savedIds(storage).map((id) => ({
      id,
      savedAt: displayableDate(dates[id])
        ? dates[id]
        : new Date().toISOString(),
    })),
    read: readIds(storage),
    theme:
      theme === "light" || theme === "dark" || theme === "auto" ? theme : null,
  };
}
export function parseLocalImport(raw: string): {
  starred: { id: string; savedAt: string }[];
  read: string[];
  theme: Theme | null;
  skipped: number;
} {
  if (raw.length > IMPORT_MAX_CHARS)
    throw new Error("文件过大，上限 2,000,000 字符。");
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    throw new Error("不是有效 JSON，未改动本机数据。");
  }
  if (
    !value ||
    typeof value !== "object" ||
    !("version" in value) ||
    value.version !== 1
  )
    throw new Error("需要 version: 1 的收藏备份文件。");
  const data = value as Partial<LocalBundle>;
  if (!Array.isArray(data.starred) || !Array.isArray(data.read))
    throw new Error("收藏与已读列表格式无效，未改动本机数据。");
  let skipped = 0;
  const starred = data.starred.filter((entry) => {
    const valid =
      entry &&
      typeof entry === "object" &&
      typeof entry.id === "string" &&
      UUID_PATTERN.test(entry.id) &&
      displayableDate(entry.savedAt);
    if (!valid) skipped++;
    return valid;
  });
  const read = data.read.filter((id) => {
    const valid = typeof id === "string" && UUID_PATTERN.test(id);
    if (!valid) skipped++;
    return valid;
  });
  return {
    starred,
    read,
    theme:
      data.theme === "light" || data.theme === "dark" || data.theme === "auto"
        ? data.theme
        : null,
    skipped,
  };
}
export function importLocalBundle(raw: string): Promise<{
  savedAdded: number;
  readAdded: number;
  skipped: number;
  readFailed: boolean;
}> {
  const incoming = parseLocalImport(raw);
  return editLocalData(() => {
    requireReadable(localStorage, SAVED_KEY);
    requireReadable(localStorage, READ_KEY);
    const current = exportLocalBundle(localStorage);
    const saved = new Set(current.starred.map((entry) => entry.id));
    const read = new Set(current.read);
    const additions = incoming.starred.filter((entry) => {
      if (saved.has(entry.id)) return false;
      saved.add(entry.id);
      return true;
    });
    const accepted = additions.slice(0, STARRED_LIMIT - current.starred.length);
    const readNew = incoming.read.filter((id) => {
      if (read.has(id)) return false;
      read.add(id);
      return true;
    });
    const readAccepted = readNew.slice(0, READ_LIMIT - current.read.length);
    localStorage.setItem(
      SAVED_KEY,
      JSON.stringify(
        [...current.starred, ...accepted].map((entry) => entry.id),
      ),
    );
    try {
      localStorage.setItem(
        DATES_KEY,
        JSON.stringify(
          Object.fromEntries(
            [...current.starred, ...accepted].map((entry) => [
              entry.id,
              entry.savedAt,
            ]),
          ),
        ),
      );
    } catch {
      /* Successfully merged IDs remain useful. */
    }
    let readFailed = false;
    try {
      localStorage.setItem(
        READ_KEY,
        JSON.stringify([...current.read, ...readAccepted]),
      );
    } catch {
      readFailed = true;
    }
    if (!localStorage.getItem(THEME_KEY) && incoming.theme) {
      try {
        localStorage.setItem(THEME_KEY, incoming.theme);
        applyTheme(incoming.theme);
      } catch {
        /* Import's saved/read result remains explicit. */
      }
    }
    notify();
    return {
      savedAdded: accepted.length,
      readAdded: readFailed ? 0 : readAccepted.length,
      skipped:
        incoming.skipped +
        additions.length -
        accepted.length +
        readNew.length -
        readAccepted.length,
      readFailed,
    };
  });
}
export function applyTheme(theme: Theme) {
  document.documentElement.classList.toggle(
    "dark",
    theme === "dark" ||
      (theme === "auto" && matchMedia("(prefers-color-scheme: dark)").matches),
  );
}
export function themePreference(storage: Reader): Theme {
  const theme = storage.getItem(THEME_KEY);
  return theme === "light" || theme === "dark" ? theme : "auto";
}
export function saveTheme(theme: Theme) {
  localStorage.setItem(THEME_KEY, theme);
  applyTheme(theme);
  notify();
}
export function clearLocalReading(): Promise<void> {
  return editLocalData(() => {
    for (const key of [SAVED_KEY, READ_KEY, DATES_KEY])
      localStorage.removeItem(key);
    notify();
  });
}
