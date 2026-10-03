import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { getIdentitySession } from "@/api/identity";
import { isPublicPagePath, safeReturnTo } from "@/components/auth/access";
import { ApiRequestError } from "@/request";

function createContentSecurityPolicy(nonce: string): string {
  const isDevelopment = process.env.NODE_ENV === "development";

  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${isDevelopment ? " 'unsafe-eval'" : ""}`,
    // Sonner 2.0.8 injects its official stylesheet without a nonce.
    // Permit only that exact stylesheet; the dependency hash is verified in tests.
    `style-src 'self'${isDevelopment ? " 'unsafe-inline'" : ` 'nonce-${nonce}' 'sha256-StEaX+se6YS7pqjzrzMIA0KaX9zF/8zAhvQXZAe5epY='`}`,
    "img-src 'self' blob: data:",
    "font-src 'self' data:",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    ...(isDevelopment ? [] : ["upgrade-insecure-requests"]),
  ].join("; ");
}

function setSecurityHeaders(
  response: NextResponse,
  contentSecurityPolicy: string,
  clearInvalidSession = false,
): NextResponse {
  response.headers.set("Content-Security-Policy", contentSecurityPolicy);
  response.headers.set("Referrer-Policy", "strict-origin-when-cross-origin");
  response.headers.set("X-Content-Type-Options", "nosniff");
  response.headers.set("Cache-Control", "private, no-store");
  if (clearInvalidSession) {
    response.cookies.delete("hotkey_session");
    response.cookies.delete("hotkey_csrf");
  }
  return response;
}

export async function proxy(request: NextRequest): Promise<NextResponse> {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const contentSecurityPolicy = createContentSecurityPolicy(nonce);
  const requestHeaders = new Headers(request.headers);
  requestHeaders.delete("x-hotkey-session");
  requestHeaders.delete("x-hotkey-session-error");
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", contentSecurityPolicy);

  const publicPage = isPublicPagePath(request.nextUrl.pathname);
  const sessionCookie = request.cookies.get("hotkey_session")?.value;
  const csrfCookie = request.cookies.get("hotkey_csrf")?.value;
  let authenticated = false;
  let hasPassword = false;
  let invalidSession = false;
  if (sessionCookie) {
    try {
      const session = await getIdentitySession({
        headers: {
          Cookie: [
            `hotkey_session=${sessionCookie}`,
            ...(csrfCookie ? [`hotkey_csrf=${csrfCookie}`] : []),
          ].join("; "),
        },
      });
      requestHeaders.set(
        "x-hotkey-session",
        encodeURIComponent(JSON.stringify(session)),
      );
      authenticated = true;
      hasPassword = session.user.has_password;
    } catch (error) {
      if (!(error instanceof ApiRequestError && error.status === 401)) {
        requestHeaders.set("x-hotkey-session-error", "1");
        const recoveryUrl = new URL("/login", request.url);
        recoveryUrl.searchParams.set(
          "returnTo",
          safeReturnTo(`${request.nextUrl.pathname}${request.nextUrl.search}`),
        );
        return setSecurityHeaders(
          NextResponse.rewrite(recoveryUrl, {
            status: 503,
            request: { headers: requestHeaders },
          }),
          contentSecurityPolicy,
        );
      }
      invalidSession = true;
    }
  }

  if (!publicPage && !authenticated) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set(
      "returnTo",
      request.nextUrl.pathname === "/account" &&
        request.nextUrl.searchParams.get("setup") === "1"
        ? safeReturnTo(request.nextUrl.searchParams.get("returnTo"))
        : safeReturnTo(`${request.nextUrl.pathname}${request.nextUrl.search}`),
    );
    return setSecurityHeaders(
      NextResponse.redirect(loginUrl),
      contentSecurityPolicy,
      invalidSession,
    );
  }
  if (request.nextUrl.pathname === "/login" && authenticated) {
    const returnTo = safeReturnTo(request.nextUrl.searchParams.get("returnTo"));
    const destination = new URL(
      hasPassword ? returnTo : "/account",
      request.url,
    );
    if (!hasPassword) {
      destination.searchParams.set("setup", "1");
      destination.searchParams.set("returnTo", returnTo);
    }
    return setSecurityHeaders(
      NextResponse.redirect(destination),
      contentSecurityPolicy,
    );
  }

  const response = NextResponse.next({
    request: {
      headers: requestHeaders,
    },
  });
  return setSecurityHeaders(response, contentSecurityPolicy, invalidSession);
}

export const config = {
  matcher: [
    {
      source:
        "/((?!api(?:/|$)|_next/static|_next/image|brand(?:/|$)|health(?:/|$)|favicon.ico|icon.png|apple-icon.png|manifest.webmanifest|robots.txt|sitemap.xml).*)",
    },
  ],
};
