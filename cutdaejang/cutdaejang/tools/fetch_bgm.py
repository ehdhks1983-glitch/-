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
    # ── v1.12 확장: 분위기를 세분화해 고르기 쉽게 (전부 같은 CC BY 라이브러리) ──
    ("코믹", "Pixel Peeker Polka - faster"),  # 빠른 폴카 — 몰아치는 편집
    ("코믹", "Scheming Weasel faster"),       # 장난·음모 (예능 자막 단골)
    ("코믹", "Rock the Fireplace"),           # 통통 튀는 코믹 록
    ("예능", "Bumbly March"),                 # 어영부영·귀여운 실패
    ("예능", "Comic Plodding"),               # 느긋한 코믹
    ("예능", "Marty Gots a Plan"),            # 리듬감 있는 진행
    ("브이로그", "Cheery Monday"),            # 월요일 아침 같은 산뜻함
    ("브이로그", "Sunday Plans"),             # 주말 브이로그
    ("브이로그", "Blippy Trance"),            # 담백한 반복 — 작업 영상
    ("브이로그", "Odyssey"),                  # 여행·이동
    ("신나는", "Airport Lounge"),             # 라운지 그루브
    ("신나는", "Bounce"),                     # 튀는 리듬
    ("신나는", "Funkorama"),                  # 펑키한 소개
    ("신나는", "Groove Grove"),               # 밝은 그루브
    ("잔잔", "Peaceful Desolation"),          # 고요·여백
    ("잔잔", "Piano Sonata No 15 in D major"),   # 피아노 잔잔
    ("잔잔", "Almost in F - Tranquillity"),   # 차분한 배경
    ("잔잔", "Waterford"),                    # 물결처럼 잔잔
    ("감동", "Touching Moment"),              # 뭉클한 마무리
    ("감동", "Heartwarming"),                 # 따뜻한 회상
    ("감동", "Reverie (small theme)"),        # 서정적 회고
    ("긴장", "Anxiety"),                      # 불안·경고
    ("긴장", "Long Note Two"),                # 서서히 조여드는 긴장
    ("긴장", "Redletter"),                    # 사건·긴박
    ("미스터리", "Mysterioso March"),         # 수상한 행진
    ("미스터리", "Enter the Party"),          # 은근한 의문
    ("시네마틱", "Ossuary 6 - Air"),          # 어둡고 웅장
    ("시네마틱", "Ethereal Relaxation"),      # 넓고 서늘한 공간감
    ("시네마틱", "Impact Prelude"),           # 오프닝 임팩트
    ("뉴스·리뷰", "News Theme"),              # 뉴스·브리핑
    ("뉴스·리뷰", "The Descent"),             # 진지한 설명
    ("뉴스·리뷰", "Inspired"),                # 리뷰·소개 표준
    ("로파이", "Lobby Time"),                 # 로파이 힙합 느낌
    ("로파이", "Bass Walker"),                # 걷는 듯한 베이스
    ("로파이", "Backbay Lounge"),             # 재즈 라운지
    ("트렌디", "Hackbeat"),                   # 테크·디지털
    ("트렌디", "Electrodoodle"),              # 밝은 일렉
    ("트렌디", "Itty Bitty 8 Bit"),           # 레트로 게임풍
    ("정보형", "Wholesome"),                  # 담백한 정보 전달
    ("정보형", "Study and Relax"),            # 공부·집중
    # ── v1.23 확장: +28곡 (같은 Kevin MacLeod CC BY 라이브러리) ──
    # 곡 제목이 원저작자 사이트에서 바뀌었으면 그 곡만 건너뛰고 나머지는 정상 —
    # 재실행하면 실패분만 다시 시도하므로 목록이 커져도 안전하다.
    ("코믹", "Hyperfun"),                     # 정신없이 몰아치는 예능
    ("코믹", "Quirky Dog"),                   # 능청스러운 장면
    ("코믹", "Happy Boy Theme"),              # 휘파람 코믹
    ("코믹", "The Show Must Be Go"),          # 서커스식 진행
    ("코믹", "Killing Time"),                 # 뒤뚱뒤뚱 기다림
    ("예능", "The Cannery"),                  # 부산한 작업 몽타주
    ("예능", "Daily Beetle"),                 # 아기자기한 일상 예능
    ("예능", "Beachfront Celebration"),       # 흥겨운 야외
    ("브이로그", "Bicycle"),                  # 자전거 타는 오후
    ("브이로그", "Payday"),                   # 경쾌한 보상
    ("브이로그", "George Street Shuffle"),    # 산책 재즈
    ("브이로그", "Porch Swing Days - faster"),  # 한가한 오후(빠른판)
    ("신나는", "Funk Game Loop"),             # 게임풍 펑크
    ("신나는", "Cut and Run"),                # 스피디한 전개
    ("신나는", "Overworld"),                  # 모험 시작
    ("신나는", "Upbeat Forever"),             # 계속 밝게
    ("잔잔", "Thinking Music"),               # 곰곰이 생각
    ("잔잔", "Wonder Cycle"),                 # 몽글몽글 회상
    ("잔잔", "Open Those Bright Eyes"),       # 맑은 아침
    ("감동", "Tenderness"),                   # 부드러운 감동
    ("감동", "At Rest"),                      # 차분한 여운
    ("긴장", "Volatile Reaction"),            # 사건 전개
    ("긴장", "Crypto"),                       # 서늘한 의심
    ("긴장", "Epic Unease"),                  # 불길한 웅장
    ("시네마틱", "Five Armies"),              # 대규모 전개·웅장
    ("시네마틱", "Darkest Child"),            # 어두운 드라마
    ("시네마틱", "Prelude and Action"),       # 예고편식 오프닝
    ("로파이", "Smooth Lovin"),               # 느긋한 그루브
]

CREDIT_FILE = "음원_크레딧(설명란에_붙여넣기).txt"
# 봇 티 나는 UA는 차단(CloudFlare류 403)당하기 쉽다 — 브라우저형으로 (v1.50 목록 103)
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Referer": "https://incompetech.com/music/royalty-free/",
}
LAST_ERROR = ""       # 마지막 실패 원인 (화면 표시용)
FAIL_WHY: dict = {}   # 곡별 실패 원인 — main()이 채운다


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
    """mp3 한 곡 다운로드. 실패하면 False + LAST_ERROR에 원인을 남긴다."""
    global LAST_ERROR  # noqa: PLW0603 — 실패 원인을 화면까지 전달
    LAST_ERROR = ""
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
    except urllib.error.HTTPError as e:
        LAST_ERROR = f"HTTP {e.code} (사이트가 요청을 거절)"
        return False
    except urllib.error.URLError as e:
        LAST_ERROR = f"연결 실패: {str(getattr(e, 'reason', e))[:80]}"
        return False
    except OSError as e:
        LAST_ERROR = str(e)[:100]
        return False
    if len(data) < 100_000:  # 오류 페이지/빈 응답
        LAST_ERROR = "응답이 음악 파일이 아님 (곡 주소 변경·차단 추정)"
        return False
    dest.write_bytes(data)
    return True


def default_bgm_dir() -> Path:
    from ..config import resources_dir
    return resources_dir() / "bgm"


def main(bgm_dir=None, fetch_fn=fetch) -> tuple:
    """전 곡 다운로드(있는 곡은 건너뜀) + 크레딧 파일 생성. (성공, 실패) 제목 목록 반환."""
    out = Path(bgm_dir) if bgm_dir else default_bgm_dir()
    out.mkdir(parents=True, exist_ok=True)
    FAIL_WHY.clear()
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
            FAIL_WHY[title] = LAST_ERROR or "원인 미상"
            print(f"      [!] 실패({FAIL_WHY[title]}) — 다시 실행하면 이 곡만 재시도: {title}")
    if ok:
        (out / CREDIT_FILE).write_text(credit_text(ok), encoding="utf-8")
    print()
    print(f"완료: {len(ok)}곡 준비 / 실패 {len(fail)}곡")
    if fail:
        # 원저작자 사이트에서 곡 이름이 바뀌거나 잠깐 막히면 그 곡만 실패한다.
        # 나머지는 이미 다 받았으니 그대로 쓰면 되고, 재실행하면 실패분만 다시 시도한다.
        print(f"  못 받은 곡: {', '.join(fail[:8])}{' 외' if len(fail) > 8 else ''}")
        print("  → 인터넷 상태 문제일 수 있어요. 다시 실행하면 이 곡들만 재시도합니다.")
    if ok:
        print(f"크레딧 문구: resources/bgm/{CREDIT_FILE}  ← 영상 설명란에 붙여넣기!")
        print("컷대장 화면을 새로고침(F5)하면 BGM 목록에 나타납니다.")
    return ok, fail


if __name__ == "__main__":
    main()
