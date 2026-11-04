# 워드프레스 자동 발행 — 2026년 11월 기준 조사 메모

이 문서는 `/wordpress` 자동 발행 기능 v2를 만들기 전에 조사한 내용과, 그 결과를 코드에 어떻게
반영했는지 정리한 것이다. (조사일: 2026-11-04)

## 1. 워드프레스 7.0 "Armstrong" (2026-05-20 출시)

- 관리자 화면 전면 개편(2013년 이후 첫 리디자인), 커맨드 팔레트(Ctrl/⌘+K), 새 기본 색상.
- 코어에 **AI Client + Connectors**(AI 연동 허브) 탑재. 블록 에디터는 React 19로 이동.
- 블록별 반응형 표시/숨김, 블록별 커스텀 CSS, Breadcrumbs·Icon 등 새 블록, 리비전 비교.
- 실시간 공동 편집은 출처마다 설명이 엇갈림(포함 vs 테스트 중 제외) — 공식 릴리스 노트 확인 필요.
- **외부 자동화 관점**: 글 등록의 공식 경로는 여전히 REST API(`/wp-json/wp/v2/*`) + 응용 프로그램
  비밀번호(5.6+). https 필수(http에서는 응용 프로그램 비밀번호가 비활성 → 401).

→ 반영: 연결 안내 문구에 7.0 포함 명시, 입문 가이드에 "2026년 기준" 섹션 추가.

출처: [Yoast — WordPress 7.0 highlights](https://yoast.com/wordpress-7-0/),
[WPBeginner — What's new in 7.0](https://www.wpbeginner.com/news/whats-new-in-wordpress-7-0/),
[AlternativeTo — 7.0 launch](https://alternativeto.net/news/2026/5/wordpress-7-0-launches-with-a-new-admin-panel-editor-upgrades-and-an-ai-integrations-hub/),
[Raidboxes — 7.0 features](https://raidboxes.io/en/blog/wordpress/wordpress-7-0/)

## 2. REST로 보낼 때는 블록 마크업이어야 한다

- `content`에 HTML만 보내면 WP는 **클래식 콘텐츠**로 저장 → 편집 화면에서 블록 변환을 거쳐야 하고
  일부 요소가 표시되지 않는 사례가 보고됨.
- 블록 에디터 직렬화 형식(Gutenberg 공식 픽스처 `test/integration/fixtures/blocks/`)
  - 문단: `<!-- wp:paragraph -->\n<p>…</p>\n<!-- /wp:paragraph -->`
  - 제목: `<!-- wp:heading {"level":3} -->\n<h3 class="wp-block-heading">…</h3>\n<!-- /wp:heading -->`
  - 목록: `<!-- wp:list -->\n<ul class="wp-block-list"><!-- wp:list-item -->\n<li>…</li>\n<!-- /wp:list-item --></ul>\n<!-- /wp:list -->`
  - 인용: `<!-- wp:quote -->\n<blockquote class="wp-block-quote"><!-- wp:paragraph -->…<!-- /wp:paragraph --></blockquote>\n<!-- /wp:quote -->`
  - 구분선: `<!-- wp:separator -->\n<hr class="wp-block-separator has-alpha-channel-opacity"/>\n<!-- /wp:separator -->`

→ 반영: `lib/wp/blocks.ts` — 정화된 HTML을 위 형식으로 변환해 전송(`format: "blocks"` 기본,
`classic` 선택 가능).

출처: [WordPress.org 지원 포럼 — REST API와 블록 콘텐츠](https://remarpro.com/support/?p=17541796),
[Gutenberg 저장소 픽스처](https://github.com/WordPress/gutenberg/tree/trunk/test/integration/fixtures/blocks)

## 3. 구글 "대량 생산형 콘텐츠 남용(scaled content abuse)" 정책

- 2024년 3월 도입. **생산 방식(AI/사람)과 무관**하게 "순위 조작 목적으로 독자 가치 없이 대량 생산한
  페이지"를 스팸으로 분류.
- 2026년: 3월 코어 업데이트에서 우선 적용, 6월·8월·9월 스팸 업데이트에서 반복 단속(출처마다 날짜·세부가
  조금씩 다름 — 공식 Search Central 공지 확인 권장). 5월부터 AI Overviews / AI Mode 에도 동일 정책 적용.
- 핵심: AI 글 자체가 아니라 "얇고 반복적인 글을 쏟아내는 패턴"이 문제.

→ 반영:
- 대량 자동화 기본값 = **임시글로 저장 후 검토**(바로 예약 발행은 선택).
- **중복 주제 건너뛰기**(기존 글 제목과 키워드 유사도 검사, `lib/wp/quality.ts`).
- **발행 전 품질 체크리스트** 11항목(키워드 위치·소제목·분량·목록·FAQ·메타 설명·슬러그·대표 이미지·내부
  링크·태그).
- 프롬프트에 "구체 정보·독자 가치·FAQ·반복 금지" 원칙 명시, 글 유형별 구조 가이드.
- 선택: 글 끝 "AI 활용 안내 문구" 추가.

출처: [PPC Land — scaled content abuse](https://ppc.land/scaled-content-abuse/),
[Frase — Does Google penalize AI content](https://www.frase.io/blog/does-google-penalize-ai-content-no-but-it-punishes-this),
[GSQi — August 2026 spam update case studies](https://gsqi.com/marketing-blog/august-2026-google-spam-update-case-studies/),
[PPC Land — spam policies cover AI Overviews](https://ppc.land/google-spam-policies-now-officially-cover-ai-overviews-and-ai-mode-in-search),
[Bulkbase — staying compliant in 2026](https://bulkbase.ai/seo/scaled-content-abuse-googles-policy-enforcement-how-to-stay-compliant-in-2026)

## 4. 대표 이미지(featured image)

- `POST /wp-json/wp/v2/media` 에 multipart(`file`)로 올리고 응답의 `id`를 글 생성 시 `featured_media`
  로 전달. `alt_text`, `title` 함께 전송 가능.

→ 반영: `app/api/wp/media/route.ts`(8MB, JPG/PNG/WEBP/GIF 제한, 파일명 정화) +
`lib/wp/client.ts#uploadMedia`, 글쓰기 화면의 "대표 이미지" 업로드.

출처: [Medium — upload post/image via REST](https://medium.com/@vicgupta/how-to-upload-a-post-or-image-to-wordpress-using-rest-api-220fe046ff7a),
[Rapid Developers — automate publishing](https://www.rapidevelopers.com/api-automations/how-to-automate-wordpress-blog-publishing-using-the-api)

## 5. SEO 플러그인 메타(Yoast / Rank Math)

- WP REST는 `show_in_rest` 로 등록되지 않은 post meta 키를 **조용히 무시**한다(에러 없이 빈 값).
- Yoast: `_yoast_wpseo_title`, `_yoast_wpseo_metadesc`, `_yoast_wpseo_focuskw` — 기본 등록되어 REST 쓰기 가능.
- Rank Math: `rank_math_title`, `rank_math_description`, `rank_math_focus_keyword` — 별도 등록(브리지
  플러그인: Odiseo SEO Bridge, 42flows SEO Meta 등) 필요.
- All in One SEO: 자체 테이블/REST 사용 → post meta 방식으로는 반영 안 됨.

→ 반영: 연결 시 REST 인덱스 `namespaces`(`yoast/v1`, `rankmath/v1`, `aioseo/v1`)로 플러그인 감지,
글 생성 시 Yoast·Rank Math 키를 **동시에** `meta`로 전송(미등록 키는 무시되므로 안전), 연결 화면에
Rank Math 브리지 필요 안내.

출처: [Odiseo SEO Bridge](https://wordpress.org/plugins/?p=342789),
[42flows SEO Meta](https://www.mxp.tw/plugins/42flows-seo-meta/),
[Progressio v1.6.0 release note](https://github.com/ccdevelopment/progressio-performance-tracker/releases/tag/v1.6.0)

## 6. 그 밖에 반영한 것

- **내부 링크**: 생성 시 내 사이트의 발행 글(최대 30개)을 후보로 주고, 그 URL만 `<a href>` 로 허용
  (정화기가 다른 호스트·javascript: 링크는 태그를 벗김).
- **영문 슬러그**: 한글 URL은 공유 시 퍼센트 인코딩으로 깨져 보이므로 AI가 영문 슬러그 생성, 서버가
  `^[a-z0-9]+(-[a-z0-9]+)*$` 검증(실패 시 WP 자동 생성).
- **예약 지연 감지**: WP-Cron은 방문이 있어야 돌므로, 예약 시각이 지난 `future` 글을 현황에서 경고.
- **여러 사이트 저장**: 대행/다중 블로그 운영을 위해 브라우저에 여러 연결을 저장하고 전환.
- **사이트 타임존**: REST 인덱스의 `timezone_string`/`gmt_offset`을 연결 정보에 표시.

## 7. 하지 않은 것(의도적)

- 네이버 등 공식 API가 없는 플랫폼에 대한 브라우저 자동화/봇 — 약관 위반·계정 정지 위험이 있어 범위에서 제외.
- 타 사이트 글 수집·리라이팅, 댓글/백링크 자동화 — 스팸 정책 위반 소지.
- 이미지 AI 생성 — 비용·키 관리 부담으로 로드맵으로 미룸(업로드 방식만 제공).
