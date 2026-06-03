"""
_test_shorts.py — 쇼츠 제작 엔진 검증 (ffmpeg + espeak 필요, display 불필요).
템플릿 렌더 / 나래이션(TTS) / 배경음악 믹스 / 최종 9:16 MP4 를 실제로 만들어 ffprobe로 확인.
"""
import sys, json, subprocess, traceback
from pathlib import Path
from PIL import Image

OUT = Path("_test_out"); OUT.mkdir(exist_ok=True)
ASSET = Path("_test_assets"); ASSET.mkdir(exist_ok=True)

# 테스트 사진 3장 (가로/세로 다양)
imgs = []
for i, (w, h, c) in enumerate([(800, 600, "#cc4444"), (600, 900, "#4444cc"), (1000, 500, "#44aa44")]):
    p = ASSET / f"s{i}.png"; Image.new("RGB", (w, h), c).save(p); imgs.append(str(p))

# 배경음악 stand-in (10초)
bgm = ASSET / "bgm.mp3"
subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=330:duration=10",
                str(bgm)], capture_output=True)

def probe(path):
    r = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json",
                        "-show_streams", "-show_format", str(path)], capture_output=True)
    return json.loads(r.stdout.decode())

def vstream(path):
    return [s for s in probe(path)["streams"] if s.get("codec_type") == "video"][0]
def has_audio(path):
    return any(s.get("codec_type") == "audio" for s in probe(path)["streams"])

results = []
def check(name, fn):
    try:
        fn(); results.append((name, True)); print(f"  ✅ {name}")
    except Exception as e:
        results.append((name, False)); print(f"  ❌ {name}: {e}"); traceback.print_exc()

import shorts_maker as sm

def t_templates():
    for tpl in ("blur", "fill", "card"):
        seg = sm.ShortsSegment(image_path=imgs[0], caption="테스트 자막", template=tpl)
        frame = sm.render_segment_frame(seg)
        assert frame.size == (1080, 1920), f"{tpl} 크기 {frame.size}"
        frame.close()
check("템플릿 3종 렌더 (모두 1080×1920)", t_templates)

def t_narration():
    out = str(OUT / "narr.wav")
    r = sm.generate_narration("안녕하세요 쇼츠 제작기입니다", out)
    assert r and Path(r).exists() and Path(r).stat().st_size > 0, "TTS wav 생성 실패"
    print(f"       나래이션 길이: {sm._audio_duration(r):.2f}초")
check("나래이션 TTS (글 → 음성)", t_narration)

def t_build_full():
    proj = sm.ShortsProject()
    proj.segments = [
        sm.ShortsSegment(image_path=imgs[0], duration=2.0, caption="첫 장면",
                         narration="첫 번째 장면입니다", template="blur"),
        sm.ShortsSegment(image_path=imgs[1], duration=2.0, caption="두 번째",
                         narration="", template="card"),
        sm.ShortsSegment(image_path=imgs[2], duration=2.0, caption="마지막 장면",
                         narration="마지막 장면 나래이션 테스트", template="fill"),
    ]
    proj.bgm_path = str(bgm)
    proj.bgm_volume = 0.2
    proj.output_path = str(OUT / "myshorts.mp4")
    r = sm.build_shorts(proj)
    assert r and Path(r).exists() and Path(r).stat().st_size > 0, "쇼츠 빌드 실패"
    v = vstream(r)
    assert int(v["width"]) == 1080 and int(v["height"]) == 1920, f"해상도 {v['width']}x{v['height']}"
    assert has_audio(r), "오디오(나래이션+BGM) 누락"
    dur = float(probe(r)["format"]["duration"])
    assert dur >= 6.0, f"전체 길이 {dur:.1f}s (3장×2초=6초 이상이어야)"
    print(f"       완성: 1080x1920, {dur:.1f}초, 오디오 포함, {Path(r).stat().st_size//1024}KB")
check("전체 빌드 (사진3 + 자막 + 나래이션 + BGM → 9:16 MP4)", t_build_full)

def t_build_no_audio():
    """나래이션·BGM 없이도 빌드돼야 함"""
    proj = sm.ShortsProject()
    proj.segments = [sm.ShortsSegment(image_path=imgs[0], duration=1.5, caption="조용한 쇼츠", template="blur")]
    proj.output_path = str(OUT / "silent.mp4")
    r = sm.build_shorts(proj)
    assert r and Path(r).exists(), "무음 빌드 실패"
    v = vstream(r)
    assert int(v["height"]) == 1920
check("나래이션·BGM 없이 빌드", t_build_no_audio)

passed = sum(1 for _, ok in results if ok)
print(f"\n{'='*40}\n결과: {passed}/{len(results)} 통과")
sys.exit(0 if passed == len(results) else 1)
