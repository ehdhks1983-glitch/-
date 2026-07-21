"""v0.70 — 배포 안정화: outputs 검증(허위성공 방지)·입력 검증·상태 판정."""

import subprocess
import sys

import pytest

from tests.conftest import requires_ffmpeg

CLI = [sys.executable, "-m", "cutdaejang"]


def _run(*args):
    return subprocess.run(CLI + list(args), capture_output=True, text=True, cwd=".")


def test_outputs_rejects_draft():
    """--outputs draft 는 조용히 성공하지 않고 즉시 오류(exit 2)."""
    r = _run("run", "--topic", "x", "--outputs", "draft")
    assert r.returncode == 2 and "mp4" in r.stderr
    r2 = _run("run", "--topic", "x", "--outputs", "mp4,draft")
    assert r2.returncode == 2  # 하나라도 잘못되면 거부


def test_crf_and_target_range():
    assert _run("run", "--topic", "x", "--crf", "99").returncode == 2
    assert _run("run", "--topic", "x", "--crf", "-1").returncode == 2
    assert _run("run", "--topic", "x", "--target-sec", "99999").returncode == 2


@requires_ffmpeg
def test_no_mp4_output_is_not_ok():
    """출력에 mp4가 없으면(빈 outputs) 산출물 없음 → status가 ok가 아니어야 한다."""
    import tempfile

    from cutdaejang.core import orchestrator
    from cutdaejang.core.orchestrator import JobOptions
    from cutdaejang.core.script_generator import StubScript

    with tempfile.TemporaryDirectory() as d:
        res = orchestrator.run_job(
            d, StubScript().generate("정리 습관"),
            opts=JobOptions(tts_chain=["stub"], auto_mode=True, outputs=()))
        assert res.mp4 is None
        assert res.status != "ok"  # 허위 성공 금지 (v0.70 버그 수정)


def test_readme_and_init_are_mp4_only():
    """제품 설명에서 CapCut 자동화 표기가 사라졌는지 (mp4 전용)."""
    import cutdaejang

    # 제품을 'CapCut 자동화'로 홍보하지 않아야 (제거 사실 언급은 허용)
    assert "CapCut 쇼츠" not in (cutdaejang.__doc__ or "")
    assert "CapCut 자동화" not in (cutdaejang.__doc__ or "")
    readme = open("README.md", encoding="utf-8").read()
    assert "CapCut 쇼츠·영상 조립 자동화" not in readme
    assert "--outputs mp4,draft" not in readme  # draft를 지원 기능으로 안내 금지
