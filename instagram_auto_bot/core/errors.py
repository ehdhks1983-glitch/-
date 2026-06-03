"""Map exceptions to friendly, actionable Korean messages for the UI (Stage 7).

Imports are done lazily inside the function to avoid any import cycles and to
keep this module importable in minimal environments.
"""

from __future__ import annotations


def is_auth_error(exc: BaseException) -> bool:
    from core.instagram_api import AuthError
    return isinstance(exc, AuthError)


def is_security_checkpoint(exc: BaseException) -> bool:
    from core.instagram_api import SecurityCheckpointError
    return isinstance(exc, SecurityCheckpointError)


def humanize(exc: BaseException) -> str:
    """Return a short, user-facing message explaining ``exc`` and what to do."""
    from core.content_engine import ContentRuleError
    from core.instagram_api import (
        AuthError,
        InstagramAPIError,
        MediaNotReadyError,
        RateLimitError,
        SecurityCheckpointError,
    )
    from core.uploader import UploadError
    from providers.text_base import ProviderError, ProviderUnavailable

    if isinstance(exc, SecurityCheckpointError):
        return ("보안 점검(체크포인트)이 감지되었습니다. 자동화를 중단했습니다. "
                "인스타그램 앱에서 본인 확인 후 토큰을 재발급하세요. (우회는 시도하지 않습니다)")
    if isinstance(exc, AuthError):
        return "인증/권한 오류입니다. 계정 탭에서 액세스 토큰을 재발급해 다시 입력하세요."
    if isinstance(exc, RateLimitError):
        return "API 호출 한도 또는 일일 게시 한도에 도달했습니다. 잠시 후 다시 시도하세요."
    if isinstance(exc, MediaNotReadyError):
        return "미디어가 아직 준비되지 않았습니다(9007). 잠시 후 다시 시도하세요."
    if isinstance(exc, UploadError):
        return "이미지 공개 URL 업로드에 실패했습니다. Cloudinary/ImgBB 키를 확인하세요."
    if isinstance(exc, ContentRuleError):
        return "콘텐츠 규칙(금지어)을 통과하지 못해 생성을 차단했습니다. 주제/브랜드 설정을 조정하세요."
    if isinstance(exc, ProviderUnavailable):
        return "AI 라이브러리가 설치되지 않았습니다. requirements.txt를 설치하세요."
    if isinstance(exc, ProviderError):
        return f"AI 호출 오류: {exc}"
    if isinstance(exc, InstagramAPIError):
        return f"게시 API 오류: {exc}"
    if isinstance(exc, FileNotFoundError):
        return "이미지 파일을 찾을 수 없습니다. 경로를 확인하세요."
    if isinstance(exc, ValueError):
        return f"입력 오류: {exc}"
    return f"오류가 발생했습니다: {exc}"
