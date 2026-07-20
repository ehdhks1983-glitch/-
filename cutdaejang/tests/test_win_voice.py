"""v0.59 — Windows 내장 음성 보이스 선택 (SAPI 스크립트·목록·설정 전달)."""
from cutdaejang.core import tts_engine as te


def test_build_sapi_script_substitutes_and_escapes():
    s = te.build_sapi_script(2, "O'Brien Voice")
    assert "__RATE__" not in s and "__VOICE__" not in s
    assert "$s.Rate = 2" in s
    assert "O''Brien Voice" in s  # PS 문자열 리터럴 이스케이프
    # 지정 보이스 우선 → 없으면 한국어 첫 번째 → 그래도 없으면 exit 3 (기존 동작 유지)
    assert "VoiceInfo.Name -eq $want" in s
    assert "-like 'ko*'" in s and "exit 3" in s


def test_build_sapi_script_empty_voice_keeps_ko_default():
    s = te.build_sapi_script(0, "")
    assert "$want = ''" in s and "$s.Rate = 0" in s


def test_list_windows_voices_empty_on_non_windows():
    assert te.list_windows_voices() == []


def test_windows_tts_cache_extra_reflects_voice_and_rate():
    assert te.WindowsTTS().cache_extra == ""
    assert te.WindowsTTS(rate=2).cache_extra == "rate2"
    assert te.WindowsTTS(voice="Microsoft Heami Desktop").cache_extra == "v:Microsoft Heami Desktop"
    assert te.WindowsTTS(rate=-2, voice="A").cache_extra == "rate-2|v:A"


def test_make_provider_passes_windows_voice():
    settings = {"tts": {"windows_rate": 2, "windows_voice": "Microsoft Heami Desktop"}}
    prov = te.make_provider("windows", settings)
    assert prov.rate == 2
    assert prov.voice == "Microsoft Heami Desktop"
