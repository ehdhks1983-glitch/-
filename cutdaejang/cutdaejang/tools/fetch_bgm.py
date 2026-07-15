"""무료 BGM 자동 받기 — 전 세계에서 가장 많이 쓰는 무료 음원을 resources/bgm에 채운다.

전부 Kevin MacLeod(incompetech.com)의 CC BY(저작자표시) 곡 — 유튜브 예능·쇼츠에서
수십 년째 쓰이는 국민 BGM들. 영상 설명란에 크레딧 한 줄만 붙이면 상업용(수익화)도
무료다. 크레딧 문구는 함께 생성되는 "음원_크레딧(설명란에_붙여넣기).txt"에서 복사.

주의: 음원 파일을 프로그램 zip에 담아 재배포하는 것은 원저작자 사이트 정책·안전상
하지 않는다 — 각자 PC에서 이 스크립트로 직접 받는 방식(다운로드는 무료·합법).

실행: windows\\6_무료음원_받기.bat  또는  python -m cutdaejang.tools.fetch_bgm
"""

from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

_BASE = "https://incompetech.com/music/royalty-free/mp3-royaltyfree/"

# (분위기 태그, 곡 제목) — 파일명은 "분위기_제목.mp3"로 저장돼 UI 목록에서 바로 구분
TRACKS = [
    ("코믹", "Monkeys Spinning Monkeys"),   # 예능 자막 필수 국민 BGM
    ("코믹", "Fluffing a Duck"),            # 귀엽고 장난스러움
    ("코믹", "Sneaky Snitch"),              # 몰래·장난·수상한 장면
    ("코믹", "Merry Go"),                   # 동글동글 코믹
    ("예능", "Local Forecast - Elevator"),  # 엘리베이터·기다림·티키타카
    ("브이로그", "Carefree"),               # 밝고 여유로운 일상
    ("브이로그", "Life of Riley"),          # 산뜻한 시작
    ("브이로그", "Wallpaper"),              # 가볍고 경쾌
    ("브이로그", "The Builder"),            # 담백한 작업·과정
    ("신나는", "Happy Alley"),              # 통통 튀는 진행
    ("잔잔", "Easy Lemon"),                 # 차분한 배경
    ("미스터리", "Cipher"),                 # 정보·추리·긴장
    ("미스터리", "Investigations"),         # 수사·의문
    ("정보형", "Deliberate Thought"),       # 설명·지식 전달
]

CREDIT_FILE = "음원_크레딧(설명란에_붙여넣기).txt"
_HEADERS = {"User-Agent": "Mozilla/5.0 (cutdaejang bgm fetch)"}


def track_url(title: str) -> str:
    return _BASE + urllib.parse.quote(f"{title}.mp3")


def save_name(mood: str, title: str) -> str:
    return f"{mood}_{title}.mp3"


def credit_text(titles: list) -> str:
    """받은 곡들의 CC BY 크레딧 — 유튜브 설명란에 그대로 붙여넣는 형식."""
    blocks = [
        "■ 아래 문구를 영상 설명란에 붙여넣으세요 (CC BY 저작자표시 — 이거면 상업용도 무료!)",
        "",
    ]
    for t in titles:
        blocks += [
            f'"{t}" Kevin MacLeod (incompetech.com)',
            "Licensed under Creative Commons: By Attribution 4.0 License",
            "http://creativecommons.org/licenses/by/4.0/",
            "",
        ]
    blocks += [
        "※ 여러 곡을 쓴 영상이면 쓴 곡의 문구만 골라 붙이면 됩니다.",
        "※ 크레딧 없이 쓰면 저작권 표시 위반이 될 수 있어요 — 꼭 붙여주세요!",
    ]
    return "\n".join(blocks)


def fetch(url: str, dest: Path, timeout: float = 180.0) -> bool:
    """mp3 한 곡 다운로드. 실패하거나 응답이 비정상(100KB 미만)이면 False."""
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
    except (urllib.error.URLError, OSError):
        return False
    if len(data) < 100_000:  # 오류 페이지/빈 응답
        return False
    dest.write_bytes(data)
    return True


def default_bgm_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "resources" / "bgm"


def main(bgm_dir=None, fetch_fn=fetch) -> tuple:
    """전 곡 다운로드(있는 곡은 건너뜀) + 크레딧 파일 생성. (성공, 실패) 제목 목록 반환."""
    out = Path(bgm_dir) if bgm_dir else default_bgm_dir()
    out.mkdir(parents=True, exist_ok=True)
    ok, fail = [], []
    for i, (mood, title) in enumerate(TRACKS, 1):
        dest = out / save_name(mood, title)
        if dest.is_file() and dest.stat().st_size > 100_000:
            print(f"[{i:2d}/{len(TRACKS)}] 이미 있음 → {dest.name}")
            ok.append(title)
            continue
        print(f"[{i:2d}/{len(TRACKS)}] 받는 중… {dest.name}", flush=True)
        if fetch_fn(track_url(title), dest):
            ok.append(title)
        else:
            fail.append(title)
            print(f"      [!] 실패 — 나중에 다시 실행하면 이 곡만 재시도합니다: {title}")
    if ok:
        (out / CREDIT_FILE).write_text(credit_text(ok), encoding="utf-8")
    print()
    print(f"완료: {len(ok)}곡 준비 / 실패 {len(fail)}곡")
    if ok:
        print(f"크레딧 문구: resources/bgm/{CREDIT_FILE}  ← 영상 설명란에 붙여넣기!")
        print("컷대장 화면을 새로고침(F5)하면 BGM 목록에 나타납니다.")
    return ok, fail


if __name__ == "__main__":
    main()
