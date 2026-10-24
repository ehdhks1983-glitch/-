# 숏폼·스레드/인스타그램 게시·AI 영상 번역: 2025~2026년 10월 현황과 곰대리(컷대장·쇼츠/스레드 자동화·영상번역) 시사점

> 조사 기준일: 2026-10-24. 조사 방법상 한계: 이 환경에서는 WebFetch가 모든 호스트에서 DNS 실패(getaddrinfo ENOTFOUND)했고, curl은 프록시 정책(403)으로 막혔다. 그래서 아래 내용은 모두 WebSearch(extended) 결과의 요약과 스니펫에 기반하며, 원문 페이지를 직접 열어 대조하지 못했다. 공식 문서(YouTube Help, Meta for Developers, TikTok for Developers)도 검색 결과를 통해서만 확인했다. 수치가 중요한 항목은 원문으로 다시 확인해야 한다. 날짜 표기: [YYYY-MM] = 출처 또는 사건의 시점이다. 2025년 이전 정보는 "(2025년 이전)"으로 표시했다.

## 1. YouTube 2025~2026: 비진정성(inauthentic) 콘텐츠 수익화 정책, AI 표시, 자동 더빙, 유사성(likeness) 감지, Data API 업로드 규칙

### Takeaway
YouTube는 AI 자체를 금지하지 않는다. 다만 2025-07-15부터 '반복적(repetitious) 콘텐츠'를 '비진정성(inauthentic) 콘텐츠'로 이름을 바꿨고, 2026-07에는 이를 ①일반적·반복적·템플릿 기반 콘텐츠 ②불쾌·충격성 콘텐츠 ③AI 페르소나가 건강·금융 같은 민감 주제를 다루는 콘텐츠의 3개 범주로 명확히 했다. 집행은 채널 단위다. 그래서 '블로그 글 → TTS + 이미지 슬라이드 쇼츠'처럼 같은 틀로 대량 생산하는 방식은 수익화 위험이 가장 큰 패턴이다. 2026-05-27부터는 사실적인 AI를 크리에이터가 표시하지 않아도 YouTube가 자동으로 라벨을 붙인다. Data API 업로드 쿼터는 2026-06에 별도 버킷(일 100회)으로 분리된 것으로 보도되지만, 공식 문서끼리도 내용이 엇갈린다.

### Cited Findings
**비진정성 콘텐츠 정책: 2025-07 개명**
- [2025-07] YouTube 크리에이터 리에종 Rene Ritchie는 YPP 정책의 핵심 변경이 "repetitious" 콘텐츠를 "inauthentic" 콘텐츠로 개명한 것이라고 설명했다. 목적은 대량 생산형·반복형 영상을 명확히 포함하는 것이다. YouTube는 이를 YPP 정책의 "minor update"라고 불렀다 — [Search Engine Journal](https://www.searchenginejournal.com/youtube-targets-mass-produced-content-in-monetization-update/550337/); [Social Media Today](https://www.socialmediatoday.com/news/youtube-clarifies-monetization-update-inauthentic-repeated-content/752892/)
- [2025-07] 시행일은 2025-07-15다. 최소한의 노력, 과도한 템플릿화, 대량 재사용으로 만든 영상이 대상이다. 다만 YouTube는 대상 콘텐츠의 완전한 목록은 공개하지 않았다 — [Gulf News](https://gulfnews.com/technology/youtube-updates-monetisation-policies-ai-and-repetitive-content-ban-begins-july-15-1.500192660); [ContentGrip](https://www.contentgrip.com/youtube-tightens-monetisation/)
- [2025-07] 재사용 콘텐츠도 상당한 독창적 해설, 수정, 교육·오락적 가치를 더하면 수익화를 유지할 수 있다. "규칙은 새롭지 않지만 집행이 새롭다"는 평가가 있다 — [Social Media Today](https://www.socialmediatoday.com/news/youtube-clarifies-monetization-update-inauthentic-repeated-content/752892/); [Live Breathe SEO (Substack)](https://livebreatheseo.substack.com/p/youtubes-july-2025-policy-update)
- [2025-07] 국내 보도는 'TTS·AI 음성 영상, 개별 내러티브 없이 이미지만 나열한 영상, 최소 편집 재사용, 재사용 스크립트 기반 영상'을 대상으로 꼽았다. 반복·대량 생산 위주 채널은 YPP에서 퇴출될 수 있다고 했다(2차 보도) — [한국경제 2025-07-10](https://www.hankyung.com/article/2025071091627); [뉴스스페이스](https://www.newsspace.kr/news/article.html?no=7932)
- [2026-01] 국내 언론은 "AI로 찍어낸 쇼츠 '수익 정지' 철퇴"라는 제목으로 유사 AI 쇼츠 수익 정지 사례를 보도했다 — [다음뉴스 2026-01-19](https://v.daum.net/v/20260119173612764)

**비진정성 콘텐츠 정책: 2026-07 명확화**
- [2026-07-20] TechCrunch는 YouTube가 'AI slop'과 불쾌한 영상 관련 정책을 명확히 했다고 보도했다. 이번 업데이트는 새 금지가 아니라 기존 정책에 뉘앙스를 더한 것이다. 비진정성 콘텐츠는 ①generic·repetitive·template-based 콘텐츠 ②off-putting·distressing 콘텐츠 ③AI 페르소나가 건강·금융 등 민감 주제를 다루는 콘텐츠의 3개 범주로 나뉜다 — [TechCrunch 2026-07-20](https://techcrunch.com/2026/07/20/youtube-clarifies-policies-around-ai-slop-and-upsetting-videos/); [OutlierKit (2차, 시행일을 2026-07-16로 표기)](https://outlierkit.com/blog/youtube-updates-july-2026); [Influencer Marketing Hub](https://influencermarketinghub.com/youtube-inauthentic-content/)
- [2026] 2차 자료들은 AI 보조 콘텐츠도 "significant original and authentic value"가 있으면 수익화 대상이라고 설명한다. 또 정책이 채널 단위로 작동해서, 채널이 YPP에서 제외되면 문제없는 영상까지 모든 영상의 광고 수익이 끊긴다고 설명한다(2차 블로그라 신뢰도는 중간) — [Miraflow](https://miraflow.ai/blog/youtube-monetization-ai-content-2026-allowed-demonetized); [arwriterai](https://arwriterai.com/en/blog/youtube-inauthentic-content-policy-ai-creators-2026/); [TubeBuddy](https://www.tubebuddy.com/blog/youtube-ai-monetization-best-practices/)
- 상충: 국내 검색에서는 "2026년 7월의 새 변경은 찾지 못했다"는 요약도 나왔다. 반면 TechCrunch(2026-07-20)는 명확화가 있었다고 보도했다. 이 노트는 TechCrunch를 우선하되, 원문을 직접 열어 보지는 못했다 — [viralpulse (국내 2차)](https://viralpulse.net/blog/ai-shorts-youtube-policy)

**AI(변형·합성) 콘텐츠 표시**
- [2026-05-27] YouTube는 크리에이터가 표시하지 않은 '상당한(significant)' 사실적 AI 사용을 시스템이 감지하면 직접 라벨을 붙이기로 했다. AI 라벨도 더 눈에 띄게 바뀌었다. 새 라벨은 "모든 사실적(photorealistic)이거나 의미 있게 AI로 변형·생성된 콘텐츠에 대한 단일 라벨 형식"이다. 단순히 양식화했거나 가볍게 변형한 콘텐츠는 설명란 표시만 유지된다 — [Variety](https://variety.com/2026/digital/news/youtube-ai-video-labels-automatic-detection-1236758865/); [Music Business Worldwide](https://www.musicbusinessworldwide.com/youtube-will-now-automatically-detect-and-label-ai-videos-even-when-creators-dont-disclose-it/)
- [2026-05] YouTube는 표시 라벨 자체가 추천이나 수익화 자격을 바꾸지 않는다고 밝혔다. 즉 표시는 '수익화 면책'이 아니다. 자동 라벨에 크리에이터가 이의를 제기할 수 있는지는 출처마다 다르다 — [Variety](https://variety.com/2026/digital/news/youtube-ai-video-labels-automatic-detection-1236758865/); [Kompozy](https://kompozy.io/news/youtube-ai-disclosure-likeness-rules-2026)

**유사성(likeness) 감지**
- [2025-09-16] YouTube는 Studio 업데이트에서 likeness detection을 YPP 크리에이터 전체 대상 오픈 베타로 예고했다. 크리에이터는 자기 얼굴을 무단 사용한 영상을 감지·관리하고 삭제를 요청할 수 있다. 립싱크 더빙도 같은 발표에 포함됐다 — [TechCrunch 2025-09-16](https://techcrunch.com/2025/09/16/youtube-rolls-out-studio-updates-likeness-detection-lip-synced-dubs-creator-collabs-and-more)
- [2026-05] 자동 AI 라벨 발표와 함께, likeness detection이 만 18세 이상 모든 적격 크리에이터로 확대된 것으로 보도됐다 — [Variety](https://variety.com/2026/digital/news/youtube-ai-video-labels-automatic-detection-1236758865/)
- [2026-08-17] 비평 기사는 likeness detection이 '자동 보호'가 아니라 '검토 큐'라고 지적했다. 일치 항목이 실제 영상인지, 합성인지, 승인된 사용인지는 크리에이터가 직접 판단해야 한다 — [LaunchVibes](https://www.launchvibes.tech/articles/2026-08-17-youtube-likeness-detection-review-queue)

**자동 더빙과 다국어 오디오**
- [2025] YouTube는 자동 더빙을 전체 크리에이터로 확대하고 립싱크 기능을 시험한다고 발표했다 — [Social Media Today](https://www.socialmediatoday.com/news/youtube-expands-auto-dubbing-to-all-creators/811375/); [Social Samosa](https://www.socialsamosa.com/news-2/youtube-expands-auto-dubbing-tests-lip-sync-11077978)
- [2026-02] 자동 더빙이 크리에이터 대상으로 정식 제공(GA)되고 27개 언어로 확대됐다. 'Expressive Speech'는 영·불·독·힌디·인니·이탈리아·포르투갈·스페인어 8개 언어로 전 채널에 적용됐다. 시청자용 'Preferred Language' 설정(더빙/원본 선택)도 추가됐다. 2025-12 기준 자동 더빙 콘텐츠를 하루 10분 이상 시청한 사람은 일평균 600만 명을 넘었다 — [PPC Land](https://ppc.land/youtube-auto-dubbing-tops-6m-daily-viewers-expands-to-27-languages/); [Digit](https://www.digit.in/news/audio-video/youtube-auto-dubbing-now-supports-27-languages-lip-sync-and-viewer-controls.html); [YouTube Blog](https://blog.youtube/news-and-events/youtube-auto-dubbing-expressive-speech/)
- [2026-05~07] 립싱크 더빙은 아직 파일럿이다. 일부 채널과 적격 영상·언어에만 제공된다. 경쟁사 sync.so는 2026-07 시점에 크리에이터에게 출시되지 않았다고 주장했다(경쟁사 주장이라 주의가 필요하다). 자동 더빙은 여전히 합성 음성이다 — [Android Authority](https://www.androidauthority.com/youtube-auto-dub-translations-3637915/); [sync.so](https://sync.so/blog/youtube-auto-dubbing)
- 27개 언어에 한국어, 일본어, 중국어가 포함되는지는 검색 요약에서 확인하지 못했다(Gaps 참조).

**YouTube Data API 업로드 규칙(서드파티 업로더)**
- [2026-06] 2026-06 변경으로 videos.insert와 search.list가 각자 별도 버킷(각각 일 100회, 호출당 1유닛)으로 분리됐다고 한다. 다른 메서드는 기존 10,000유닛 버킷에 남았다. 그 전에는 업로드 1건이 1,600유닛이었다. 다만 2025-08 갱신된 'Quota calculator' 페이지는 여전히 1,600유닛을 표시한다는 지적이 있다 — [TimeToPost](https://timetopost.co/blog/how-to-upload-videos-youtube-api/); [PostZen](https://www.postzen.dev/blog/youtube-data-api-upload); [Outstand](https://www.outstand.so/blog/youtube-api-pricing-quota); [Google for Developers: videos.insert](https://developers.google.com/youtube/v3/docs/videos/insert)
- (2020년부터 이어진 규정, 2025년 이전) 2020-07-28 이후 생성된 '미검증(unverified)' API 프로젝트가 videos.insert로 올린 영상은 비공개(private)로 제한된다. 이를 풀려면 API 프로젝트가 ToS 준수 감사(audit)를 받아야 한다. 상충: 2026-10-08 기준 공식 레퍼런스에는 '미검증 프로젝트 업로드가 비공개로 제한되지 않는다'는 문구가 있다는 보고가 있다. 반면 개정 이력에는 제한 문구가 남아 있다 — [PostZen (quota)](https://www.postzen.dev/blog/youtube-api-quota-exceeded); [Google for Developers](https://developers.google.com/youtube/v3/docs/videos/insert)

### Inferences
- 컷대장의 핵심 플로우인 "블로그 글 → 3분 만에 영상"은 기본값이 '같은 템플릿 + AI 음성 + 스톡/생성 이미지 나열'이다. 이는 YouTube가 2025-07 이후 계속 지목한 '템플릿 기반·대량 생산' 패턴과 겹친다. 한 사업자가 매일 같은 틀로 올리면 채널 단위 YPP 위험이 생긴다. 다만 소상공인 채널은 대부분 애드센스 수익이 아니라 '매장 홍보'가 목적이다. 그래서 수익화 박탈 자체의 피해는 상대적으로 작고, 실제 리스크는 추천 노출 저하와 브랜드 신뢰 문제일 가능성이 높다. 이것은 추론이며 노출 저하를 직접 입증하는 자료는 확보하지 못했다.
- 한량연구소 채널이 'AI 쇼츠 수익화 공식 정책' 영상을 만든 것은 이 불안이 고객층에 실재한다는 신호다. 제품 차원의 '정책 준수 장치'가 판매 포인트가 될 수 있다.
- 업로드 쿼터가 '프로젝트당 일 100건'이라면 SaaS 하나(단일 GCP 프로젝트)로 수천 명의 사장님 채널에 매일 자동 업로드하는 구조는 금방 막힌다. 쿼터 증설 신청과 감사 통과는 필수 선결 과제다.

### Gaps
- YouTube 공식 YPP 정책 페이지와 Help Center 원문을 직접 열지 못해 3개 범주의 정확한 문구와 쇼츠 전용 예시를 확인하지 못했다.
- 자동 더빙 27개 언어 목록에 한국어(원본 또는 대상)가 들어가는지, 쇼츠에도 적용되는지 확인하지 못했다.
- 크리에이터가 직접 만든 더빙 트랙을 올리는 다국어 오디오(Multi-language audio) 기능이 2025~2026년에 전체 크리에이터로 확대됐는지는 출처를 확보하지 못했다.
- Data API의 2026-06 쿼터 분리는 서드파티 블로그 보도에 기반한다. 공식 개정 이력 원문은 확인하지 못했다.

## 2. Instagram/Meta: AI 라벨, 오리지널 콘텐츠 랭킹, 트라이얼 릴스, Edits 앱, Graph API 게시 범위

### Takeaway
Instagram은 2024년 릴스에 적용한 '오리지널 우대'를 2026-04에 사진과 캐러셀로 넓혔다. 애그리게이터(재게시) 계정은 추천 면에서 빠진다(최근 30일 기준). Graph API로는 릴스, 캐러셀, 스토리, 트라이얼 릴스(trial_params)까지 게시할 수 있다. 다만 네이티브 '예약 게시' 파라미터는 없어서 자체 큐가 필요하다. 한도는 대체로 롤링 24시간 100건이고, 공식 문서 안에서도 50건 표기가 섞여 있다. Edits 앱은 2026년에 이중언어 자막(15개 언어), AI Restyle, 데스크톱 버전, AI 어시스턴트를 추가하며 무료 경쟁 도구로 떠올랐다.

### Cited Findings
**오리지널 콘텐츠 랭킹**
- (2025년 이전, 2024-04) Instagram은 작은 오리지널 크리에이터를 더 노출하도록 랭킹을 바꿨다. 같은 콘텐츠가 여럿이면 원본을 추천하는 방식이 릴스에 먼저 도입됐다 — [TechCrunch 2024-04-30](https://techcrunch.com/2024/04/30/instagram-is-updating-its-ranking-systems-to-surface-more-content-from-smaller-original-creators)
- [2026-04-30] Instagram은 애그리게이터 계정의 사진·캐러셀을 탐색 탭 등 추천 면에서 더 이상 추천하지 않는 시스템을 도입했다. 판정을 되돌리려면 최근 30일 동안 게시물·캐러셀·릴스 '대부분'이 오리지널이어야 한다. 워터마크 추가, 속도 변경 같은 저노력 편집은 오리지널로 인정되지 않는다. 출처를 밝힌 스크린샷도 마찬가지다. 실질적 편집은 오리지널로 본다. 기존 팔로워에게는 계속 보이지만 비팔로워 도달(성장)은 사실상 꺼진다. 계정은 비오리지널 콘텐츠를 지우고 이의를 제기할 수 있다 — [TechCrunch 2026-04-30](https://techcrunch.com/2026/04/30/instagram-restricts-reach-of-content-aggregators-in-new-crackdown/); [Yahoo Tech](https://tech.yahoo.com/social-media/articles/instagram-stop-recommending-accounts-dont-151646266.html); [Social Media Today](https://www.socialmediatoday.com/news/instagram-updates-algorithm-to-benefit-original-creators/819016/)

**Graph API 게시**
- [2026-10] 게시 한도는 롤링 24시간 100건(캐러셀은 1건으로 계산)이라는 보고가 많다. 릴스, 피드, 스토리가 같은 버킷을 쓴다. 다만 Meta 문서 안에서도 100건(게시 가이드)과 50건(캐러셀 섹션, content_publishing_limit 레퍼런스)이 엇갈린다. 2026-10 실측에서는 엔드포인트가 100을 반환했다는 보고가 있다. 잔여량은 GET /{ig_user_id}/content_publishing_limit로 확인한다. 한도 초과 시 에러 9 / subcode 2207042가 난다 — [Reel Uploader](https://reeluploader.com/blog/instagram-api-publishing-limits); [Bundle.social](https://bundle.social/blog/instagram-graph-api); [Meta for Developers: Content Publishing](https://developers.facebook.com/docs/instagram-platform/content-publishing/)
- [2026] Instagram API에는 네이티브 예약 게시 기능이 없다. 24시간 안에 게시하지 않은 컨테이너는 만료되므로 개발사가 직접 큐를 운영한다. Facebook 릴스는 scheduled_publish_time(10분~29일)을 지원한다. 릴스는 비동기 처리라서 컨테이너 상태를 폴링한 뒤 게시한다. API로 게시한 릴스가 최대 90초로 제한된다는 주장은 교차 확인되지 않았다 — [PostProxy](https://postproxy.dev/blog/instagram-reels-api-publishing-guide/); [KeyAPI](https://www.keyapi.ai/blog/instagram-api-rate-limits-2026-what-changed-and-how-to-adapt/); [Zernio](https://zernio.com/blog/instagram-graph-api)
- [2026] 기타 한도(서드파티 보고): 계정당 컨테이너 생성은 롤링 24시간 400건, 사용자 토큰당 시간당 200회 호출이다 — [KeyAPI](https://www.keyapi.ai/blog/instagram-api-rate-limits-2026-what-changed-and-how-to-adapt/)

**트라이얼 릴스**
- [2026] 트라이얼 릴스는 비팔로워에게만 노출되는 릴스다. API에서는 릴스 컨테이너를 만들 때 trial_params를 넣어 게시한다. 졸업(graduation) 전략은 MANUAL(앱에서 수동)과 SS_PERFORMANCE(성과가 좋으면 자동 졸업) 두 가지다 — [Sume 가이드](https://www.sume.com/guides/instagram-trial-reels-api-graduation-strategy); [Meta for Developers: Content Publishing](https://developers.facebook.com/docs/instagram-platform/content-publishing/)
- [2026-04] Mosseri는 트라이얼 릴스 예약 기능을 발표한 것으로 전해진다. 2026-09-30 기준 자격 요건(2차 요약)은 공개 계정, 개인 계정이면 팔로워 1,000명 이상, 추천 적격 상태다. API 트라이얼 릴스 일일 한도(약 20건)는 확인되지 않았다 — [PostFast](https://postfa.st/blog/instagram-trial-reels); [Exemplary](https://exemplary.ai/blog/instagram-trial-reels)
- [2026-08] 2026-08의 'First Draft' 편집 기능은 API로 쓸 수 없다. API는 완성된 영상만 게시한다 — [InvisibleAPI 2026-10 정리](https://invisibleapi.ai/blog/instagram-new-features/)

**Edits 앱(2026)**
- [2026-06-11] Meta는 무료 편집 앱 Edits의 데스크톱 버전을 발표한 것으로 보도됐다 — [EmbedSocial](https://embedsocial.com/blog/new-instagram-features-2026/)
- [2026-08-19] Edits 업데이트에는 애니메이션 효과 15종, AI Restyle(프롬프트로 영상 룩 변환), 15개 언어 이중언어(bilingual) 자막, 커스텀 오디오 가져오기, 릴스 3개 비교 분석, 15분 내보내기가 포함됐다(2차 블로그) — [arwriterai](https://arwriterai.com/en/blog/instagram-edits-app-update-2026/)
- [2026-09-30/10-01] 'Edits Assistant'가 미국에서 출시됐다. 오디언스 정보, 성과 지표, 트렌드를 분석해 계정별 인사이트와 아이디어를 주는 AI 챗봇이다 — [PetaPixel 2026-10-01](https://petapixel.com/2026/10/01/instagram-launches-ai-assistant-that-analyzes-your-reels-and-suggests-new-ideas/)
- [2025] Edits에 IG 링크, 주간 아이디어, 새 영상 효과가 추가됐다 — [Social Media Today](https://www.socialmediatoday.com/news/edits-gets-ig-links-weekly-ideas-and-new-video-effects-features/809644/)

### Inferences
- 곰대리가 같은 템플릿 영상을 여러 고객 계정에 거의 그대로 뿌리거나, 블로그·카페에 쓴 이미지를 그대로 캐러셀로 재게시하면 애그리게이터·비오리지널 판정을 받을 수 있다. 2026-04부터 사진·캐러셀까지 확대됐으므로 '사장님 직접 촬영 소스'를 투입하는 것이 노출의 전제 조건이 된다.
- Edits가 무료로 이중언어 자막과 AI Restyle을 제공하므로, 컷대장의 '자막 + 효과' 수준 기능만으로는 유료 가치를 증명하기 어렵다. 컷대장의 차별점은 '게시까지 이어지는 자동화'와 '업종별 기획'이어야 한다.
- 트라이얼 릴스를 API로 쓸 수 있으니 "같은 매장 소재 2~3개 버전을 비팔로워에게 먼저 테스트하고 이긴 버전만 팔로워에게 졸업"시키는 A/B 자동화를 바로 만들 수 있다.

### Gaps
- Meta의 'AI info' 라벨(2024-07에 'Made with AI'에서 이름이 바뀐 것으로 알려짐, 2025년 이전, 출처 미확보)이 2025~2026년에 어떻게 바뀌었는지, API로 게시한 콘텐츠에 AI 라벨을 지정하는 파라미터가 있는지 확인하지 못했다. 한 검색 요약은 2026-08-31자 'AI-generated profile' 라벨과 도달 제한을 언급했지만 출처를 특정하지 못해 인용하지 않았다.
- Instagram Graph API의 콘텐츠 게시 한도는 공식 문서 안에서도 50건과 100건이 엇갈린다. 원문을 대조하지 못했다.
- 한국 내 Edits 어시스턴트 제공 여부는 확인하지 못했다.

## 3. Threads: API 기능(2026), 레이트 리밋, 한국 이용 현황, 알고리즘, 광고

### Takeaway
2026년 Threads API는 텍스트·이미지·영상·캐러셀 게시, 투표, 토픽 태그, 위치 태그, 링크 첨부, GIF, 텍스트 첨부, 스포일러, 고스트 포스트(24시간 자동 보관), 인스타 스토리 교차 공유, 답글 승인·숨김 관리, 키워드·태그 검색(미디어 타입 필터), 인사이트, 웹훅까지 지원한다. 사실상 앱과 거의 같은 수준이다. 네이티브 예약 파라미터는 없다. 한도는 프로필당 24시간 250게시·1,000답글이다(서드파티 정리 기준). 한국 MAU는 2025년 말 약 692만 명으로 X를 바짝 추격했고, 광고는 2026-01 전 세계 사용자 대상으로 확대됐다. 한국에 한정한 광고 정보는 확보하지 못했다.

### Cited Findings
**API 기능 타임라인**
- [2025-07] Threads API에 위치 태그, 투표(텍스트 게시물만, 링크 첨부와 병행 불가), 토픽 태그와 태그 검색, 기간 지정 키워드 검색, 클릭 지표, 실시간 알림이 추가됐다. 키워드 검색이 롤링 7일 500쿼리로 제한된다는 보도는 공식 문서로 확인하지 못했다 — [PPC Land](https://ppc.land/meta-expands-threads-api-with-advanced-features-for-developers/); [SwipeInsight](https://web.swipeinsight.app/posts/threads-api-receives-new-enhancements-for-developers-18375); [Social Media Today](https://www.socialmediatoday.com/news/threads-expands-api-functionality-social-media-management/754239/)
- [2025-09-09] 공식 Threads API 변경 로그: 키워드 검색에서 미디어 타입별 공개 게시물 검색을 지원하기 시작했다 — [Threads API Changelog (@threadsapi.changelog)](https://www.threads.com/@threadsapi.changelog/post/DOav3ZngUHX/threads-api-updateseptember-9-2025-support-for-searching-for-public-posts-by-med)
- [2026-03-19] 공식 변경 로그: Post Intents로 답글과 인용 게시물을 만드는 새 파라미터가 추가됐다(검색 요약 기준) — [Threads API Changelog](https://www.threads.com/@threadsapi.changelog)
- [2026-03-25] Meta 개발자 블로그(Marketing API): Threads 광고의 답글을 조회·숨김·응답할 수 있게 됐다 — [Meta for Developers Blog 2026-03-25](https://developers.facebook.com/blog/post/2026/03/25/marketing-api-latest-updates-for-ads-on-threads/); [Social Media Today](https://www.socialmediatoday.com/news/meta-updates-its-threads-marketing-api/815757/)
- [2026-04 중순] 서드파티 앱으로 고스트 포스트(24시간 뒤 자동 보관되는 텍스트 전용)를 게시하고 인스타 스토리에 공유할 수 있게 됐다. 예약 게시에 텍스트 첨부, GIF, 스포일러 태그(텍스트·이미지·영상)를 넣을 수 있다. 공개 게시물은 액세스 토큰 없이 임베드할 수 있다. 프로필 탐색(analytics) 팔로워 기준은 1,000명에서 100명으로 낮아졌다. 게시·삭제 실시간 알림과 답글 승인·대기 답글 관리 도구도 추가됐다. 일부 매체는 이 업데이트를 2026-03으로 표기한다 — [Social Media Today](https://www.socialmediatoday.com/news/meta-updates-threads-api-with-more-third-party-app-integrations/817502/); [Shopifreaks](https://www.shopifreaks.com/meta-updates-the-threads-api-with-scheduling-upgrades-gif-support-post-embedding-and-lower-follower-thresholds-for-analytics/); [ALM Corp](https://almcorp.com/blog/meta-threads-api-update-third-party-app-integration/)
- [2026-04-21] 공식 변경 로그: 광고 생성에 Page 기반 Threads 계정을 쓸 수 있게 됐고, 기존 Facebook·Instagram 게시물을 Threads 광고로 홍보할 수 있게 됐다 — [Threads API Changelog](https://www.threads.com/@threadsapi.changelog)

**레이트 리밋과 게시 방식(서드파티 정리, Meta 원문 미확인)**
- [2026] 프로필당 롤링 24시간 기준 API 게시 250건, 답글 1,000건, 삭제 100건, 위치 검색 500건이다. 캐러셀(2~20개 항목)은 1건으로 계산한다. 텍스트는 500자다. 게시는 컨테이너 생성 후 게시하는 2단계이며, 약 30초 대기가 권장된다. 컨테이너는 24시간 뒤 만료된다. 앱에서 직접 올린 게시물도 한도에 포함되므로 publishing-limit 엔드포인트로 잔여량을 확인해야 한다. 별도로 '24시간 호출 수 = 4,800 × 노출수(최소 10)' 형태의 호출 예산이 있다. API에 내장 스케줄러는 없다 — [Blotato](https://www.blotato.com/blog/threads-api-pricing); [Outstand](https://www.outstand.so/blog/threads-api); [PostProxy](https://postproxy.dev/blog/how-to-post-to-threads-via-api/); [UltraLab 튜토리얼](https://ultralab.tw/en/blog/threads-api-auto-post-tutorial-2026)

**한국 이용 현황**
- [2025-12 기준, 2026 보도] 와이즈앱·리테일 기준 국내 Threads MAU는 692만 명이다(X는 757만 명). 다른 조사기관 수치는 다를 수 있다 — [서울경제](https://www.sedaily.com/article/14036762)
- [2026-06] Meta는 Threads 글로벌 MAU가 5억 명을 넘었다고 밝혔다. 국내 앱 이용 시간은 전년 동기 대비 80% 이상 늘었고, 같은 시기 커뮤니티 기능이 국내에 도입됐다. 국가별 매출과 이용자 데이터는 공개되지 않았다. 광고 시스템이 인스타그램만큼 고도화되지 않았다는 지적도 있다 — [아이티데일리](http://www.itdaily.kr/news/articleView.html?idxno=239897); [네이트뉴스(2026-06-16)](https://m.news.nate.com/view/20260616n34816); [코리아리포트](https://www.koreareport.co.kr/news/articleView.html?idxno=52717)
- [2025] Threads 모바일 사용자 수가 X를 추월했다는 보도가 있다(측정 기관에 따라 다름) — [AI포스트](https://www.aipostkorea.com/news/articleView.html?idxno=10516); [Raylogue](https://www.raylogue.com/threads-2025-korea-market-analysis/)

**알고리즘(확인된 것과 미확인 구분)**
- (2025년 이전, 2024-11) Mosseri는 팔로우 계정 비중을 늘리고 무관한 추천을 줄이도록 랭킹을 재조정했다고 밝혔다. Meta Transparency Center는 후보 게시물을 사용자 행동 신호로 점수화하는 AI 랭킹이라고 설명한다 — [BulkPublish](https://www.bulkpublish.com/blog/threads-algorithm/); [Threads Dashboard](https://www.threadsdashboard.com/blog/threads-algorithm-how-it-works)
- [2025~2026] Mosseri는 여러 차례 '답글을 다는 것이 게시만큼 성장에 중요하다'고 말했다(공식 문서가 아닌 SNS 발언). Meta는 저노력 '참여 유도(engagement bait)' 답글의 순위를 낮추는 중이라고 인정했다. 링크 게시물 가중치를 높였다는 주장과 링크 페널티 주장은 서로 상충하고 미확인이다. "첫 30~60분이 도달을 결정한다"는 주장도 미확인이다 — [BulkPublish](https://www.bulkpublish.com/blog/threads-algorithm/); [Postory](https://postory.io/blog/threads-algorithm)

**광고**
- [2026-01-21] Meta는 Threads 광고를 전 세계 모든 사용자에게 확대한다고 발표했다(2026-01-26 주부터). 앞서 2025-04-23에 전 세계 적격 광고주에게 개방했고, 미국·일본에서 테스트를 시작했었다. 형식은 이미지, 영상, 캐러셀, Advantage+ 카탈로그, 앱 광고다. Ads Manager의 'Threads Feed' 지면(모바일 전용, 4:5)으로 구매한다. 영상(2025-08)과 캐러셀(2025-10) 개시 시점은 출처마다 다르다 — [TechCrunch 2026-01-21](https://techcrunch.com/2026/01/21/threads-rolls-out-ads-to-all-users-worldwide); [Social Media Today](https://www.socialmediatoday.com/news/meta-announces-global-expansion-of-threads-ads/810151/); [PPC Land](https://ppc.land/meta-finally-brings-threads-ads-to-every-user-after-yearlong-testing-phase/); [AdMake (2026-07 검증)](https://admakeai.com/blog/threads-ads)
- [2026-06] Meta CFO는 Threads가 2026년 매출 성장의 의미 있는 동력은 아닐 것이라고 말한 것으로 전해졌다. 반면 Evercore ISI는 Threads의 2026년 매출을 113억 달러로 추정했다 — [네이트뉴스](https://m.news.nate.com/view/20260616n34816)

### Inferences
- 동네 가게에 특히 가치 있는 API 기능은 ①위치 태그(매장 위치) ②투표("이번 주 신메뉴 A vs B") ③토픽 태그(지역·업종) ④고스트 포스트("오늘만 선착순" 같은 휘발성 공지) ⑤키워드·태그 검색으로 "성수 카페 추천"류 글을 찾아 답글 기회 발굴 ⑥답글 승인·숨김(악성 댓글 관리) ⑦인스타 스토리 교차 공유다. 현재 곰대리 '스레드 자동화'가 게시만 한다면 이 기능들이 확장 여지다.
- Mosseri 발언대로 답글이 성장의 핵심이고 Meta가 engagement-bait 답글을 하향 조정한다면, '자동 대량 답글'은 역효과를 낸다. 'AI 답글 초안 + 사장님 원탭 승인' 구조가 정책 위험과 효과의 균형점이다.
- 한도(250게시/1,000답글)는 소상공인 1계정에는 넉넉하다. 그래서 제약은 기술보다 품질과 스팸 판정 쪽이다.

### Gaps
- Meta 공식 Threads API 문서와 변경 로그 원문을 직접 열지 못해 레이트 리밋 수치를 1차로 확인하지 못했다(한 가이드는 Meta 레이트 리밋 페이지가 404라고 보고).
- 한국에서 Threads 광고의 실제 집행 가능 여부, CPM, 소상공인 성과 데이터는 찾지 못했다.
- 2026년 국내 Threads MAU 최신 수치(2026년 3분기 기준)는 찾지 못했다. 일부 블로그의 '543만 명' 같은 수치는 출처와 시점이 불분명해 제외했다.

## 4. 네이버 클립과 틱톡: 서드파티 업로드 경로, 한국 로컬 비즈니스에서 네이버 클립의 중요성

### Takeaway
네이버 클립은 2026-08 기준 DAU 1,200만 명을 넘었고, 플레이스 리뷰와 연동되며, 2026년 하반기 롱폼(PC 3분 초과) 업로드까지 열려 지역 매장 검색 동선의 핵심 숏폼 채널이 됐다. 다만 외부 앱이 업로드할 수 있는 공개 API는 확인되지 않았다. PC 웹의 다중 업로드와 예약 기능을 활용하는 '반자동'이 현실적이다. 틱톡 Content Posting API는 감사를 통과하기 전에는 비공개(SELF_ONLY) 게시만 가능하다.

### Cited Findings
**네이버 클립**
- [2026-02-06] 2026년 클립 크리에이터 프로그램은 최초 1만 명에서 최대 2만 명까지 선발하는 상시 운영 체제로 바뀌었다. 활동 기간은 약 11개월(2~12월)이고, 활동비와 어워즈 상금을 합쳐 월 최대 90만 원이다. 숏폼뿐 아니라 텍스트와 이미지를 결합한 게시물도 수익화 대상이다 — [뉴시스 2026-02-06](https://www.newsis.com/view/NISX20260206_0003505593); [네이트뉴스](https://m.news.nate.com/view/20260206n29119)
- [2026-03-09] 네이버는 클립 크리에이터 수익 지원을 확대했다 — [바이라인네트워크](https://byline.network/2026/03/09_naver_clip/)
- [2026-04-14] MY플레이스와 클립 프로필을 연결하면 기존 플레이스 리뷰(숏폼 클립 리뷰, 텍스트, 사진·동영상)를 한 번에 클립 프로필로 연동할 수 있다 — [비즈워치](https://news.bizwatch.co.kr/article/mobile/2026/04/14/0004); [디지털데일리](https://www.ddaily.co.kr/page/view/2026041411252645600)
- [2026-08-13] 클립의 전월 평균 DAU가 1,200만 명을 넘었다. 2026년 하반기에는 숏폼, 리뷰, 롱폼을 모두 올릴 수 있는 통합 동영상·리뷰 플랫폼으로 넓히고, 연내 '네이버 메이트' 대상에 클립 크리에이터를 추가할 계획이다 — [전자신문 2026-08-13](https://www.etnews.com/20260813000395)
- [2026-08-18 네이버 안내 → 2026-08-23 정리] PC 클립 크리에이터 웹에서는 3분 초과 영상을 올릴 수 있고, 긴 영상은 PC에서만 올릴 수 있다. 네이버앱과 클립 크리에이터 앱 등 모바일은 최대 1분 30초다. AI 하이라이트 기능도 소개됐다 — [다이오라마마케팅](https://www.dioramarketing.co.kr/blog/naver-clip-long-video-ai-highlight-2026)
- [2026-10-05 확인] PC 웹에서는 완성된 영상 파일 업로드(드래그 앤 드롭), 다중 업로드, 예약, 임시저장이 가능하다. 'PC 업로드 미지원'이라고 쓴 구 가이드(Filmora)는 현재 상황과 맞지 않는다 — [다이오라마마케팅](https://www.dioramarketing.co.kr/blog/naver-clip-pc-upload-guide); [Filmora (구버전 정보)](https://filmora.wondershare.kr/video-editing-tips/naver-clip-upload.html)
- [2026] 네이버 검색 API는 NAVER API HUB로 이관 중이며, 기존 개발자센터 방식은 2027-06-30에 지원이 끝난다. 이것은 검색 API이고 클립 업로드와는 무관하다 — [Waffleboard](https://waffleboard.io/blog/naver-search-api-hub-migration-guide)

**틱톡**
- [공식 문서, 2026 확인] 감사받지 않은 API 클라이언트의 콘텐츠는 비공개 보기로 제한된다. 이를 풀려면 ToS 준수 감사가 필요하다. 감사 전 Direct Post는 SELF_ONLY이며 24시간 기준 사용자 5명으로 제한된다는 보고가 있다. 에러 코드는 unaudited_client_can_only_post_to_private_accounts(HTTP 403)다. 받은편지함 초안(inbox draft) 업로드는 이 제한에서 예외라는 보고가 있다. 감사 소요 기간은 공개되지 않았다 — [TikTok for Developers: Direct Post](https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post); [PostZen](https://www.postzen.dev/blog/tiktok-api); [VorpLabs](https://vorplabs.com/agent-tools/tiktok-content-posting-api); [TimeToPost](https://timetopost.co/blog/how-to-post-to-tiktok-api/)

### Inferences
- 카페·미용실·식당 손님의 탐색 동선은 '네이버 지도·플레이스 → 리뷰 → 클립'이다. 클립이 플레이스 리뷰와 묶인 이상, 국내 소상공인에게는 YouTube 쇼츠보다 네이버 클립이 전환에 더 가까울 가능성이 높다(추론, 정량 근거 미확보). 곰대리의 강점인 '네이버 블로그·카페' 자동화와도 자연스럽게 이어진다.
- 공개 업로드 API가 없으므로 무단 브라우저 자동화(로그인 대행 매크로)는 약관과 계정 정지 위험이 크다. 대신 'PC 다중 업로드·예약에 맞춘 파일 묶음(제목·해시태그·장소 정보 포함) 내보내기 + 체크리스트' 방식이 안전하다.
- 틱톡은 감사 전에는 '초안함 업로드(사장님이 앱에서 최종 게시)' 방식으로 제공하는 것이 현실적이다.

### Gaps
- 네이버 클립의 공식 업로드 API 존재 여부를 네이버 개발자 문서로 확인하지 못했다(검색에서 미발견).
- 클립 광고와 숏폼 광고 상품(소상공인용) 및 플레이스 광고 연계는 검색에서 확인하지 못했다.
- 클립이 지역 매장 방문 전환에 미치는 효과를 다룬 정량 데이터는 찾지 못했다.

## 5. AI 영상 도구 기능 벤치마크(2026): 무엇이 '기본기(table stakes)'가 됐나

### Takeaway
2026년 기준 ①자동 자막과 스타일링 ②화면비 자동 리프레이밍 ③긴 영상에서 하이라이트 자동 추출과 점수화(바이럴 점수) ④AI B-roll ⑤감정 표현 TTS ⑥브랜드 키트·템플릿 ⑦다중 플랫폼 자동 게시·캘린더는 주요 도구 대부분이 갖춘 기본기다. 차별화는 ⑧URL·웹사이트 → 광고·소셜 영상 자동 기획·게시(Mirage Social Studio, VCAT URL 영상) ⑨디지털 트윈 아바타와 립싱크 번역(HeyGen) ⑩에이전트·API(MCP) 연동 ⑪생성형 영상 모델(Veo 3.1, Kling 3.0, Runway Gen-4.5, Seedance) 통합으로 옮겨 갔다. Sora 2는 2026년에 서비스가 종료됐다는 2차 보도가 있다(검증 필요).

### Cited Findings
**클리핑과 리퍼포징**
- [2026] Opus Clip: 바이럴 점수(0~99, Hook·Flow·Value·Trend 구성)를 Starter·Pro에서 제공한다. 점수와 실제 조회수의 상관관계를 다룬 연구는 공개하지 않았다. Starter는 YouTube Shorts, TikTok, Instagram Reels 자동 게시를 지원하고, Pro는 X, Facebook, LinkedIn, Pinterest, Threads, Bluesky와 캘린더 스케줄러를 추가한다. Starter는 월 15달러, 150크레딧이다. 자동 리프레이밍, AI 자막, AI B-roll, 자연어로 구간을 찾는 ClipAnything을 제공한다. 에이전트용 MCP 서버(29개 도구)와 REST API(Pro 베타)가 있다는 보고가 있지만 공식 확인은 못 했다 — [SendShort 리뷰](https://sendshort.ai/guides/opus-review/); [Ssemble](https://www.ssemble.com/blog/opus-clip-review-2026); [Javis Review](https://javisreview.com/review/opusclip-review-2026/)
- [2026] Vrew(브루): 긴 영상을 요약본이나 하이라이트 클립으로 자동 변환하는 기능(파일 탭 '비디오 리믹스')이 있다. 2026-04-22부터 모든 AI 기능에 공통으로 쓰는 '통합 크레딧'으로 바뀌었고 무료 200크레딧이라는 2차 정보가 있다. 최신 버전은 4.3.1(2026-07)로 소개된다. 4.0.0에서 '이미지 한 장으로 생성부터 영상까지'와 일관성 있는 쇼츠 만들기를 도입했다(시점 불명확) — [Vrew 공식: 쇼츠 만들기](https://vrew.ai/ko/feature/video-summarizer/); [모켓](https://www.moket.kr/tools/vrew); [Vrew 공식 블로그](https://vrew.ai/ko/blog/all/vrew-ai-edit-start/)
- [2026] CapCut: 자동 자막 정확도는 영어 토킹헤드 기준 약 92~94%이고, 20개 이상 언어를 지원하며, 자막 자동 번역도 된다. 생성형 모델 Seedance 2.0은 일부 국가(브라질, 인도네시아 등)의 유료 사용자에게 순차 제공되고, 미국은 2026-05 기준 미제공이다. 최신 가이드는 Seedance 2.5가 PC·웹 Pro/Ultra에서 초당 과금된다고 언급한다(출처마다 다름). ByteDance는 SMB용 별도 플랫폼 Pippit을 운영한다 — [CapCut Ideas](https://www.capcut.com/ideas/seedance-2-0-for-subtitle-editing); [NemoVideo](https://www.nemovideo.com/blog/capcut-ai-video-generator-review); [arwriterai](https://arwriterai.com/en/blog/capcut-ai-features-complete-guide-2026/); [Wikipedia: Pippit](https://en.wikipedia.org/wiki/Pippit)

**URL·상품 기반 마케팅 영상**
- [2025-06] VCAT.AI(브이캣): 상세페이지 URL 하나로 이미지·텍스트를 추출하고 브랜드 가이드에 맞춰 이미지·영상을 자동 제작한다. 도움말 기준 '템플릿 자동 추천'과 '직접 선택' 방식이 있고, 최대 15초 영상과 이미지 20장을 1분 만에 만든다고 소개한다. NHN커머스 앱스토어(샵바이, 고도몰)에 입점해 있다. 2026년 신기능은 확인하지 못했다 — [ZDNet Korea 2025-06-05](https://zdnet.co.kr/view/?no=20250605143249); [VCAT.AI 도움말](https://vcat.ai/help/ko/articles/9775002-url%EB%A1%9C-%EC%98%81%EC%83%81-%EC%A0%9C%EC%9E%91); [NHN커머스 앱스토어](https://apps.nhn-commerce.com/apps/499)
- [2025-09~2026] Captions는 2025-09에 Mirage로 리브랜딩했다(자체 파운데이션 모델 중심). 최근 기능은 'Social Studio'(웹사이트 링크를 넣으면 AI가 소셜 영상을 기획·제작·게시), 'AI Ads'(휴대폰·PC 화면 제품 데모, 상품 URL로 UGC형 광고 변형 다수 생성), 디지털 아바타, TikTok 연결이다. 약관상 AI 액터를 광고에 쓰려면 서면 동의가 필요하다는 보고가 있다 — [Wikipedia: Captions](https://en.wikipedia.org/wiki/Captions_(app)); [Mirage/Captions Help: What's new](https://help.mirage.app/updates/android); [AdTestBench](https://adtestbench.com/ai-ugc/)

**아바타와 TTS**
- [2026] HeyGen: Avatar IV가 사진·디지털 트윈 애니메이션 엔진이고, 2026-09 리뷰는 더 새로운 Avatar V를 언급한다. 립싱크 번역은 175~177개 언어(HeyGen 자체 블로그 수치)이며 Speed와 Precision 모드가 있다. Precision 립싱크는 분당 10크레딧, 오디오만 번역하면 분당 4크레딧이다. 립싱크와 Avatar IV는 플랜별 상한이 있는 'Premium Credits'를 쓴다. 무료 플랜은 월 1분 영상 3개(워터마크) — [HeyGen 블로그: AI 더빙](https://www.heygen.com/blog/best-ai-dubbing-tools); [HeyGen 블로그: 다국어 아바타](https://www.heygen.com/blog/best-ai-avatars-multilingual-marketing); [BIGVU](https://bigvu.tv/blog/heygen-ai-avatar-video-generator-complete-review-2026-best-ai-video-generation-tool/); [DIYAI 2026-09](https://diyai.io/ai-tools/video-generation/reviews/heygen-review/)
- [2026] Synthesia: 프레젠터형 아바타와 160개 이상 언어 더빙을 제공하며 교육·기업용 중심이다. 이용정책상 스톡 아바타를 SNS 유료·부스트 광고에 쓰려면 서면 동의가 필요하다는 보고가 있다. 2026년 신기능은 확인하지 못했다 — [AdTestBench](https://adtestbench.com/ai-ugc/); [Pixo](https://pixo.video/blog/heygen-alternatives)
- [2026-02-25] 타입캐스트: 자체 모델 SSFM 3.0 기반으로 문맥에 맞춰 감정을 자동 적용하는 TTS API를 출시했다(emotion_type="smart", previous_text·next_text로 정확도 향상). 500개 캐릭터, 37개 언어, 보이스당 최대 7개 감정·스타일 프리셋과 강도·피치·속도 조절을 지원한다. 단어·문자 단위 타임스탬프 TTS API(자막·립싱크용)가 있고, API 출시 후 월 2배씩 성장했다고 회사가 주장한다 — [인공지능신문 2026-02-25](https://www.aitimes.kr/news/articleView.html?idxno=38778); [플래텀](https://platum.kr/archives/282452); [타입캐스트: SSFM 3.0](https://typecast.ai/kr/learn/typecast-api-ssfm-v30-smart-emotion/); [타입캐스트 API](https://typecast.ai/developers/api/)

**생성형 영상 모델(2026)**
- [2026] Veo 3.1은 대사·효과음·환경음을 한 번에 생성하는 네이티브 오디오(48kHz)에서 가장 일관된 평가를 받는다. 1회 생성 길이는 4/6/8초이며, '최대 60초'는 연장 기능 기준으로 보인다. Kling 3.0은 가장 저렴하고 동적 움직임이 강하지만 오디오가 탁하다는 평이 있다. Runway Gen-4.5는 카메라 제어와 캐릭터 일관성에 강하고, 2025-12부터 네이티브 오디오를 지원한다(구 비교표에는 무음으로 표기돼 상충) — [Lushbinary](https://lushbinary.com/blog/ai-video-generation-sora-veo-kling-seedance-comparison/); [BuildMVPFast](https://www.buildmvpfast.com/blog/ai-video-generation-api-sora-veo-runway-developer-2026); [Rangy](https://rangy.ai/blog/veo-vs-kling-vs-runway/); [Tech Insider](https://tech-insider.org/best-ai-video-generator-2026/)
- [2026, 검증 필요] 여러 2차 출처는 OpenAI가 Sora 2를 종료했다고 전한다(앱 2026-04-26, API 2026-09-24). 1차 출처로는 확인하지 못했다 — [KursVideoAI](https://kursvideoai.pl/en/blog/sora-vs-veo-vs-runway-vs-kling/); [Lushbinary](https://lushbinary.com/blog/ai-video-generation-sora-veo-kling-seedance-comparison/)

### Inferences
- 기본기 체크리스트(2026)와 곰대리 컷대장의 공개 문구("블로그 → 영상 3분", "편집 10분 대체")를 비교하면 다음과 같다. 컷대장이 강조하는 것은 '텍스트 → 영상 생성'과 '편집 시간 단축'이다. 상대적으로 확인되지 않는 것은 바이럴 점수와 A/B, 다중 플랫폼 자동 게시·캘린더, 브랜드 키트, 아바타·립싱크, 생성형 B-roll이다. 단, 컷대장의 실제 기능 목록은 공식 사이트가 없어 확인하지 못했다.
- 국내 경쟁 구도: 브루는 무료와 한국어 자막 강자, 브이캣은 커머스 URL 영상, 타입캐스트는 한국어 감정 TTS API, CapCut과 Edits는 무료 편집으로 자리 잡고 있다. 컷대장이 이들과 기능 대 기능으로 싸우기보다 '업종별 로컬 매장 기획 + 네이버 생태계(블로그·카페·플레이스·클립) + 게시 자동화'의 통합으로 차별화하는 편이 합리적이다.
- 타입캐스트 API(감정 자동, 타임스탬프)를 쓰면 자체 TTS 없이도 '감정 있는 한국어 내레이션 + 단어 단위 자막 싱크'를 쉽게 붙일 수 있다(외부 API 의존과 비용은 확인 필요).

### Gaps
- 컷대장 자체의 정확한 기능, 요금, 출력 품질은 공식 사이트를 찾지 못해 확인하지 못했다.
- Vrew, VCAT, Synthesia의 2026년 공식 릴리스 노트는 확보하지 못했다.
- Veo 3.1, Kling 3.0의 공식 가격과 한국어 대사 생성 품질은 공식 자료로 확인하지 못했다.
- Sora 2 종료는 2차 보도에만 근거한다.

## 6. 영상 번역·더빙 최신 수준과 외국인 관광객 대상 한국 매장 활용

### Takeaway
2026년 영상 번역 시장은 셋으로 나뉜다. ①무료 플랫폼 내장(YouTube 자동 더빙 27개 언어, 립싱크는 파일럿) ②음성 더빙 API(ElevenLabs Dubbing v2, 한국어 포함 92개 언어, 립싱크 없음) ③립싱크 영상 번역(HeyGen 175개 이상 언어, Perso AI는 ElevenLabs 음성과 프레임 단위 립싱크, sync.so)이다. 1~9월 방한객 1,711만 명 중 중국(547만), 일본(312만), 대만(186만), 홍콩(55만)이 상위라서, 한국 매장의 영상 번역 우선순위는 중국어(간체와 번체 모두), 일본어, 영어다.

### Cited Findings
- [2026-08] ElevenLabs는 음성 대 음성(speech-to-speech) 방식의 Dubbing v2 API를 출시했다. 한국어를 포함해 92개 언어를 지원하지만 영상 립싱크 처리는 제공하지 않는다 — [The Elec](https://www.thelec.net/news/articleView.html?idxno=12934)
- [게시일 미상] ElevenLabs 공식 도움말: 더빙에는 립싱크가 없고, 립싱크는 이미지·영상 기능이나 Studio의 서드파티 모델로 제공한다 — [ElevenLabs Help](https://help.elevenlabs.io/hc/en-us/articles/23793433149073-Do-you-offer-lip-sync-in-Dubbing)
- [2025~2026] Perso AI(이스트소프트)는 ElevenLabs 음성 기술에 자사의 프레임 단위 립싱크, 다중 화자 분리, 영상 번역 파이프라인을 결합한다. Perso V3는 한국어를 포함해 99개 이상 언어를 지원한다(자사 홍보 수치). 이스트소프트는 2025년 ElevenLabs와 파트너십을 맺었다 — [ElevenLabs 블로그: PERSO.ai](https://elevenlabs.io/blog/persoai); [Perso V3](https://perso.ai/v3-ai-dubbing-model); [Wikipedia: ESTsoft](https://en.wikipedia.org/wiki/ESTsoft)
- [2026-05] sync.so는 ElevenLabs 음성 더빙 뒤에 립싱크를 한 번에 적용하는 워크플로를 출시했다. 지원 목록에 한국어는 명시돼 있지 않았다 — [sync.so](https://sync.so/blog/introducing-ai-dubbing-in-sync)
- [2026] HeyGen 영상 번역은 175~177개 언어, Speed와 Precision(립싱크) 모드를 제공하며, 비용은 Precision 분당 10크레딧, 오디오만 4크레딧이다. Rask AI, Maestra, Kapwing과의 비교 글이 있다(HeyGen 자체 블로그라 편향 가능) — [HeyGen 블로그: AI 더빙](https://www.heygen.com/blog/best-ai-dubbing-tools); [HeyGen vs Rask AI 비교](https://www.heygen.com/blog/heygen-vs-rask-ai-vs-maestra-vs-kapwing)
- [2026-02] YouTube 자동 더빙은 27개 언어로 GA됐고 Expressive Speech는 8개 언어다(한국어 미포함으로 보임). 립싱크는 파일럿이다(1번 항목 참조) — [PPC Land](https://ppc.land/youtube-auto-dubbing-tops-6m-daily-viewers-expands-to-27-languages/)
- [2026-08] Instagram Edits는 15개 언어 이중언어 자막을 추가했다(2차 출처) — [arwriterai](https://arwriterai.com/en/blog/instagram-edits-app-update-2026/)
- [2026-10-22] 문체부의 2026년 9월 방한 관광 동향: 1~9월 방한객은 1,711만 명(전년 동기 대비 +21.5%)이다. 국가별로는 중국 547만(+29.2%, 약 32%), 일본 312만(+16.9%), 대만 186만(+32.4%), 홍콩 55만(+18.6%), 미주 162만(+12.0%)이다. 9월 한 달은 206만 명이고, 2025년 연간은 1,894만 명이었다 — [한국경제 2026-10-22](https://www.hankyung.com/article/202610227461g); [뉴스핌](https://www.newspim.com/news/view/20261022000161); [파이낸셜뉴스](https://www.fnnews.com/news/202610220454378743)

### Inferences
- 단순 음성 더빙은 YouTube가 무료로 제공하고(언어 목록 확인 필요) ElevenLabs API로도 쉽게 붙일 수 있어 차별성이 낮다. 소상공인용 '영상 번역'의 가치는 ①메뉴명·가격·위치 같은 고유명사 용어집과 정확한 현지 표현 ②화면 안 텍스트(메뉴판, 자막 카드) 현지화 ③번체(대만·홍콩)와 간체(중국 본토) 구분 ④사장님 본인 목소리 클론과 립싱크(동의 기반) ⑤언어별 제목·해시태그·설명과 플랫폼별 배포에서 나온다.
- 대만 방한객 증가율(+32.4%)이 가장 높고 홍콩까지 더하면 번체권이 240만 명을 넘는다. '중국어 = 간체'로만 처리하면 큰 시장을 놓친다.
- 관광객은 국내 플랫폼(네이버 클립, Threads)보다 Instagram, YouTube, 그리고 중국 본토라면 샤오홍슈·더우인 같은 자국 플랫폼으로 탐색할 가능성이 높다(추론, 이번 조사 범위 밖이며 근거 미확보).

### Gaps
- 한국어 → 일본어·중국어 립싱크 더빙 품질을 비교한 독립 벤치마크는 찾지 못했다.
- Rask AI의 2026년 현황(언어 수, 립싱크 품질)은 HeyGen 비교 글 외에는 확인하지 못했다.
- 외국인 관광객의 매장 탐색 플랫폼 비중(샤오홍슈, Instagram, Google Maps, 네이버 지도)은 이번 조사에서 확보하지 못했다.

## 7. 시사점: 컷대장, 쇼츠·스레드 자동화, 영상번역이 추가·변경해야 할 기능

### Takeaway
2026년 플랫폼들은 공통적으로 '대량 생산·템플릿 반복·재게시'를 벌하고 '오리지널·사람의 관여'를 보상한다. 한국은 2026-01-22부터 AI 기본법으로 AI 서비스 제공 사업자에게 생성물 표시(워터마크) 의무를 지웠다. 따라서 곰대리의 다음 버전은 "더 많이, 더 빨리"보다 ①원본성(사장님 소스·목소리·변주) ②정책 준수 자동화(AI 표시·반복성 검사) ③공식 API 기반의 멀티채널 게시(네이버 클립 반자동 포함) ④테스트·인사이트 루프 ⑤관광객용 현지화 번역에 투자해야 한다.

### Cited Findings
**한국 AI 기본법: 제품에 직접 영향**
- [2026-01-22 시행] AI 기본법이 시행됐다. 생성형 AI 결과물 표시(워터마크) 의무는 AI 서비스를 제공하는 사업자에게만 있고, 결과물을 소비·게시하는 일반 이용자는 대상이 아니다. 일반 결과물은 가시적 표시와 비가시적 표시(디지털 워터마크 등) 중 고를 수 있다. 실제와 구분하기 어려운 딥페이크(제31조)는 이용자가 명확히 인식할 수 있도록 가시적으로 표시해야 한다. 예술·창의적 표현물은 감상을 해치지 않는 방식으로 표시할 수 있다 — [뉴시스 2026-01-21](https://www.newsis.com/view/NISX20260121_0003484769); [국민일보](https://www.kmib.co.kr/article/view.asp?arcid=1768984300); [ZDNet Korea 2026-01-20](https://zdnet.co.kr/view/?no=20260120125937)
- [2026] 제재는 시정명령이고, 이를 따르지 않으면 3,000만 원 이하 과태료다. 계도기간은 최소 1년 이상으로 안내된다(블로그 정리라 시행령 원문 대조 필요). 네이버는 쇼핑라이브 등 전 서비스에 AI 워터마크를 확대할 방침이다 — [오픈위키 (2026-08 기준)](https://wikidocs.net/blog/@openwiki/28121/); [ZDNet Korea](https://zdnet.co.kr/view/?no=20260120125937)
- 정책 근거 요약(앞 항목에서 인용): YouTube 비진정성 3개 범주와 채널 단위 집행 [2026-07], YouTube 자동 AI 라벨 [2026-05-27], Instagram 애그리게이터 추천 제외의 사진·캐러셀 확대 [2026-04-30], Threads engagement-bait 답글 하향 [2025~2026], Instagram 게시 100건/24h와 trial_params [2026], Threads API 기능 확장 [2025-07 ~ 2026-04], YouTube 업로드 쿼터 분리(일 100회) [2026-06], TikTok 감사 전 비공개 [2026], 네이버 클립 공개 업로드 API 미확인과 PC 예약 업로드 [2026-08~10] — [TechCrunch 2026-07-20](https://techcrunch.com/2026/07/20/youtube-clarifies-policies-around-ai-slop-and-upsetting-videos/); [Variety](https://variety.com/2026/digital/news/youtube-ai-video-labels-automatic-detection-1236758865/); [TechCrunch 2026-04-30](https://techcrunch.com/2026/04/30/instagram-restricts-reach-of-content-aggregators-in-new-crackdown/); [BulkPublish](https://www.bulkpublish.com/blog/threads-algorithm/); [Reel Uploader](https://reeluploader.com/blog/instagram-api-publishing-limits); [Social Media Today](https://www.socialmediatoday.com/news/meta-updates-threads-api-with-more-third-party-app-integrations/817502/); [TimeToPost](https://timetopost.co/blog/how-to-upload-videos-youtube-api/); [TikTok for Developers](https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post); [다이오라마마케팅](https://www.dioramarketing.co.kr/blog/naver-clip-pc-upload-guide)

### Inferences
**A. 컷대장(AI 쇼츠 제작·편집): 추가·변경 제안**
1. 원본 소스 우선 파이프라인: '블로그 글 → 스톡·생성 이미지 + TTS' 기본값을 '사장님 휴대폰 촬영본(매장, 메뉴, 시술 과정) 업로드 → AI가 컷 선별, 자막, 구성'으로 바꾼다. 실촬영 소스가 없을 때만 생성형 B-roll(Veo 3.1, Kling 3.0 등)로 보충하고, 비율 가이드(예: 실촬영 50% 이상)를 둔다. 근거는 YouTube 템플릿·반복 범주와 Instagram 오리지널 판정이다.
2. 반복성(유사도) 검사기: 같은 계정의 최근 업로드와 템플릿, BGM, 스크립트 구조, 썸네일을 비교해 "최근 N개와 너무 비슷함" 경고를 내고 변주를 자동 제안한다(훅 문장, 컷 순서, 색감, 음성). 고객 간에도 같은 템플릿을 동시에 쓰는 비율을 제한한다(애그리게이터·중복 콘텐츠 방지).
3. 사람 관여 레이어: 사장님 본인 음성 녹음(10초 원테이크) 또는 본인 동의를 받은 보이스 클론, 사장님 얼굴 디지털 트윈(본인 likeness, 동의서 저장)을 기본 옵션으로 제공한다. 스톡 AI 아바타는 Synthesia와 Mirage처럼 광고 사용 제한이 있으므로 약관을 표기한다.
4. AI 표시 자동화와 컴플라이언스: 출력물에 비가시 워터마크·메타데이터를 넣고(AI 기본법상 서비스 제공 사업자 의무 대비), 사실적 합성 인물이나 장면이 있으면 가시 표시를 넣는다. 업로드 시 YouTube 'altered or synthetic' 체크 여부를 자동 판정하고 안내한다. 건강·금융성 업종(한의원, 보험 등)에서 AI 페르소나 사용을 막거나 경고한다(YouTube 2026-07 범주 ③).
5. 기본기 보강: 9:16/1:1/4:5 동시 출력(Threads·Instagram 광고는 4:5), 자막 스타일 프리셋과 브랜드 키트(로고, 색, 폰트), 감정 TTS(예: 타입캐스트 smart emotion API)와 단어 단위 자막 싱크, 긴 영상(사장님 인터뷰, 라이브) → 하이라이트 쇼츠 자동 추출과 점수(Opus식, 단 점수의 한계 고지)를 갖춘다.
6. 업종별 기획 템플릿을 '형식'이 아니라 '기획'으로 제공한다: 미용실 비포·애프터, 식당 조리 과정·오늘의 메뉴, 학원 합격 후기(개인정보 동의), 카페 신메뉴 투표 연계 등. 같은 기획이라도 매번 다른 구성으로 생성한다.

**B. 쇼츠·스레드 자동화(배포): 추가·변경 제안**
1. 공식 API와 감사 기반 아키텍처: YouTube는 API 프로젝트 감사와 쿼터 증설 신청을 진행한다(업로드 버킷 일 100회/프로젝트로 보도됨). TikTok은 감사 전에는 '초안함 업로드' 모드로 제공한다. Instagram은 자체 예약 큐를 운영하고(컨테이너 24시간 만료, 100건/24h, publishing_limit 사전 확인), Threads는 250게시/1,000답글 한도를 모니터링한다. 비공식 매크로나 로그인 대행은 배제한다.
2. Instagram 트라이얼 릴스 A/B: 같은 소재 2~3개 버전을 trial_params(SS_PERFORMANCE)로 비팔로워 테스트한 뒤 자동 졸업시키고, 이긴 훅을 다음 제작에 반영하는 루프를 만든다.
3. Threads 고급 기능 활용: 위치 태그(매장), 투표(메뉴 선택), 토픽 태그(지역·업종), 고스트 포스트(당일 한정 이벤트), 링크 첨부(예약·플레이스 링크, 단 링크 가중치는 미확인), 인스타 스토리 교차 공유, 인사이트 리포트를 쓴다.
4. 답글 코파일럿(사람 승인형): 키워드·태그 검색(미디어 타입 필터)으로 '지역 + 업종' 질문 글을 찾아 답글 초안을 만들고, 사장님이 원탭으로 승인한다. 내 게시물 답글은 승인 대기와 숨김 API로 악성 댓글을 관리한다. 자동 대량 답글은 engagement-bait 하향 대상이 될 수 있어 금지한다.
5. 네이버 클립 반자동 패키지: 공개 업로드 API가 확인되지 않았으므로 '클립용 파일(1분 30초 이하 모바일용 / 3분 초과 PC용) + 제목·태그·장소 묶음 내보내기 → PC 다중 업로드·예약 가이드'를 제공한다. 플레이스 리뷰·클립 프로필 연동과 클립 크리에이터 프로그램 지원 안내도 포함한다. 곰대리 블로그·카페 글과 같은 키워드로 클립을 연동하는 크로스 채널 캠페인을 묶는다.
6. 채널별 재가공(같은 영상 그대로 뿌리지 않기): 플랫폼마다 훅, 자막, 길이, 비율, 캡션을 다르게 자동 변형해 중복·애그리게이터 판정 위험을 낮춘다.

**C. 영상번역: 추가·변경 제안**
1. 언어 우선순위 프리셋은 '중국어 간체 + 번체(대만·홍콩) + 일본어 + 영어'로 한다(2026년 1~9월 방한 통계 기준).
2. 매장 용어집: 메뉴명, 시술명, 가격, 주소, 영업시간을 고정 번역 사전으로 관리하고, 숫자·통화·주소 표기를 현지화한다. 화면 내 텍스트(메뉴판, 자막 카드) 번역도 포함한다.
3. 품질 단계 분리: '자막 번역(무료·저가) → 음성 더빙(ElevenLabs Dubbing v2급 API) → 립싱크(Perso, HeyGen급, 사장님 출연 영상에만)' 3단 요금 구조로 나눈다. YouTube 자동 더빙이 무료라는 점을 고려해 YouTube용은 자막과 메타데이터 번역에 집중하고, Instagram용은 번역 자막을 영상에 입히는(burn-in) 방식으로 한다.
4. 언어별 메타데이터 패키지: 제목, 설명, 해시태그, 지도 링크(Google Maps, 네이버 지도)를 언어별로 생성한다. 외국인용 짧은 매장 소개 영상(15~30초)과 외국어 Threads·Instagram 캡션을 세트로 제공한다.
5. 동의와 표시: 사장님 목소리·얼굴 클론에 동의서를 받고, 립싱크 합성 영상에는 AI 기본법상 딥페이크 가시 표시가 필요한지 법률 검토를 표시 기능과 연동한다.

### Gaps
- 곰대리, 컷대장의 실제 현재 기능, 가격, 사용하는 API 구조는 공식 사이트가 없고 YouTube 접근이 막혀 확인하지 못했다. 그래서 위 제안 중 일부는 이미 구현돼 있을 수 있다.
- AI 기본법 시행령에서 '영상 편집 SaaS가 사업자 의무 주체인지', 표시 방식의 세부 기준, 계도기간 정확한 일정은 법령 원문으로 확인하지 못했다.
- 위 기능들의 효과(도달, 전환 개선)를 입증하는 소상공인 대상 정량 데이터는 확보하지 못했다.
