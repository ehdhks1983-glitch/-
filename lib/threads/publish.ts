// lib/threads/publish.ts  [업데이트] — 단일 게시물 발행(수동 발행 + 크론 공용).
// TEXT : 컨테이너 생성 → 즉시 발행.
// IMAGE: 컨테이너 생성 → status 가 FINISHED 될 때까지 폴링(공식 권장) → 발행.
//        Meta가 이미지를 가져와 처리하는 데 수 초~수십 초 걸릴 수 있어, 폴링 후 발행해야 안정적이다.

import { createContainer, publishContainer, getContainerStatus } from "./client";
import { THREADS_MEDIA_POLL_ATTEMPTS, THREADS_MEDIA_POLL_INTERVAL_MS } from "./config";
import type { ThreadsMediaType } from "./db";

export interface PublishInput {
  threadsUserId: string;
  accessToken: string;
  text: string;
  mediaType: ThreadsMediaType;
  imageUrl?: string | null;
}

export interface PublishOptions {
  /** 테스트 주입용 sleep(기본은 실제 setTimeout). */
  sleep?: (ms: number) => Promise<void>;
}

/** 컨테이너 생성 → (이미지면 처리 대기) → 발행. 성공 시 Threads 미디어 id. 실패 시 throw. */
export async function publishOne(input: PublishInput, opts: PublishOptions = {}): Promise<string> {
  const sleep = opts.sleep ?? defaultSleep;

  const creationId = await createContainer(input.threadsUserId, input.accessToken, {
    mediaType: input.mediaType,
    text: input.text,
    imageUrl: input.imageUrl ?? undefined,
  });

  // 이미지는 처리 완료까지 대기. 텍스트는 즉시 발행 가능.
  if (input.mediaType !== "TEXT") {
    await waitUntilReady(creationId, input.accessToken, sleep);
  }

  return publishContainer(input.threadsUserId, input.accessToken, creationId);
}

/** 컨테이너 status 가 FINISHED 될 때까지 폴링. ERROR/EXPIRED/타임아웃은 throw. */
async function waitUntilReady(
  containerId: string,
  token: string,
  sleep: (ms: number) => Promise<void>,
): Promise<void> {
  for (let attempt = 0; attempt < THREADS_MEDIA_POLL_ATTEMPTS; attempt++) {
    const { status, error } = await getContainerStatus(containerId, token);
    if (status === "FINISHED") return;
    if (status === "ERROR") throw new Error(`미디어 처리 실패: ${error || "ERROR"}`);
    if (status === "EXPIRED") throw new Error("미디어 컨테이너가 만료됐습니다.");
    await sleep(THREADS_MEDIA_POLL_INTERVAL_MS);
  }
  throw new Error("미디어 처리 시간이 초과됐습니다. 잠시 후 다시 시도해 주세요.");
}

function defaultSleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}
