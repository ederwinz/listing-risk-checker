import { NextRequest, NextResponse } from "next/server";

const LANGS = ["en", "zh"];
const DEFAULT_LANG = "en";

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (LANGS.some((l) => pathname === `/${l}` || pathname.startsWith(`/${l}/`))) return;
  request.nextUrl.pathname = `/${DEFAULT_LANG}${pathname}`;
  return NextResponse.redirect(request.nextUrl);
}

export const config = {
  matcher: ["/((?!api|_next|.*\\..*).*)"],
};
