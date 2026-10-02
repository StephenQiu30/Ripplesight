import { headers } from "next/headers";

export async function readLayoutSession(): Promise<HotKeyAPI.IdentitySessionView | null> {
  const verified = (await headers()).get("x-hotkey-session");
  if (!verified) return null;
  try {
    return JSON.parse(
      decodeURIComponent(verified),
    ) as HotKeyAPI.IdentitySessionView;
  } catch {
    return null;
  }
}
