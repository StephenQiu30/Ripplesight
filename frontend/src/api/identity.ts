// @ts-ignore
/* eslint-disable */
import request from "@/request";

/** Update Credentials PUT /api/identity/credentials */
export async function updateIdentityCredentials(
  body: HotKeyAPI.IdentityCredentialsUpdateInput,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.IdentitySessionView>("/api/identity/credentials", {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    data: body,
    ...(options || {}),
  });
}

/** Email Challenge POST /api/identity/email/challenges */
export async function sendEmailLoginCode(
  body: HotKeyAPI.EmailCodeInput,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.EmailChallengeView>(
    "/api/identity/email/challenges",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      data: body,
      ...(options || {}),
    },
  );
}

/** Email Login POST /api/identity/email/sessions */
export async function verifyEmailLoginCode(
  body: HotKeyAPI.VerifyEmailCodeInput,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.IdentitySessionView>(
    "/api/identity/email/sessions",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      data: body,
      ...(options || {}),
    },
  );
}

/** Github Start POST /api/identity/github/authorize */
export async function startGithubLogin(
  body: HotKeyAPI.GithubAuthorizationInput,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.GithubAuthorizationView>(
    "/api/identity/github/authorize",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      data: body,
      ...(options || {}),
    },
  );
}

/** Github Callback GET /api/identity/github/callback */
export async function completeGithubLogin(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.completeGithubLoginParams,
  options?: import("@/request").RequestOptions,
) {
  return request<any>("/api/identity/github/callback", {
    method: "GET",
    params: {
      ...params,
    },
    ...(options || {}),
  });
}

/** Options GET /api/identity/options */
export async function getLoginOptions(
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.LoginOptionsView>("/api/identity/options", {
    method: "GET",
    ...(options || {}),
  });
}

/** Session GET /api/identity/session */
export async function getIdentitySession(
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.IdentitySessionView>("/api/identity/session", {
    method: "GET",
    ...(options || {}),
  });
}

/** Logout DELETE /api/identity/session */
export async function deleteIdentitySession(
  options?: import("@/request").RequestOptions,
) {
  return request<any>("/api/identity/session", {
    method: "DELETE",
    ...(options || {}),
  });
}

/** Password Login POST /api/identity/sessions */
export async function createIdentitySession(
  body: HotKeyAPI.IdentityPasswordLoginInput,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.IdentitySessionView>("/api/identity/sessions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    data: body,
    ...(options || {}),
  });
}
