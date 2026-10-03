import { LoginExperience } from "./components/login-experience";
import {
  LoginFormLayout,
  LoginFormSkeleton,
} from "./components/login-form-layout";

export default function Loading() {
  return (
    <LoginExperience>
      <LoginFormLayout loading>
        <LoginFormSkeleton />
      </LoginFormLayout>
    </LoginExperience>
  );
}
