"""Stage 1 - skeleton: paths, config, settings store, logging."""

from __future__ import annotations

import json
import logging

import config
import paths
from core.logging_setup import add_ui_handler, get_logger, remove_handler, setup_logging
from core.settings_store import DEFAULT_SETTINGS, SECRET_KEYS, SettingsStore, mask_secret


# --------------------------------------------------------------------------- #
# paths
# --------------------------------------------------------------------------- #
def test_not_frozen_by_default():
    assert paths.is_frozen() is False
    assert paths.BASE_DIR.name == "instagram_auto_bot"


def test_appdata_override(tmp_home):
    assert paths.appdata_dir() == tmp_home
    assert paths.logs_dir() == tmp_home / "logs"
    assert paths.settings_file() == tmp_home / "settings.json"


def test_ensure_dirs_creates(tmp_home):
    assert not tmp_home.exists()
    paths.ensure_dirs()
    assert tmp_home.is_dir()
    assert (tmp_home / "logs").is_dir()


def test_resource_path_under_base():
    rp = paths.resource_path("skills", "skill.md")
    assert rp.name == "skill.md"
    assert "skills" in rp.parts


# --------------------------------------------------------------------------- #
# config
# --------------------------------------------------------------------------- #
def test_config_invariants():
    # Instagram hashtag count must sit inside the allowed band.
    assert config.IG_HASHTAG_MIN <= config.IG_HASHTAG_COUNT <= config.IG_HASHTAG_MAX
    # Banned words include the three explicit medical-authority terms.
    for w in ("의사", "병원", "전문의"):
        assert w in config.BANNED_WORDS
        assert w in config.BANNED_WORDS_EXTENDED
    # Conservative daily cap is well below the API hard cap.
    assert 1 <= config.MAX_POSTS_PER_DAY <= config.API_DAILY_HARD_CAP
    # Ratios are strings of the expected form.
    assert config.FEED_RATIO in ("4:5", "1:1")
    assert config.REELS_RATIO == "9:16"
    assert config.CAPTION_HOOK_LEN < config.CAPTION_MAX_LEN


def test_graph_url_is_versioned():
    url = config.graph_url("17841400000000000", "media")
    assert url == (
        f"{config.GRAPH_BASE_URL}/{config.GRAPH_API_VERSION}/17841400000000000/media"
    )
    assert config.graph_url().endswith(config.GRAPH_API_VERSION)


# --------------------------------------------------------------------------- #
# settings store
# --------------------------------------------------------------------------- #
def test_defaults_all_secrets_blank(tmp_home):
    store = SettingsStore().load()
    for key in SECRET_KEYS:
        assert store.get_str(key) == "", f"secret {key} must default blank"
    # Provider defaults mirror config.
    assert store.get("text_provider") == config.TEXT_PROVIDER
    assert store.get_int("hashtag_count") == config.IG_HASHTAG_COUNT


def test_round_trip_persist_and_reload(tmp_home):
    store = SettingsStore().load()
    store.set("ig_access_token", "SECRET123456")
    store.set("brand_name", "한글브랜드")
    store.save()

    # Raw file is UTF-8 and contains the unescaped Korean.
    raw = paths.settings_file().read_text(encoding="utf-8")
    assert "한글브랜드" in raw
    assert json.loads(raw)["ig_access_token"] == "SECRET123456"

    reloaded = SettingsStore().load()
    assert reloaded.get_str("ig_access_token") == "SECRET123456"
    assert reloaded.get_str("brand_name") == "한글브랜드"


def test_corrupt_file_falls_back_to_defaults(tmp_home):
    paths.ensure_dirs()
    paths.settings_file().write_text("{not valid json", encoding="utf-8")
    store = SettingsStore().load()
    assert store.get("text_provider") == config.TEXT_PROVIDER  # defaults restored


def test_missing_key_gets_default_after_upgrade(tmp_home):
    paths.ensure_dirs()
    # Simulate an old file lacking newer keys.
    paths.settings_file().write_text(json.dumps({"brand_name": "X"}), encoding="utf-8")
    store = SettingsStore().load()
    assert store.get_str("brand_name") == "X"
    # A key absent from the old file still resolves to its default.
    assert store.get("max_posts_per_day") == DEFAULT_SETTINGS["max_posts_per_day"]


def test_mask_secret_and_redaction(tmp_home):
    assert mask_secret("ABCDEFGH") == "ABCD****"
    assert mask_secret("ab") == "**"
    assert mask_secret("") == ""

    store = SettingsStore().load()
    store.set("openai_api_key", "sk-livesecretvalue")
    redacted = store.as_dict(redact_secrets=True)
    assert redacted["openai_api_key"].startswith("sk-l")
    assert "secretvalue" not in redacted["openai_api_key"]


def test_is_configured_for_publish(tmp_home):
    store = SettingsStore().load()
    assert store.is_configured_for_publish() is False
    store.set("ig_access_token", "t")
    store.set("ig_user_id", "123")
    assert store.is_configured_for_publish() is True


# --------------------------------------------------------------------------- #
# logging
# --------------------------------------------------------------------------- #
def test_logging_writes_dated_file_and_ui_callback(tmp_home):
    log = setup_logging()
    captured: list[str] = []
    handler = add_ui_handler(captured.append, level=logging.INFO)
    try:
        get_logger("test").error("의도적 에러 메시지")  # intentional error line
        for h in log.handlers:
            h.flush()
    finally:
        remove_handler(handler)

    # The UI callback received the line.
    assert any("의도적 에러 메시지" in line for line in captured)

    # A dated log file exists and contains the message.
    log_files = list(paths.logs_dir().glob("insta_*.log"))
    assert log_files, "expected a dated log file"
    contents = "\n".join(p.read_text(encoding="utf-8") for p in log_files)
    assert "의도적 에러 메시지" in contents
