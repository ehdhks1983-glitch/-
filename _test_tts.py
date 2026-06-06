"""
_test_tts.py — 음성 설정 + 배경음악 믹스(페이드/더킹) 검증 (display 불필요)
ElevenLabs 실제 호출은 키/인터넷 필요 → 여기선 폴백·설정·믹스 동작만 확인.
"""
import sys, json, subprocess, traceback
from pathlib import Path

OUT = Path("_test_out"); OUT.mkdir(exist_ok=True)
ASSET = Path("_test_assets"); ASSET.mkdir(exist_ok=True)

results = []
def check(name, fn):
    try:
        fn(); results.append((name, True)); print(f"  ✅ {name}")
    except Exception as e:
        results.append((name, False)); print(f"  ❌ {name}: {e}"); traceback.print_exc()

import tts_engine as te
import shorts_maker as sm

def t_settings():
    # 저장/불러오기 라운드트립 (원복)
    prev = te.tts_settings.get("voice_id")
    te.tts_settings.set("voice_id", "TESTVOICE123")
    assert te.tts_settings.get("voice_id") == "TESTVOICE123"
    te.tts_settings.set("voice_id", prev or "")
    # 키 없으면 use_elevenlabs False
    te.tts_settings.set("use_elevenlabs", True)
    te.tts_settings.set("api_key", ""); te.tts_settings.set("voice_id", "")
    assert te.tts_settings.use_elevenlabs is False, "키 없는데 활성화됨"
    te.tts_settings.set("use_elevenlabs", False)
check("TTS 설정 저장/불러오기 + 활성조건", t_settings)

def t_elevenlabs_nokey():
    assert te.elevenlabs_tts("테스트", str(OUT / "x.mp3")) is None, "키 없는데 None 아님"
check("ElevenLabs 키 없을 때 안전하게 None", t_elevenlabs_nokey)

def t_fallback_narration():
    # EL 미설정 → 시스템 음성 폴백으로 wav 생성 (리눅스=espeak)
    r = sm.generate_narration("안녕하세요 폴백 테스트", str(OUT / "fb.wav"))
    assert r and Path(r).exists() and Path(r).stat().st_size > 0, "폴백 음성 생성 실패"
check("ElevenLabs 미설정 시 시스템 음성 폴백", t_fallback_narration)

def t_duck_mix():
    """새 배경음악 믹스(afade + sidechaincompress + alimiter)가 이 ffmpeg에서 동작하는지"""
    from shorts_maker import find_ffmpeg, _run
    ff = find_ffmpeg()
    narr = ASSET / "narr_t.wav"; bgm = ASSET / "bgm_t.mp3"
    subprocess.run([ff, "-y", "-f", "lavfi", "-i", "sine=frequency=300:duration=4",
                    str(narr)], capture_output=True)
    subprocess.run([ff, "-y", "-f", "lavfi", "-i", "sine=frequency=600:duration=10",
                    str(bgm)], capture_output=True)
    total = 4.0; f_bgm = total - 1.4; f_all = total - 0.5; vol = 0.18
    duck = (f"[1:a]aformat=sample_rates=44100:channel_layouts=stereo,"
            f"volume={vol:.3f},afade=t=in:st=0:d=0.8,afade=t=out:st={f_bgm:.2f}:d=1.4[bg];"
            f"[bg][0:a]sidechaincompress=threshold=0.03:ratio=8:attack=15:release=350[bgd];"
            f"[0:a][bgd]amix=inputs=2:duration=first:normalize=0[mx];"
            f"[mx]afade=t=out:st={f_all:.2f}:d=0.5,alimiter=limit=0.95[a]")
    out = OUT / "duck.m4a"
    _run([ff, "-y", "-i", str(narr), "-stream_loop", "-1", "-i", str(bgm),
          "-filter_complex", duck, "-map", "[a]", "-t", f"{total:.3f}",
          "-c:a", "aac", "-b:a", "192k", str(out)], timeout=120)
    assert out.exists() and out.stat().st_size > 0, "더킹 믹스 실패 (필터 미지원?)"
    # 오디오 스트림 확인
    r = subprocess.run(["ffprobe", "-v", "quiet", "-select_streams", "a",
                        "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(out)],
                       capture_output=True)
    assert b"audio" in r.stdout, "출력에 오디오 없음"
check("배경음악 페이드+더킹 믹스 동작 (sidechaincompress/alimiter)", t_duck_mix)

def t_full_build_with_bgm():
    """전체 쇼츠 빌드가 새 믹스로도 정상 (오디오 포함 1080x1920)"""
    from PIL import Image
    imgs = []
    for i, c in enumerate(["#334", "#433"]):
        p = ASSET / f"tt{i}.png"; Image.new("RGB", (800, 600), c).save(p); imgs.append(str(p))
    bgm = ASSET / "bgm_t.mp3"
    proj = sm.ShortsProject()
    proj.segments = [sm.ShortsSegment(image_path=imgs[0], duration=2, caption="가", narration="첫 장면입니다", template="blur"),
                     sm.ShortsSegment(image_path=imgs[1], duration=2, caption="나", narration="", template="fill")]
    proj.bgm_path = str(bgm); proj.bgm_volume = 0.18
    proj.output_path = str(OUT / "tts_build.mp4")
    r = sm.build_shorts(proj)
    assert r and Path(r).exists(), "빌드 실패"
    info = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json",
                           "-show_streams", str(r)], capture_output=True)
    streams = json.loads(info.stdout)["streams"]
    assert any(s["codec_type"] == "audio" for s in streams), "오디오 없음"
    v = [s for s in streams if s["codec_type"] == "video"][0]
    assert int(v["height"]) == 1920, "세로 아님"
check("전체 쇼츠 빌드 (새 믹스 + BGM)", t_full_build_with_bgm)

passed = sum(1 for _, ok in results if ok)
print(f"\n{'='*40}\n결과: {passed}/{len(results)} 통과")
sys.exit(0 if passed == len(results) else 1)
