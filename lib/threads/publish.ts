// lib/threads/publish.ts  [신규] — 단일 게시물 발행 핵심 로직(수동 발행 + 크론 공용).
// 2단계: createContainer → publishContainer. 토큰/식별자는 호출부가 넘긴다(저장은 db 가 담당).

import { createContainer, publishContainer } from "./client";
import type { ThreadsMediaType } from "./db";

export interface PublishInput {
  threadsUserId: string;
  accessToken: string;
  text: string;
  mediaType: ThreadsMediaType;
  imageUrl?: string | null;
}

/** 컨테이너 생성 → 발행. 성공 시 Threads 미디어 id 반환. 실패 시 throw. */
export async function publishOne(input: PublishInput): Promise<string> {
  const creationId = await createContainer(input.threadsUserId, input.accessToken, {
    mediaType: input.mediaType,
    text: input.text,
    imageUrl: input.imageUrl ?? undefined,
  });
  return publishContainer(input.threadsUserId, input.accessToken, creationId);
}
