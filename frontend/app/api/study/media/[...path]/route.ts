import { createReadStream, statSync } from "node:fs";
import path from "node:path";
import { Readable } from "node:stream";

export const runtime = "nodejs";

const repoRoot = path.basename(process.cwd()) === "frontend" ? path.resolve(process.cwd(), "..") : process.cwd();
const studyMediaRoot = path.join(repoRoot, "study_media");
const resolvedStudyMediaRoot = path.resolve(studyMediaRoot);

function resolveMediaPath(parts: string[]) {
  const candidate = path.resolve(studyMediaRoot, ...parts);
  const rootWithSeparator = `${resolvedStudyMediaRoot}${path.sep}`;
  if (!candidate.startsWith(rootWithSeparator)) {
    return null;
  }
  return candidate;
}

function mediaHeaders(fileSize: number, extraHeaders: Record<string, string> = {}) {
  return {
    "content-type": "video/mp4",
    "accept-ranges": "bytes",
    "cache-control": "public, max-age=3600",
    "content-length": String(fileSize),
    ...extraHeaders,
  };
}

function streamResponse(filePath: string, start: number, end: number, status: 200 | 206, extraHeaders: Record<string, string> = {}) {
  const stream = createReadStream(filePath, { start, end });
  return new Response(Readable.toWeb(stream) as BodyInit, {
    status,
    headers: mediaHeaders(end - start + 1, extraHeaders),
  });
}

function filePathAndSize(parts: string[]) {
  const filePath = resolveMediaPath(parts ?? []);
  if (!filePath) {
    return { error: new Response("Forbidden", { status: 403 }) };
  }

  try {
    const stats = statSync(filePath);
    if (!stats.isFile()) {
      return { error: new Response("Not found", { status: 404 }) };
    }
    return { filePath, fileSize: stats.size };
  } catch {
    return { error: new Response("Not found", { status: 404 }) };
  }
}

function parseRange(range: string | null, fileSize: number): { start: number; end: number } | null {
  if (!range) return { start: 0, end: fileSize - 1 };

  const match = /^bytes=(\d*)-(\d*)$/.exec(range);
  if (!match) return null;

  const requestedStart = match[1];
  const requestedEnd = match[2];
  if (!requestedStart && !requestedEnd) return null;

  if (!requestedStart) {
    const suffixLength = Number(requestedEnd);
    if (!Number.isFinite(suffixLength) || suffixLength <= 0) return null;
    return { start: Math.max(0, fileSize - suffixLength), end: fileSize - 1 };
  }

  const start = Number(requestedStart);
  const end = requestedEnd ? Number(requestedEnd) : fileSize - 1;
  if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end >= fileSize || start > end) {
    return null;
  }
  return { start, end };
}

export async function HEAD(_request: Request, context: { params: Promise<{ path: string[] }> }) {
  const { path: requestedPath } = await context.params;
  const resolved = filePathAndSize(requestedPath ?? []);
  if (resolved.error) return resolved.error;
  return new Response(null, { status: 200, headers: mediaHeaders(resolved.fileSize) });
}

export async function GET(request: Request, context: { params: Promise<{ path: string[] }> }) {
  const { path: requestedPath } = await context.params;
  const resolved = filePathAndSize(requestedPath ?? []);
  if (resolved.error) return resolved.error;
  const { filePath, fileSize } = resolved;

  const range = request.headers.get("range");
  const parsedRange = parseRange(range, fileSize);
  if (!parsedRange) {
    return new Response("Invalid range", { status: 416, headers: { "content-range": `bytes */${fileSize}` } });
  }

  if (!range) {
    return streamResponse(filePath, 0, fileSize - 1, 200);
  }

  const { start, end } = parsedRange;
  return streamResponse(filePath, start, end, 206, {
    "content-range": `bytes ${start}-${end}/${fileSize}`,
  });
}
