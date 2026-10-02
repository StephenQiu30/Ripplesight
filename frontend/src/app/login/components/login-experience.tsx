import { LoginBrandStory } from "./login-brand-story";
import { LoginForm } from "./login-form";

export function LoginExperience({
  returnTo,
  oauthFailed,
}: {
  returnTo: string;
  oauthFailed: boolean;
}) {
  return (
    <div className="grid flex-1 items-center gap-12 py-4 lg:grid-cols-2 lg:gap-20 xl:gap-28">
      <LoginBrandStory />
      <LoginForm returnTo={returnTo} oauthFailed={oauthFailed} />
    </div>
  );
}
