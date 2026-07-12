<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

# 결과물 전달 규칙 (사용자 요청)

파일을 만들거나 고치는 작업을 마치면, 사용자가 바로 확인할 수 있도록 항상 두 가지를 만들어 전달한다:

1. **미리보기 HTML** — 결과를 눈으로 확인할 수 있는 단일 HTML 파일(가능하면 실제 실행 화면 스크린샷을 인라인 포함)
2. **소스 압축파일(zip)** — 프로젝트 전체 소스(`.git`, `node_modules`, `.next` 제외)
