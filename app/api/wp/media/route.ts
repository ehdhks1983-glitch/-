// app/api/wp/media/route.ts  [신규 — 워드프레스 자동 발행 v2]
// POST(multipart): 이미지 업로드 → 미디어 id. 글 등록 시 featuredMediaId(대표 이미지)로 사용.
// 이미지 타입·크기를 서버에서 제한하고, 파일명은 안전한 문자만 남긴다.

import { NextResponse } from "next/server";
import { uploadMedia } from "@/lib/wp/client";
import { readConnection, needConnection, badRequest, tooMany, wpErrorResponse } from "@/lib/wp/serverUtil";
import { sanitizeText } from "@/lib/sanitize";
import { rateLimit, clientKey, sweep } from "@/lib/rateLimit";

export const runtime = "nodejs";

const UPLOAD_LIMIT = 30; // 분당 업로드(IP 기준)
const UPLOAD_WINDOW_MS = 60_000;
const MAX_BYTES = 8 * 1024 * 1024;
const ALLOWED_TYPES: Record<string, string> = {
  "image/jpeg": "jpg",
  "image/png": "png",
  "image/webp": "webp",
  "image/gif": "gif",
};
const FIELD_LIMITS = { altText: 200, title: 120, filename: 80 };

function safeFilename(name: string, ext: string): string {
  const base = name.split(/[\\/]/).pop() ?? "image";
  const stem = base.replace(/\.[^.]+$/, "").replace(/[^a-zA-Z0-9._-]+/g, "-").replace(/^-+|-+$/g, "");
  const trimmed = (stem || "image").slice(0, FIELD_LIMITS.filename);
  return `${trimmed}.${ext}`;
}

export async function POST(req: Request) {
  sweep();
  if (!rateLimit(clientKey(req, "wp-upload"), UPLOAD_LIMIT, UPLOAD_WINDOW_MS).ok) return tooMany();
  const conn = readConnection(req);
  if (!conn) return needConnection();

  let fd: FormData;
  try {
    fd = await req.formData();
  } catch {
    return badRequest("이미지 업로드 형식이 올바르지 않습니다.");
  }

  const file = fd.get("file");
  if (!(file instanceof File)) return badRequest("이미지 파일을 선택해 주세요.");

  const ext = ALLOWED_TYPES[file.type];
  if (!ext) return badRequest("JPG, PNG, WEBP, GIF 이미지만 올릴 수 있어요.");
  if (file.size > MAX_BYTES) return badRequest("이미지는 8MB 이하만 올릴 수 있어요.");
  if (file.size === 0) return badRequest("빈 파일이에요.");

  const altRaw = fd.get("altText");
  const titleRaw = fd.get("title");
  const altText = sanitizeText(typeof altRaw === "string" ? altRaw : "", FIELD_LIMITS.altText);
  const title = sanitizeText(typeof titleRaw === "string" ? titleRaw : "", FIELD_LIMITS.title);

  try {
    const data = await file.arrayBuffer();
    const media = await uploadMedia(conn, {
      data,
      filename: safeFilename(file.name, ext),
      mimeType: file.type,
      ...(altText ? { altText } : {}),
      ...(title ? { title } : {}),
    });
    return NextResponse.json({ media });
  } catch (err) {
    return wpErrorResponse(err, "api/wp/media POST");
  }
}
