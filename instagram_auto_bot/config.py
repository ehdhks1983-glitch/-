"""Central configuration - every externally-dependent value lives here.

Principle #8: no magic numbers / hard-coded selectors elsewhere in the code.
Anything that Meta, a provider, or policy might change (API versions, ratios,
delays, limits, model names) is a named constant in this file.

User secrets are NOT stored here - they default to empty strings and are read
from the per-user settings store at runtime (see ``core/settings_store.py``).
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Meta Graph API
# --------------------------------------------------------------------------- #
# Graph API versions are deprecated on a rolling ~2yr basis - revisit yearly.
GRAPH_API_VERSION: str = "v22.0"
GRAPH_BASE_URL: str = "https://graph.facebook.com"
# Resumable upload host used for Reels video bytes.
RUPLOAD_BASE_URL: str = "https://rupload.facebook.com"
# Instagram Graph host used for long-lived token refresh.
INSTAGRAM_GRAPH_URL: str = "https://graph.instagram.com"
TOKEN_REFRESH_PATH: str = "refresh_access_token"
IG_SCOPES: list[str] = ["instagram_basic", "instagram_content_publish"]

# Container status_code values returned while a media container is processing.
IG_STATUS_FINISHED: str = "FINISHED"
IG_STATUS_IN_PROGRESS: str = "IN_PROGRESS"
IG_STATUS_ERROR: str = "ERROR"
IG_STATUS_EXPIRED: str = "EXPIRED"
# Graph error codes worth retrying (rate limit / transient app issues).
TRANSIENT_ERROR_CODES: frozenset[int] = frozenset({1, 2, 4, 17, 32, 341, 613})
# Token / permission errors - require user re-auth, never a silent retry.
AUTH_ERROR_CODES: frozenset[int] = frozenset({10, 102, 190, 200, 463, 467, 803})
# Subcodes that indicate a security checkpoint / validation gate. The official
# API route should never hit a captcha; if one of these appears we PAUSE/STOP and
# alert the user - we never attempt to bypass it.
CHECKPOINT_SUBCODES: frozenset[int] = frozenset({458, 459, 460, 461})
# Carousel must contain 2-10 children (Meta limit).
CAROUSEL_MIN, CAROUSEL_MAX = 2, 10


def graph_url(*path: str) -> str:
    """Build a versioned Graph API URL, e.g. graph_url(ig_id, 'media')."""
    tail = "/".join(str(p).strip("/") for p in path if str(p) != "")
    return f"{GRAPH_BASE_URL}/{GRAPH_API_VERSION}/{tail}" if tail else f"{GRAPH_BASE_URL}/{GRAPH_API_VERSION}"


# --------------------------------------------------------------------------- #
# Content rules  (Instagram-specific - intentionally different from blog bot)
# --------------------------------------------------------------------------- #
IG_HASHTAG_COUNT: int = 5            # Instagram sweet spot 3-5; 10+ reads as spam.
IG_HASHTAG_MIN: int = 3
IG_HASHTAG_MAX: int = 7
# Banned vocabulary (medical-authority claims). Associative terms handled in
# content_rules via the extended list below.
BANNED_WORDS: list[str] = ["의사", "병원", "전문의"]
# Extra associative / evocative terms also screened out of generated copy.
BANNED_WORDS_EXTENDED: list[str] = [
    "의사", "병원", "전문의", "의원", "진료", "처방", "치료해",
    "가운", "청진기", "닥터", "doctor", "clinic",
]
# Hashtags that should never be emitted (spam / shadow-ban risk magnets).
BANNED_HASHTAGS: list[str] = [
    "#팔로우", "#맞팔", "#선팔", "#좋아요반사", "#follow4follow", "#f4f",
    "#like4like", "#l4l", "#followme", "#팔로워늘리기",
]

THUMBNAIL_RATIO: str = "1:1"
FEED_RATIO: str = "4:5"              # or "1:1"; blog's 3:2 is NOT used on IG.
FEED_RATIO_ALT: str = "1:1"
REELS_RATIO: str = "9:16"
CAPTION_MAX_LEN: int = 2200
CAPTION_HOOK_LEN: int = 125          # front-load keywords within first 125 chars.

# Pixel targets per ratio (width, height) used by the image engine.
RATIO_PIXELS: dict[str, tuple[int, int]] = {
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
    "9:16": (1080, 1920),
    "1.91:1": (1080, 566),
}

# --------------------------------------------------------------------------- #
# Safety / rate limits
# --------------------------------------------------------------------------- #
MAX_POSTS_PER_DAY: int = 2           # conservative self-limit (API hard cap = 100/24h).
API_DAILY_HARD_CAP: int = 100
SCHEDULE_JITTER_MIN: int = 15        # +/- minutes of random jitter on scheduled posts.
PAGE_WAIT_MIN: int = 3               # random inter-action wait (seconds).
PAGE_WAIT_MAX: int = 8
RETRY_COUNT: int = 3                 # retries before skip+log.
RETRY_BACKOFF_BASE: float = 2.0      # exponential backoff base (seconds).
STATUS_POLL_SEC: int = 5             # container status poll interval.
STATUS_POLL_MAX: int = 30            # max polls before giving up (~150s).
HTTP_TIMEOUT_SEC: int = 30           # per-request network timeout.

# Token lifetime (long-lived IG/FB tokens last ~60 days).
TOKEN_LIFETIME_DAYS: int = 60
TOKEN_REFRESH_BEFORE_DAYS: int = 7   # refresh when within this many days of expiry.

# --------------------------------------------------------------------------- #
# Providers (model names are user-configurable; left blank => chosen in UI)
# --------------------------------------------------------------------------- #
TEXT_PROVIDER: str = "claude"        # claude | openai | gemini
TEXT_MODEL: str = ""                 # blank -> default per provider (see provider).
IMAGE_PROVIDER: str = "openai"
IMAGE_MODEL: str = ""                # blank -> provider default.
HOST_PROVIDER: str = "cloudinary"    # cloudinary | imgbb

# Sensible per-provider default models when the user leaves the field blank.
DEFAULT_TEXT_MODELS: dict[str, str] = {
    "claude": "claude-sonnet-4-6",
    "openai": "gpt-4o",
    "gemini": "gemini-1.5-pro",
}
DEFAULT_IMAGE_MODEL: str = "gpt-image-1"

# --------------------------------------------------------------------------- #
# Meta error codes we explicitly defend against
# --------------------------------------------------------------------------- #
ERR_MEDIA_NOT_READY = 9007           # published before container FINISHED.
ERR_MEDIA_URL_UNREACHABLE = 9004      # image/video URL not publicly reachable.

# --------------------------------------------------------------------------- #
# UI
# --------------------------------------------------------------------------- #
APP_TITLE: str = "Instagram Auto Bot"
UI_THEME: str = "dark"               # CustomTkinter appearance mode.
UI_COLOR_THEME: str = "blue"
WINDOW_MIN_SIZE: tuple[int, int] = (1024, 680)
SCHEDULE_REQUIRES_RUNNING_NOTICE: str = (
    "예약 발행은 PC와 프로그램이 켜져 있을 때만 작동합니다."
)
