// @ts-ignore
/* eslint-disable */
import request from "@/request";

/** 读取当前账户头像 GET /api/identity/avatar */
export async function getIdentityAvatar(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getIdentityAvatarParams,
  options?: import("@/request").RequestOptions,
) {
  return request<string>("/api/identity/avatar", {
    method: "GET",
    params: {
      ...params,
    },
    ...(options || {}),
  });
}

/** 上传并替换当前账户头像 PUT /api/identity/avatar */
export async function uploadIdentityAvatar(
  body: HotKeyAPI.IdentityAvatarInput,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.IdentitySessionView>("/api/identity/avatar", {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    data: body,
    ...(options || {}),
  });
}

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

/** 验证并绑定当前账户邮箱 PUT /api/identity/email/link */
export async function linkIdentityEmail(
  body: HotKeyAPI.VerifyEmailCodeInput,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.IdentitySessionView>("/api/identity/email/link", {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    data: body,
    ...(options || {}),
  });
}

/** 发送账户绑定邮箱验证码 POST /api/identity/email/link/challenges */
export async function sendEmailLinkCode(
  body: HotKeyAPI.EmailCodeInput,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.EmailChallengeView>(
    "/api/identity/email/link/challenges",
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

/** 连接当前账户的GitHub身份 POST /api/identity/github/link */
export async function startGithubLink(
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.GithubAuthorizationView>(
    "/api/identity/github/link",
    {
      method: "POST",
      ...(options || {}),
    },
  );
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

/** 更新当前账户基本资料 PUT /api/identity/profile */
export async function updateIdentityProfile(
  body: HotKeyAPI.IdentityProfileInput,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.IdentitySessionView>("/api/identity/profile", {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    data: body,
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
