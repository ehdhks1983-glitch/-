"""
shorts_maker.py — 쇼츠 제작 엔진 (오케스트레이션)
사진 여러 장 + 화면 자막 + 나래이션(TTS) + 배경음악 → 세로 9:16 MP4

구조(템플릿) 3종:
  - blur : 흐림 배경 + 사진 가운데 맞춤 (자막 하단)
  - fill : 사진을 9:16로 꽉 채움(크롭) (자막 하단)
  - card : 카드뉴스 스타일 — 흰 배경, 상단 큰 제목(자막) + 사진 아래

엔진은 역할별로 분리되어 있다(부록 A):
  - shorts_common   : 영상 규격(W,H), ffmpeg 실행/탐지 헬퍼
  - shorts_models   : ShortsSegment / ShortsProject
  - shorts_render   : 프레임 렌더(PIL) — render_segment_frame
  - shorts_subtitle : ASS 자막
  - shorts_tts      : 나래이션(TTS) — generate_narration
  - shorts_maker    : build_shorts (이 파일 — 합성 오케스트레이션만)

나래이션은 타이핑한 글을 음성으로 읽어줍니다:
  - ElevenLabs(설정 시) → 윈도우 SAPI / espeak-ng → pyttsx3 폴백
배경음악은 사용자가 고른 음악 파일을 깔아줍니다(저작권 안전).
"""

import os
import tempfile
from typing import List, Optional, Callable
from pathlib import Path

from config import KENBURNS
from utils import find_ffmpeg, generate_output_name, format_filesize
from shorts_common import W, H, _run, _audio_duration, _filter_available
from shorts_models import ShortsSegment, ShortsProject, TEMPLATES
from shorts_render import render_segment_frame, kenburns_vf
from shorts_subtitle import _ass_font, _build_ass_file
from shorts_tts import generate_narration

# 외부에서 `from shorts_maker import ...` 하던 이름들을 그대로 노출(하위호환).
__all__ = [
    "W", "H", "TEMPLATES",
    "ShortsSegment", "ShortsProject",
    "render_segment_frame", "generate_narration", "build_shorts",
]


# ════════════════════════════════════════
# 빌드
# ════════════════════════════════════════
def build_shorts(project: ShortsProject,
                 on_progress: Optional[Callable[[int, str], None]] = None) -> Optional[str]:
    """쇼츠 프로젝트 → 세로 9:16 MP4 (나래이션 + 배경음악 합성)"""
    ff = find_ffmpeg()
    if not ff:
        if on_progress:
            on_progress(0, "❌ FFmpeg를 찾을 수 없습니다")
        return None
    if not project.segments:
        if on_progress:
            on_progress(0, "❌ 장면이 없습니다")
        return None

    def prog(p, m):
        if on_progress:
            on_progress(p, m)

    work = tempfile.mkdtemp(prefix="shorts_")
    try:
        use_ass = _filter_available(ff, "subtitles")

        # ── 켄번스(줌/팬 모션) 준비 — 1-1 ──
        kb = KENBURNS
        kb_on = bool(getattr(project, "kenburns_enabled", True))
        # 워터마크는 1.15배 줌에 화면 밖으로 잘려나가므로, 켄번스 on일 때는 프레임에
        #   박지 않고 최종 합치기 단계에서 ffmpeg로 영상에 입힌다.
        try:
            import watermark as _wm
            wm_active = bool(_wm.watermark.active)
        except Exception:
            _wm = None
            wm_active = False
        wm_via_ffmpeg = kb_on and wm_active
        bake_wm = not wm_via_ffmpeg   # 켄번스+워터마크일 때만 프레임에 안 박음
        # 일부 ffmpeg 빌드는 drawtext(libfreetype)가 없음 → 있을 때만 텍스트 워터마크 사용
        wm_has_drawtext = _filter_available(ff, "drawtext") if wm_via_ffmpeg else False

        ass_events = []   # (start, end, caption)
        cur_t = 0.0
        seg_clips: List[str] = []
        seg_audios: List[str] = []
        total = len(project.segments)

        for i, seg in enumerate(project.segments):
            if project.cancelled:
                return None
            base_pct = int((i / total) * 60)
            prog(base_pct + 3, f"장면 {i + 1}/{total} 만드는 중...")

            # 1) 나래이션 먼저 생성(있으면) → 길이에 맞춰 노출시간 결정
            narr_wav = None
            narr_dur = 0.0
            if seg.narration.strip():
                nw = os.path.join(work, f"narr{i}.wav")
                narr_wav = generate_narration(seg.narration, nw)
                if narr_wav:
                    narr_dur = _audio_duration(narr_wav)

            eff_dur = max(float(seg.duration), narr_dur + 0.4, 1.0)
            if seg.caption.strip():
                ass_events.append((cur_t, cur_t + eff_dur, seg.caption.strip()))
            cur_t += eff_dur

            # 2) 프레임 렌더 → PNG (ASS 쓰면 자막은 마지막에, 켄번스면 워터마크도 마지막에 입힘)
            frame = render_segment_frame(seg, project.caption_size, project.caption_color,
                                         with_caption=not use_ass, with_watermark=bake_wm)
            png = os.path.join(work, f"f{i}.png")
            frame.save(png)
            frame.close()

            # 3) 무음 비디오 클립 (켄번스 on이면 zoompan 모션, off면 기존 scale 그대로)
            clip = os.path.join(work, f"c{i}.mp4")
            clip_cmd = [ff, "-y", "-loop", "1", "-i", png, "-t", f"{eff_dur:.3f}",
                        "-r", str(project.fps), "-c:v", "libx264", "-pix_fmt", "yuv420p"]
            if kb_on:
                clip_cmd += ["-vf", kenburns_vf(project.fps, eff_dur, kb.get("direction", "in"),
                                                kb.get("max_zoom", 1.15), kb.get("zoom_step", 0.0008),
                                                kb.get("prescale", 2)),
                             "-crf", str(int(kb.get("crf", 20)))]
            else:
                clip_cmd += ["-vf", f"scale={W}:{H}"]
            clip_cmd += ["-preset", "veryfast", clip]
            r = _run(clip_cmd, timeout=300)
            if not Path(clip).exists():
                err = r.stderr.decode("utf-8", "replace")[-200:]
                prog(0, f"❌ 장면 {i+1} 클립 실패: {err.strip()}")
                return None
            seg_clips.append(clip)

            # 4) 세그먼트 오디오: 나래이션을 eff_dur 길이로 (없으면 무음)
            seg_audio = os.path.join(work, f"a{i}.wav")
            if narr_wav:
                _run([ff, "-y", "-i", narr_wav, "-af",
                      f"apad,atrim=0:{eff_dur:.3f},aformat=sample_rates=44100:channel_layouts=stereo",
                      seg_audio], timeout=120)
            if not Path(seg_audio).exists():
                _run([ff, "-y", "-f", "lavfi", "-i",
                      "anullsrc=r=44100:cl=stereo", "-t", f"{eff_dur:.3f}", seg_audio], timeout=60)
            seg_audios.append(seg_audio)

        # 5) 비디오 이어붙이기
        prog(65, "장면 이어붙이는 중...")
        vlist = os.path.join(work, "vlist.txt")
        Path(vlist).write_text("".join(f"file '{c}'\n" for c in seg_clips), encoding="utf-8")
        video_only = os.path.join(work, "video.mp4")
        _run([ff, "-y", "-f", "concat", "-safe", "0", "-i", vlist,
              "-c", "copy", video_only], timeout=300)
        if not Path(video_only).exists():
            # copy 실패 시 재인코딩 폴백
            _run([ff, "-y", "-f", "concat", "-safe", "0", "-i", vlist,
                  "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
                  video_only], timeout=600)
        if not Path(video_only).exists():
            prog(0, "❌ 영상 이어붙이기 실패")
            return None

        # 6) 나래이션 트랙 이어붙이기
        prog(75, "나래이션 합치는 중...")
        alist = os.path.join(work, "alist.txt")
        Path(alist).write_text("".join(f"file '{a}'\n" for a in seg_audios), encoding="utf-8")
        narration_track = os.path.join(work, "narration.wav")
        _run([ff, "-y", "-f", "concat", "-safe", "0", "-i", alist,
              "-c", "copy", narration_track], timeout=300)
        if not Path(narration_track).exists():
            _run([ff, "-y", "-f", "concat", "-safe", "0", "-i", alist, narration_track], timeout=300)

        total_dur = _audio_duration(narration_track)

        # 7) 배경음악 믹스 — 페이드 + 더킹(음성 위로 음악 자동 낮춤)
        prog(85, "배경음악 합치는 중..." if project.bgm_path else "오디오 마무리...")
        final_audio = os.path.join(work, "final.m4a")
        bgm = project.bgm_path
        if bgm and Path(bgm).exists():
            vol = max(0.0, min(1.0, project.bgm_volume))
            f_bgm = max(0.1, total_dur - 1.4)   # 배경음악 페이드아웃 시작
            f_all = max(0.1, total_dur - 0.5)   # 전체 페이드아웃 시작
            duck = (
                f"[1:a]aformat=sample_rates=44100:channel_layouts=stereo,"
                f"volume={vol:.3f},afade=t=in:st=0:d=0.8,afade=t=out:st={f_bgm:.2f}:d=1.4[bg];"
                f"[bg][0:a]sidechaincompress=threshold=0.03:ratio=8:attack=15:release=350[bgd];"
                f"[0:a][bgd]amix=inputs=2:duration=first:normalize=0[mx];"
                f"[mx]afade=t=out:st={f_all:.2f}:d=0.5,alimiter=limit=0.95[a]"
            )
            _run([ff, "-y", "-i", narration_track, "-stream_loop", "-1", "-i", bgm,
                  "-filter_complex", duck, "-map", "[a]", "-t", f"{total_dur:.3f}",
                  "-c:a", "aac", "-b:a", "192k", final_audio], timeout=300)
            if not Path(final_audio).exists():   # 더킹 실패 시 단순 믹스로 폴백
                _run([ff, "-y", "-i", narration_track, "-stream_loop", "-1", "-i", bgm,
                      "-filter_complex",
                      f"[1:a]aformat=sample_rates=44100:channel_layouts=stereo,volume={vol:.3f}[bg];"
                      f"[0:a][bg]amix=inputs=2:duration=first:normalize=0[a]",
                      "-map", "[a]", "-t", f"{total_dur:.3f}",
                      "-c:a", "aac", "-b:a", "192k", final_audio], timeout=300)
        if not Path(final_audio).exists():   # 최종 폴백: 나래이션만
            _run([ff, "-y", "-i", narration_track, "-c:a", "aac", "-b:a", "192k",
                  final_audio], timeout=120)

        # 8) 영상 + 오디오 합치기 (+ ASS 전문 자막, 켄번스면 워터마크도 여기서 입힘)
        prog(93, "최종 합치는 중...")
        if not project.output_path:
            project.output_path = generate_output_name("shorts", "mp4")
        ass_path = None
        if use_ass and ass_events:
            ass_path = os.path.join(work, "captions.ass")
            _build_ass_file(ass_events, ass_path, _ass_font(), project.caption_size)
        has_ass = bool(ass_path and Path(ass_path).exists())

        if wm_via_ffmpeg:
            # 켄번스 모드: 프레임에 안 박은 워터마크를 영상에 입힌다.
            #   텍스트=drawtext, 로고=overlay(추가 입력). 자막이 있으면 같은 체인에 합침.
            vparts = []
            if has_ass:
                vparts.append("subtitles=captions.ass")
            dt = _wm.drawtext_filter(H) if wm_has_drawtext else ""
            if dt:
                vparts.append(dt)
            logo = _wm.video_logo_path()
            inputs = ["-i", "video.mp4", "-i", "final.m4a"]
            if logo:
                base_chain = "[0:v]" + (",".join(vparts) if vparts else "null") + "[base]"
                filter_complex = base_chain + ";" + _wm.video_logo_overlay(W, "[2:v]", "[base]", "[v]")
                inputs += ["-i", logo]
            else:
                filter_complex = "[0:v]" + (",".join(vparts) if vparts else "null") + "[v]"
            _run([ff, "-y", *inputs,
                  "-filter_complex", filter_complex, "-map", "[v]", "-map", "1:a",
                  "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", str(int(kb.get("crf", 20))),
                  "-preset", "veryfast", "-c:a", "aac", "-shortest", "-movflags", "+faststart",
                  project.output_path], timeout=600, cwd=work)
        elif has_ass:
            # 작업폴더 기준 상대경로로 호출(윈도우 경로 이스케이프 회피)
            _run([ff, "-y", "-i", "video.mp4", "-i", "final.m4a",
                  "-filter_complex", "[0:v]subtitles=captions.ass[v]",
                  "-map", "[v]", "-map", "1:a",
                  "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "veryfast",
                  "-c:a", "aac", "-shortest", "-movflags", "+faststart",
                  project.output_path], timeout=600, cwd=work)
        if not Path(project.output_path).exists() and wm_via_ffmpeg and has_ass:
            # 워터마크 합성이 실패해도 최소한 자막은 살린다(자막만 번인)
            _run([ff, "-y", "-i", "video.mp4", "-i", "final.m4a",
                  "-filter_complex", "[0:v]subtitles=captions.ass[v]",
                  "-map", "[v]", "-map", "1:a",
                  "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "veryfast",
                  "-c:a", "aac", "-shortest", "-movflags", "+faststart",
                  project.output_path], timeout=600, cwd=work)
        if not Path(project.output_path).exists():
            # 폴백: 자막 번인 없이 합치기
            _run([ff, "-y", "-i", video_only, "-i", final_audio,
                  "-c:v", "copy", "-c:a", "aac", "-shortest",
                  "-movflags", "+faststart", project.output_path], timeout=300)
        if not Path(project.output_path).exists():
            prog(0, "❌ 최종 합치기 실패")
            return None

        size = format_filesize(Path(project.output_path).stat().st_size)
        prog(100, f"✅ 쇼츠 완성! {size}")
        return project.output_path

    finally:
        try:
            import shutil
            shutil.rmtree(work, ignore_errors=True)
        except Exception:
            pass
