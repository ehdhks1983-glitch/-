"""v0.57.3 — filter_complex 전달 방식 호환 (최신 ffmpeg의 -filter_complex_script 제거 대응).

BtbN master 빌드(1_설치.bat이 받는 빌드)는 FFmpeg 8.x대라 -filter_complex_script가
제거되어 "Unrecognized option"으로 즉사한다(실사용 리포트). 짧은 그래프는 인라인,
긴 그래프만 파일 경유하되 빌드가 지원하는 옵션을 도움말에서 감지해 고른다.
"""
import os
import stat
import subprocess

import pytest

from cutdaejang.utils import ffmpeg as ff


@pytest.fixture(autouse=True)
def _clear_cache():
    ff._FILTER_SCRIPT_OPT.clear()
    yield
    ff._FILTER_SCRIPT_OPT.clear()


def _fake_ffmpeg(tmp_path, name, help_text):
    """-h full 요청에 help_text를 내놓는 가짜 ffmpeg 실행 파일."""
    if os.name == "nt":
        p = tmp_path / f"{name}.bat"
        p.write_text(f"@echo off\r\necho {help_text}\r\n", encoding="utf-8")
    else:
        p = tmp_path / name
        p.write_text("#!/bin/sh\necho '" + help_text + "'\n", encoding="utf-8")
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return str(p)


def test_short_graph_stays_inline(tmp_path):
    args = ff.filter_complex_args("[0:v]null[v]", tmp_path / "f.txt")
    assert args == ["-filter_complex", "[0:v]null[v]"]
    assert not (tmp_path / "f.txt").exists()  # 파일도 만들지 않는다


def test_long_graph_legacy_build_uses_script_option(tmp_path, monkeypatch):
    """도움말에 filter_complex_script가 있는 빌드(≤7.x) → 구형 옵션."""
    fake = _fake_ffmpeg(tmp_path, "ffold", "-filter_complex_script filename  read graph")
    monkeypatch.setenv("CUTDAEJANG_FFMPEG", fake)
    graph = "x" * (ff._FILTER_INLINE_MAX + 1)
    args = ff.filter_complex_args(graph, tmp_path / "g.txt")
    assert args == ["-filter_complex_script", str(tmp_path / "g.txt")]
    assert (tmp_path / "g.txt").read_text(encoding="utf-8") == graph


def test_long_graph_new_build_uses_slash_option(tmp_path, monkeypatch):
    """도움말에 구형 옵션이 없는 빌드(2025+ master, 옵션 제거됨) → -/filter_complex."""
    fake = _fake_ffmpeg(tmp_path, "ffnew", "-/filter_complex filename  load from file")
    monkeypatch.setenv("CUTDAEJANG_FFMPEG", fake)
    graph = "y" * (ff._FILTER_INLINE_MAX + 1)
    args = ff.filter_complex_args(graph, tmp_path / "g.txt")
    assert args == ["-/filter_complex", str(tmp_path / "g.txt")]


def test_detection_failure_falls_back_to_legacy(tmp_path, monkeypatch):
    """도움말 실행이 실패해도 죽지 않고 구형 옵션으로 (십수 년 지원돼 온 쪽)."""
    p = tmp_path / ("ffbroken.bat" if os.name == "nt" else "ffbroken")
    if os.name == "nt":
        p.write_text("@echo off\r\nexit /b 1\r\n", encoding="utf-8")
    else:
        p.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")  # 출력 없이 실패
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
    assert ff._filter_script_opt(str(p)) == "-filter_complex_script"


def test_detection_cached_per_binary(tmp_path):
    fake_old = _fake_ffmpeg(tmp_path, "ffa", "-filter_complex_script filename")
    fake_new = _fake_ffmpeg(tmp_path, "ffb", "no such option here")
    assert ff._filter_script_opt(fake_old) == "-filter_complex_script"
    assert ff._filter_script_opt(fake_new) == "-/filter_complex"
    os.remove(fake_old)  # 캐시됐다면 재실행 없이 같은 답
    assert ff._filter_script_opt(fake_old) == "-filter_complex_script"


def test_scene_slideshow_script_path_renders(tmp_path, monkeypatch):
    """파일 경유 경로 실렌더 — 시스템 ffmpeg가 지원하는 옵션으로 진짜 영상이 나와야 한다."""
    from cutdaejang.core import background_generator as bg
    from cutdaejang.spec import Canvas

    imgs = []
    for i, c in enumerate(("red", "lime")):
        p = tmp_path / f"s{i}.png"
        ff.run([ff.ffmpeg_bin(), "-y", "-v", "error", "-f", "lavfi",
                "-i", f"color=c={c}:s=160x284:d=0.1", "-frames:v", "1", str(p)])
        imgs.append(str(p))
    monkeypatch.setattr(ff, "_FILTER_INLINE_MAX", 10)  # 강제로 파일 경유
    out = bg.scene_slideshow([(p, 500_000) for p in imgs],
                             str(tmp_path / "out.mp4"), Canvas(w=160, h=284, fps=24))
    assert (tmp_path / "out.filter.txt").exists()
    dur = ff.probe_duration_us(out)
    assert 800_000 < dur < 1_400_000  # 2장 × 0.5초
