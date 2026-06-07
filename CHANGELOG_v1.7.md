# GIF Maker Pro — v1.7.0 변경 사항 (구조 분리)

성격이 다른 두 기능이 한 앱에 섞여 있던 걸, **두 개의 독립 프로그램으로 분리**했습니다.

## ① GIF 메이커 (이 폴더 = 루트) — 움짤 전용
- 탭: **이미지 합치기 · 영상→GIF/WebP/APNG · 화면 녹화 · 편집**(카톡 이모티콘·배치) · 워터마크
- **제거**: 영상 기획 / 쇼츠 제작 탭, 영상 탭의 MP4·쇼츠 옵션 → GIF 도구답게 깔끔해짐
- 기본 탭이 다시 '이미지 합치기'로

### GIF 메이커에 적용하려면
1. 덮어쓰기: `ui_app.py`, `ui_video_tab.py`, `watermark.py`, `config.py`, `version.json`
2. **삭제**(이제 영상 제작기로 이동): `content_planner.py`, `ui_planner_tab.py`, `shorts_maker.py`, `ui_shorts_tab.py`, `tts_engine.py`, `tts_dialog.py`

## ② 영상 제작기 (별도 폴더 `shortsmaker/`) — 쇼츠 전용
- 탭: **영상 기획 → 쇼츠 제작**(기획 결과가 쇼츠로 자동 전달) · 워터마크
- ASS 전문 자막 + ElevenLabs 음성 + 배경음악(페이드/더킹)
- **독립 실행**: 폴더에 `ffmpeg` 복사 후 `python main.py`
- 자세한 건 `shortsmaker/README.md` 참고

## ✅ 검증
- GIF 메이커: engine/카톡/워터마크/배치 + 4탭 레이아웃·앱 구성, 영상탭 MP4/쇼츠 제거 확인 — 통과
- 영상 제작기: 폴더 격리 상태로 앱 구성·기획→쇼츠 연결·쇼츠 빌드(ASS+음성) — 통과
- watermark를 editor 의존에서 분리해 영상 제작기가 GIF 편집코드 없이 독립 동작
