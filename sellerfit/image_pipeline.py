"""
image_pipeline.py - 이미지 처리 파이프라인
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
도완님 결정: "3. 크롤링" (도매꾹에서 다운로드 → 쿠팡 업로드)

쿠팡 상품 등록 API는 이미지 URL을 직접 받는 방식.
즉 "우리가 접근 가능한 URL만 있으면 쿠팡이 알아서 가져감".

Slice 1 전략 (단순화):
  1. 도매꾹 이미지 URL 접근성 먼저 체크
  2. 접근 가능하면 → URL 그대로 쿠팡에 전달 (이미지 1차 시도)
  3. 접근 불가능하면 → 로컬 다운로드 후 snapshot에 저장 (다음 버전에서 별도 호스팅)

※ 쿠팡이 외부 도메인(특히 alicdn.com 같은 해외)을 거부할 수 있어서
   Slice 2에서 자체 CDN 업로드 로직 추가 예정.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

try:
    import requests
except ImportError:
    raise ImportError("requests 미설치")

from logger import log


UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


@dataclass
class ImageResult:
    """이미지 1장 처리 결과"""
    original_url: str
    accessible: bool = False          # HEAD 응답 OK?
    final_url: str = ""               # 쿠팡에 전달할 URL
    content_type: str = ""
    size_bytes: int = 0
    local_path: str = ""              # 다운로드된 경우
    error: str = ""

    def to_dict(self):
        from dataclasses import asdict
        return asdict(self)


@dataclass
class ImagePipelineResult:
    """전체 이미지 처리 결과"""
    input_count: int = 0
    accessible_count: int = 0
    downloaded_count: int = 0
    failed_count: int = 0
    results: List[ImageResult] = field(default_factory=list)

    @property
    def usable_urls(self) -> List[str]:
        """쿠팡 등록에 쓸 수 있는 URL 리스트 (순서 보존)"""
        return [r.final_url for r in self.results if r.final_url]

    def to_dict(self):
        return {
            "input_count": self.input_count,
            "accessible_count": self.accessible_count,
            "downloaded_count": self.downloaded_count,
            "failed_count": self.failed_count,
            "results": [r.to_dict() for r in self.results],
        }


class ImagePipeline:
    """이미지 다운로드 + 접근성 체크"""

    def __init__(self, max_images: int = 10, timeout: int = 10,
                 download_dir: Optional[Path] = None):
        self.max_images = max_images
        self.timeout = timeout
        self.download_dir = Path(download_dir) if download_dir else None
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": UA,
            "Accept-Language": "ko-KR,ko;q=0.9",
        })

    def process(self, image_urls: List[str],
                download_if_needed: bool = False) -> ImagePipelineResult:
        """
        이미지 URL 리스트 처리.

        Args:
            image_urls: 도매꾹에서 받은 이미지 URL 리스트
            download_if_needed: True면 접근 불가 URL을 로컬 다운로드 시도

        Returns:
            ImagePipelineResult
        """
        pipeline_result = ImagePipelineResult(input_count=len(image_urls))

        urls = image_urls[:self.max_images]

        for i, url in enumerate(urls, 1):
            result = self._process_single(url, index=i, download=download_if_needed)
            pipeline_result.results.append(result)

            if result.accessible:
                pipeline_result.accessible_count += 1
            elif result.local_path:
                pipeline_result.downloaded_count += 1
            else:
                pipeline_result.failed_count += 1

        log.info(
            f"[IMG] 처리 완료: 접근 {pipeline_result.accessible_count}/{len(urls)}, "
            f"다운로드 {pipeline_result.downloaded_count}, "
            f"실패 {pipeline_result.failed_count}"
        )
        return pipeline_result

    def _process_single(self, url: str, index: int = 0,
                        download: bool = False) -> ImageResult:
        """이미지 1장 처리"""
        result = ImageResult(original_url=url)

        if not url:
            result.error = "빈 URL"
            return result

        # 1. HEAD로 접근성 체크
        try:
            r = self.session.head(url, timeout=self.timeout, allow_redirects=True)
            if 200 <= r.status_code < 300:
                result.accessible = True
                result.final_url = url
                result.content_type = r.headers.get("Content-Type", "")
                cl = r.headers.get("Content-Length")
                if cl:
                    try:
                        result.size_bytes = int(cl)
                    except ValueError:
                        pass
                return result
            else:
                result.error = f"HEAD HTTP {r.status_code}"
        except requests.exceptions.RequestException as e:
            result.error = f"HEAD: {type(e).__name__}"

        # 2. GET 재시도 (일부 서버는 HEAD 거부)
        try:
            r = self.session.get(url, timeout=self.timeout, stream=True)
            if 200 <= r.status_code < 300:
                result.accessible = True
                result.final_url = url
                result.content_type = r.headers.get("Content-Type", "")
                # 다운로드 요청된 경우 content 읽기
                if download and self.download_dir:
                    content = r.content
                    result.size_bytes = len(content)
                    self.download_dir.mkdir(parents=True, exist_ok=True)
                    ext = self._guess_ext(url, result.content_type)
                    local = self.download_dir / f"img_{index:02d}{ext}"
                    local.write_bytes(content)
                    result.local_path = str(local)
                return result
            else:
                result.error = f"GET HTTP {r.status_code}"
        except requests.exceptions.RequestException as e:
            result.error = f"GET: {type(e).__name__}"

        return result

    @staticmethod
    def _guess_ext(url: str, content_type: str) -> str:
        """확장자 추정"""
        url_lower = url.lower()
        for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
            if ext in url_lower:
                return ext
        ct = (content_type or "").lower()
        if "png" in ct:
            return ".png"
        if "webp" in ct:
            return ".webp"
        if "gif" in ct:
            return ".gif"
        return ".jpg"


# ═══════════════════════════════════════════════════════════════
# 테스트
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    pipeline = ImagePipeline(max_images=5)
    test_urls = [
        "https://image11.coupangcdn.com/image/test.jpg",  # 샘플
    ]
    r = pipeline.process(test_urls)
    print(f"접근 가능: {r.accessible_count}/{r.input_count}")
    for item in r.results:
        print(f"  {item.original_url[:60]} → accessible={item.accessible}")
