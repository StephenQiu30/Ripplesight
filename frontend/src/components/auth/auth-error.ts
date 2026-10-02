import { ApiRequestError } from "@/request";

export function authErrorMessage(error: unknown, fallback: string) {
  if (!(error instanceof ApiRequestError)) return fallback;
  if (error.kind === "cancelled") return "请求已取消，可以重新操作。";
  if (error.kind === "network" || error.kind === "timeout")
    return "暂时无法连接服务，请稍后重试。";
  if (error.status === 429) return "请求过于频繁，请稍后重试。";
  if (error.status === 401) return "验证未通过，请检查输入后重试。";
  if (error.status === 503)
    return "此登录方式暂时不可用，请选择其他方式或稍后重试。";
  if (error.status === 422)
    return (
      error.details?.map((detail) => detail.message).join("；") ||
      "请检查输入内容。"
    );
  return error.message || fallback;
}
