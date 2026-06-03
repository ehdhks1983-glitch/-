"""End-to-end publish pipeline with a human approval gate (spec Stage 5).

Split into two phases so the UI can insert the mandatory review step:

  prepare(topic, media_type, image_sources)  -> PreparedPost   (generate caption,
        process images to ratio, upload to public URLs)            == shown to user
  publish(prepared)                           -> PublishResult   (Graph API 3-step)
        == runs only after the user clicks "승인"

All collaborators are injected, so the pipeline is fully unit-testable offline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from core.content_engine import ContentEngine, PostDraft
from core.image_engine import ImageEngine
from core.instagram_api import DailyPostGuard, InstagramAPI, PublishResult
from core.logging_setup import get_logger
from core.uploader import Uploader

log = get_logger("publish")


@dataclass
class ImageSource:
    """One image input: either an AI prompt or a local file path."""
    mode: str                 # "ai" | "upload"
    prompt: str = ""
    path: str = ""


@dataclass
class PreparedPost:
    draft: PostDraft
    media_type: str
    public_urls: List[str]
    local_paths: List[str] = field(default_factory=list)

    @property
    def caption(self) -> str:
        return self.draft.caption

    @property
    def hashtags(self) -> List[str]:
        return self.draft.hashtags


class PublishPipeline:
    def __init__(self, *, content_engine: ContentEngine, image_engine: ImageEngine,
                 uploader: Uploader, api: Optional[InstagramAPI] = None,
                 guard: Optional[DailyPostGuard] = None) -> None:
        self.content_engine = content_engine
        self.image_engine = image_engine
        self.uploader = uploader
        self.api = api
        self.guard = guard

    # ---- phase 1: build a preview (no posting) -------------------------- #
    def prepare(self, topic: str, media_type: str,
                image_sources: Sequence[ImageSource], *, control=None) -> PreparedPost:
        if not image_sources:
            raise ValueError("이미지 소스가 최소 1개 필요합니다.")
        if control is not None:
            control.checkpoint()

        log.info("콘텐츠 생성 시작: %s (%s)", topic, media_type)
        draft = self.content_engine.generate(topic, media_type=media_type)

        local_paths: List[str] = []
        public_urls: List[str] = []
        for idx, src in enumerate(image_sources, 1):
            if control is not None:
                control.checkpoint()
            if src.mode == "ai":
                path = self.image_engine.from_ai(src.prompt or topic, media_type=media_type)
            elif src.mode == "upload":
                path = self.image_engine.from_upload(src.path, media_type=media_type)
            else:
                raise ValueError(f"알 수 없는 이미지 모드: {src.mode}")
            local_paths.append(path)
            log.info("이미지 %d 호스팅 업로드 중...", idx)
            public_urls.append(self.uploader.upload(path))

        return PreparedPost(draft, media_type, public_urls, local_paths)

    # ---- phase 2: publish (after approval) ------------------------------ #
    def publish(self, prepared: PreparedPost, *, control=None) -> PublishResult:
        if self.api is None:
            raise RuntimeError("InstagramAPI가 설정되지 않았습니다 (토큰/계정 ID 확인).")
        if self.guard is not None:
            self.guard.check()
        if control is not None:
            control.checkpoint()

        caption = prepared.caption
        urls = prepared.public_urls
        mtype = prepared.media_type.lower()

        if mtype == "reels":
            result = self.api.publish_reels(urls[0], caption, control=control)
        elif mtype == "carousel" or len(urls) > 1:
            result = self.api.publish_carousel(urls, caption, control=control)
        else:
            result = self.api.publish_image(urls[0], caption, control=control)

        if self.guard is not None:
            self.guard.record()
        log.info("게시 완료: media_id=%s permalink=%s", result.media_id, result.permalink)
        return result
