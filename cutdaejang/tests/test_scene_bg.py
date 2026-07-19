"""v0.45 장면별 AI 이미지 배경 — 대본 장면 프롬프트·이미지 생성·슬라이드·통합."""

import subprocess

import pytest

from cutdaejang.core import background_generator as bg
from cutdaejang.core.script_generator import Script, StubScript
from cutdaejang.spec import Background, Canvas, TimelineSpec
from cutdaejang.utils import ffmpeg as ff
from tests.conftest import requires_ffmpeg

COLORS = ["red", "lime", "blue", "yellow", "magenta", "cyan"]


class FakeImage:
    """장면마다 다른 단색 PNG를 그리는 가짜 Gemini — 프롬프트 기록, 지정 회차 실패."""

    def __init__(self, fail_at=()):
        self.calls, self.fail_at = [], set(fail_at)

    def generate(self, prompt, out_path, canvas):
        i = len(self.calls)
        self.calls.append(prompt)
        if i in self.fail_at:
            raise RuntimeError("일부러 실패")
        ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
                "-i", f"color=c={COLORS[i % 6]}:s={canvas.w}x{canvas.h}:d=0.1",
                "-frames:v", "1", str(out_path)])
        return str(out_path)


def test_script_scene_prompts_roundtrip():
    s = StubScript().generate("정리 습관")
    assert len(s.scene_prompts) == len(s.sentences) and all(s.scene_prompts)
    s2 = Script.from_json_text(s.to_json())
    assert s2.scene_prompts == s.scene_prompts
    # 구버전 JSON(scene 없음)도 길이 정규화로 안전
    old = Script.from_json_text('{"title":"t","sentences":[{"text":"안녕하세요 여러분"}]}')
    assert old.scene_prompts == [""]


def test_fill_scene_gaps():
    imgs = [None, "b.png", None, "d.png"]
    filled = bg.fill_scene_gaps(imgs, base="base.png")
    assert filled == ["b.png", "b.png", "b.png", "d.png"]  # 앞=다음, 중간=직전
    assert bg.fill_scene_gaps([None, None], "base.png") == ["base.png", "base.png"]


def test_background_video_spec_validates(tmp_path):
    p = tmp_path / "slides.mp4"
    p.write_bytes(b"x")
    spec = TimelineSpec(duration_us=1_000_000,
                        background=Background(type="video", path=str(p)))
    spec.validate()  # video 타입 허용 (v0.45)
    assert not spec.missing_files()
    with pytest.raises(Exception, match="path"):
        TimelineSpec(duration_us=1_000_000,
                     background=Background(type="video")).validate()


def test_composer_args_video_background(tmp_path):
    from cutdaejang.core.render_engine.ffmpeg_composer import build_command
    from tests.test_spec import make_valid_spec

    spec = make_valid_spec()
    slides = tmp_path / "slides.mp4"
    slides.write_bytes(b"x")
    spec.background = Background(type="video", path=str(slides))
    args = build_command(spec, str(tmp_path / "v.wav"), str(tmp_path / "s.ass"),
                         str(tmp_path / "o.mp4"), fonts_dir=str(tmp_path))
    joined = " ".join(str(a) for a in args)
    assert str(slides) in joined
    assert "tpad=stop_mode=clone" in joined  # 몇 프레임 모자라도 안전
    assert "zoompan" not in joined           # 이미지 전용 모션은 미적용


@requires_ffmpeg
def test_generate_scene_images_style_and_failures(tmp_path):
    canvas = Canvas(w=180, h=320, fps=30)
    prov = FakeImage(fail_at={1})
    imgs = bg.generate_scene_images(["장면 하나", "장면 둘", "장면 셋"], prov,
                                    tmp_path / "sc", canvas, style="3D")
    assert imgs[0] and imgs[1] is None and imgs[2]
    assert all(p.startswith(bg.IMAGE_STYLES["3D"]) for p in prov.calls)


@requires_ffmpeg
def test_scene_slideshow_duration_size_order(tmp_path):
    canvas = Canvas(w=180, h=320, fps=30)
    prov = FakeImage()
    imgs = bg.generate_scene_images(["1", "2", "3"], prov, tmp_path / "sc", canvas)
    spans = [(imgs[0], 1_200_000), (imgs[1], 900_000), (imgs[2], 1_500_000)]
    out = bg.scene_slideshow(spans, str(tmp_path / "slides.mp4"), canvas)
    assert 3_400_000 <= ff.probe_duration_us(out) <= 3_850_000  # 구간 합 = 3.6s
    assert ff.probe_video_size(out) == (180, 320)

    def rgb(t):
        raw = subprocess.run(
            [ff.ffmpeg_bin(), "-v", "error", "-ss", str(t), "-i", out, "-frames:v", "1",
             "-vf", "scale=1:1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            capture_output=True, check=True).stdout
        return tuple(raw[:3])

    r1, r2, r3 = rgb(0.5), rgb(1.6), rgb(3.0)
    assert r1[0] > 180 and r2[1] > 180 and r3[2] > 180, (r1, r2, r3)  # 빨→초→파 순서


@requires_ffmpeg
def test_run_job_scene_background_integration(tmp_path):
    """스텁 TTS + 가짜 이미지 → spec 배경이 슬라이드 video로, 실패 시 단일 유지."""
    from cutdaejang.core import orchestrator
    from cutdaejang.core.orchestrator import JobOptions

    prov = FakeImage()
    res = orchestrator.run_job(
        tmp_path / "jobs", StubScript().generate("정리 습관"),
        opts=JobOptions(tts_chain=["stub"], auto_mode=True), image_provider=prov)
    assert res.status == "ok", res.errors
    assert res.bg_source == "ai_scenes:4/4"
    spec = TimelineSpec.load(f"{res.job_dir}/spec.json")
    assert spec.background.type == "video"
    assert len(prov.calls) == 5  # 기본 배경 1 + 장면 4

    # 장면이 대부분 실패하면 단일(image) 배경으로 안전하게 유지
    prov2 = FakeImage(fail_at={1, 2, 3})
    res2 = orchestrator.run_job(
        tmp_path / "jobs2", StubScript().generate("실패 테스트"),
        opts=JobOptions(tts_chain=["stub"], auto_mode=True), image_provider=prov2)
    spec2 = TimelineSpec.load(f"{res2.job_dir}/spec.json")
    assert spec2.background.type == "image" and res2.bg_source == "ai"


def test_gemini_image_model_fallback(monkeypatch, tmp_path):
    """v0.46.1 — 설정 모델이 404면 대체 모델로 자동 재시도 + 성공 모델 기억."""
    from cutdaejang.core import background_generator as bgm

    calls = []

    def fake_post(url, payload, headers):
        model = url.split("/models/")[1].split(":")[0]
        calls.append(model)
        if "preview" in model:
            raise RuntimeError("HTTP 404 NOT_FOUND: model not found")
        import base64
        png = (tmp_path / "src.png")
        if not png.exists():
            ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
                    "-i", "color=c=orange:s=90:160:d=0.1".replace(":s=90:160", ":s=90x160"),
                    "-frames:v", "1", str(png)])
        return {"candidates": [{"content": {"parts": [
            {"inlineData": {"data": base64.b64encode(png.read_bytes()).decode()}}]}}]}

    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(bgm, "_http_post_json", fake_post)
    canvas = Canvas(w=90, h=160, fps=30)
    prov = bgm.GeminiImage(model="gemini-2.5-flash-image-preview")  # 옛 설정값 시나리오
    out1 = prov.generate("장면", str(tmp_path / "a.png"), canvas)
    assert out1 and calls == ["gemini-2.5-flash-image-preview", "gemini-2.5-flash-image"]
    prov.generate("장면2", str(tmp_path / "b.png"), canvas)
    assert calls[-1] == "gemini-2.5-flash-image" and len(calls) == 3  # 기억 → 바로 성공 모델

    # 모델 문제가 아닌 오류(한도 등)는 폴백 없이 즉시 전달
    def quota_post(url, payload, headers):
        raise RuntimeError("HTTP 429 RESOURCE_EXHAUSTED: quota")
    monkeypatch.setattr(bgm, "_http_post_json", quota_post)
    prov2 = bgm.GeminiImage(model="gemini-2.5-flash-image")
    with pytest.raises(bgm.BackgroundError, match="429"):
        prov2.generate("장면", str(tmp_path / "c.png"), canvas)


def test_scene_prompt_character_injection():
    """v0.50 — 캐릭터 프리셋 키/직접 묘사가 프롬프트에 주입되는지."""
    t = bg.scene_prompt_text("바다를 바라본다", "일러스트", "해골")
    assert "해골 캐릭터" in t and "같은 모습" in t and "이 캐릭터가 바다를" in t
    t2 = bg.scene_prompt_text("웃는다", "3D", "파란 모자 쓴 문어")
    assert "파란 모자 쓴 문어" in t2
    t3 = bg.scene_prompt_text("장면", "일러스트", "")
    assert "주인공" not in t3  # 캐릭터 없으면 기존 그대로


@requires_ffmpeg
def test_generate_scene_images_uses_ref_for_character(tmp_path):
    """v0.50 — 캐릭터 모드에서 첫 성공작을 참조(ref_png)로 다음 장면에 전달."""
    canvas = Canvas(w=90, h=160, fps=30)

    class RefCapture(FakeImage):
        def __init__(self):
            super().__init__()
            self.refs = []
        def generate(self, prompt, out_path, canvas, ref_png=None):
            self.refs.append(ref_png)
            return super().generate(prompt, out_path, canvas)

    prov = RefCapture()
    bg.generate_scene_images(["a", "b", "c"], prov, tmp_path / "s", canvas,
                             character="해골")
    assert prov.refs[0] is None and prov.refs[1] and prov.refs[2]  # 2번째부터 참조
    prov2 = RefCapture()
    bg.generate_scene_images(["a", "b"], prov2, tmp_path / "s2", canvas, character="")
    assert prov2.refs == [None, None]  # 캐릭터 없으면 참조 안 씀


@requires_ffmpeg
def test_run_job_with_pregenerated_scene_images(tmp_path):
    """v0.50 — 장면 검토에서 확정한 이미지를 run_job에 넘기면 생성 없이 사용."""
    from cutdaejang.core import orchestrator
    from cutdaejang.core.orchestrator import JobOptions

    canvas = Canvas(w=1080, h=1920, fps=30)
    prov = FakeImage()
    imgs = [prov.generate(f"장면{i}", str(tmp_path / f"pre_{i}.png"), canvas)
            for i in range(4)]
    counter = FakeImage()  # 렌더 중 추가 생성 호출이 없어야 함 (기본 배경 1장 제외)
    res = orchestrator.run_job(
        tmp_path / "jobs", StubScript().generate("사전 이미지"),
        opts=JobOptions(tts_chain=["stub"], auto_mode=True),
        image_provider=counter, scene_images=imgs)
    assert res.status == "ok", res.errors
    assert res.bg_source == "ai_scenes:4/4"
    assert len(counter.calls) == 1  # prepare_background(기본 배경)만 — 장면 생성 없음
    spec = TimelineSpec.load(f"{res.job_dir}/spec.json")
    assert spec.background.type == "video"
