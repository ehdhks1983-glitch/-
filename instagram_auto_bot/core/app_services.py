"""Factory wiring: build the concrete engines/pipeline from user settings.

Centralises construction so the UI never imports providers directly.  Everything
is lazy (providers import their SDKs only when used), so these builders run fine
without any SDK/keys present - the API is simply ``None`` until a token + user-id
are configured.
"""

from __future__ import annotations

from typing import Optional

import config
from core.content_engine import ContentEngine
from core.image_engine import ImageEngine
from core.instagram_api import DailyPostGuard, InstagramAPI
from core.publish_flow import PublishPipeline
from core.settings_store import SettingsStore
from core.token_manager import TokenManager
from core.uploader import Uploader
from providers.image_openai import OpenAIImageProvider
from providers.text_base import get_text_provider


def build_text_provider(store: SettingsStore):
    return get_text_provider(
        store.get_str("text_provider"),
        store.get_str("text_api_key"),
        store.get_str("text_model"),
    )


def build_image_provider(store: SettingsStore) -> OpenAIImageProvider:
    return OpenAIImageProvider(store.get_str("openai_api_key"), store.get_str("image_model"))


def build_content_engine(store: SettingsStore) -> ContentEngine:
    return ContentEngine(build_text_provider(store), store)


def build_image_engine(store: SettingsStore) -> ImageEngine:
    return ImageEngine(store=store, image_provider=build_image_provider(store))


def build_uploader(store: SettingsStore) -> Uploader:
    return Uploader(store)


def build_api(store: SettingsStore) -> Optional[InstagramAPI]:
    token = store.get_str("ig_access_token")
    user_id = store.get_str("ig_user_id")
    if not (token and user_id):
        return None
    return InstagramAPI(token, user_id)


def build_guard(store: SettingsStore) -> DailyPostGuard:
    return DailyPostGuard(max_per_day=store.get_int("max_posts_per_day", config.MAX_POSTS_PER_DAY))


def build_pipeline(store: SettingsStore) -> PublishPipeline:
    return PublishPipeline(
        content_engine=build_content_engine(store),
        image_engine=build_image_engine(store),
        uploader=build_uploader(store),
        api=build_api(store),
        guard=build_guard(store),
    )


def build_token_manager(store: SettingsStore) -> TokenManager:
    return TokenManager(store)
