import { NextRequest, NextResponse } from "next/server";

function studyOnlyModeEnabled(): boolean {
  return process.env.VIEWTUBE_STUDY_ONLY === "1" || process.env.NEXT_PUBLIC_VIEWTUBE_STUDY_ONLY === "1";
}

function isStaticAsset(pathname: string): boolean {
  return (
    pathname.startsWith("/_next/") ||
    pathname === "/favicon.ico" ||
    pathname === "/robots.txt" ||
    pathname === "/sitemap.xml"
  );
}

function isAllowedStudyApi(pathname: string): boolean {
  return (
    pathname === "/api/events" ||
    pathname === "/api/impressions" ||
    pathname === "/api/session" ||
    pathname === "/api/session/survey" ||
    pathname.startsWith("/api/study/")
  );
}

function isAllowedStudyPage(pathname: string): boolean {
  return pathname === "/" || pathname.startsWith("/study/shorts-experiment");
}

export function proxy(request: NextRequest) {
  if (!studyOnlyModeEnabled()) return NextResponse.next();

  const { pathname, search } = request.nextUrl;
  const pathPidMatch = pathname.match(/^\/pid=([^/]+)$/);
  if (pathPidMatch) {
    const redirectUrl = request.nextUrl.clone();
    redirectUrl.pathname = "/";
    redirectUrl.search = "";
    redirectUrl.searchParams.set("pid", pathPidMatch[1]);
    return NextResponse.redirect(redirectUrl);
  }

  if (isStaticAsset(pathname) || isAllowedStudyPage(pathname) || isAllowedStudyApi(pathname)) {
    return NextResponse.next();
  }

  if (pathname.startsWith("/api/")) {
    return NextResponse.json(
      { error: "This endpoint is disabled in study-only production mode." },
      {
        status: 404,
        headers: {
          "cache-control": "no-store",
        },
      },
    );
  }

  const redirectUrl = request.nextUrl.clone();
  redirectUrl.pathname = "/";
  redirectUrl.search = search;
  return NextResponse.redirect(redirectUrl);
}

export const config = {
  matcher: ["/((?!.*\\..*).*)", "/api/:path*"],
};
