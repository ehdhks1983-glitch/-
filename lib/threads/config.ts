// lib/threads/config.ts  [신규]
// 공식 Threads(Meta) API 연동 설정. 키·호스트·한도는 전부 여기서만 관리(하드코딩/매직넘버 금지).
// 모든 값은 env로 override 가능. 필수 키가 없으면 isThreadsConfigured()=false → 라우트/UI가 "미설정" 안내로 비활성.
// 참고(공식 문서 검증): 발행 권한은 threads_basic + threads_content_publish 면 충분. 24시간 발행 상한 250/계정.

export const THREADS = {
  appId: process.env.THREADS_APP_ID ?? "",
  appSecret: process.env.THREADS_APP_SECRET ?? "",
  /** OAuth 콜백 URL. Meta 앱 대시보드의 redirect URI 와 정확히 일치해야 함. */
  redirectUri: process.env.THREADS_REDIRECT_URI ?? "",
  /** 발행만이면 이 두 권한으로 충분. 더 필요한 기능(답글/인사이트) 추가 시 env로 확장. */
  scopes: process.env.THREADS_SCOPES ?? "threads_basic,threads_content_publish",
  /** 사용자 인가(OAuth 다이얼로그) 호스트. 토큰/그래프 호출 호스트와 분리됨. */
  authHost: process.env.THREADS_AUTH_HOST ?? "https://threads.net",
  /** 토큰 교환 + 그래프(me/threads/publish) 호스트. 토큰 엔드포인트는 버전 없는 루트 경로. */
  graphHost: process.env.THREADS_GRAPH_HOST ?? "https://graph.threads.net",
} as const;

/** 하루 발행 안전 한도(계정당). Meta 공식 상한은 250/24h지만, 스팸 방지를 위해 보수적 기본값. env로 조정. */
export const THREADS_DAILY_CAP = numEnv("THREADS_DAILY_CAP", 10);
/** Meta 공식 24시간 발행 상한(참고/방어용 상수). */
export const THREADS_META_DAILY_LIMIT = 250;
/** Threads 본문 최대 길이(공식 500자). */
export const THREADS_MAX_TEXT = numEnv("THREADS_MAX_TEXT", 500);
/** 한 번에 생성 가능한 AI 초안 개수 상한(과생성 방지). */
export const THREADS_MAX_DRAFTS = numEnv("THREADS_MAX_DRAFTS", 5);

/** OAuth state(CSRF 방지) 쿠키 이름/수명(초). */
export const THREADS_STATE_COOKIE = "threads_oauth_state";
export const THREADS_STATE_TTL_SEC = 600; // 10분

/** 장기 토큰 만료 N일 전부터 갱신 시도(공식 토큰 수명 약 60일). */
export const THREADS_REFRESH_BEFORE_DAYS = numEnv("THREADS_REFRESH_BEFORE_DAYS", 7);

/** 크론 1회 실행당 처리할 최대 게시물 수(과부하 방지). */
export const THREADS_CRON_BATCH = numEnv("THREADS_CRON_BATCH", 20);

/** appId/secret/redirectUri 가 모두 있으면 true. 없으면 연동 비활성(앱은 정상 동작). */
export function isThreadsConfigured(): boolean {
  return Boolean(THREADS.appId && THREADS.appSecret && THREADS.redirectUri);
}

/** OAuth 인가 URL 생성. state 는 CSRF 방지용 — 호출부에서 쿠키에 저장 후 콜백에서 대조한다. */
export function buildAuthorizeUrl(state: string): string {
  const p = new URLSearchParams({
    client_id: THREADS.appId,
    redirect_uri: THREADS.redirectUri,
    scope: THREADS.scopes,
    response_type: "code",
    state,
  });
  return `${THREADS.authHost}/oauth/authorize?${p.toString()}`;
}

function numEnv(name: string, fallback: number): number {
  const v = Number(process.env[name]);
  return Number.isFinite(v) && v > 0 ? v : fallback;
}
