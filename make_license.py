#!/usr/bin/env python3
"""🔑 컷대장 정품 코드 생성기 — 판매자 전용 (v1.49 목록 99).

⚠ 이 파일은 «저장소 루트»에 둔다 (cutdaejang/ 밖). 제품 zip·EXE에는
   절대 들어가지 않는다 — 여기 든 비밀 열쇠가 새면 누구나 코드를 찍는다.
   build_zip.sh는 git archive HEAD:cutdaejang 만 담으므로 자동으로 빠진다.

사용법:
  python make_license.py 2026-12-31              # 그 날짜까지 유효한 코드 1개
  python make_license.py 2026-12-31 --n 20       # 20명분 (각각 다른 코드)
  python make_license.py 2026-12-31 --name 홍길동  # 메모와 함께 (코드엔 영향 없음)
  python make_license.py 평생                      # 영구 코드 (2099-12-31)

코드를 회원에게 주면, 회원이 프로그램 첫 화면 «정품 등록»에 넣어 잠금을 푼다.
"""
import argparse
import secrets
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "cutdaejang"))
from cutdaejang.core import license as lic  # noqa: E402


def _parse_until(s: str) -> str:
    if s in ("평생", "영구", "lifetime", "forever"):
        return "20991231"
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y%m%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y%m%d")
        except ValueError:
            continue
    raise SystemExit(f"날짜 형식을 못 읽었어요: {s!r} (예: 2026-12-31 또는 '평생')")


def main() -> None:
    ap = argparse.ArgumentParser(description="컷대장 정품 코드 생성기 (판매자 전용)")
    ap.add_argument("until", help="유효 마지막 날 (2026-12-31) 또는 '평생'")
    ap.add_argument("--n", type=int, default=1, help="만들 개수 (기본 1)")
    ap.add_argument("--name", default="", help="메모 (누구에게 줬는지 — 코드엔 안 들어감)")
    a = ap.parse_args()

    expiry = _parse_until(a.until)
    exp_iso = f"{expiry[:4]}-{expiry[4:6]}-{expiry[6:]}"
    if datetime.strptime(expiry, "%Y%m%d").date() < date.today():
        print(f"⚠ 주의: {exp_iso}는 오늘보다 과거라, 만든 코드가 바로 만료돼 있어요.")

    print(f"== 정품 코드 {a.n}개 — {exp_iso}까지 유효 "
          f"{'· ' + a.name if a.name else ''} ==")
    for _ in range(max(1, a.n)):
        seed = secrets.token_hex(2).upper()          # 4자 — 코드마다 유일
        code = lic.make_code(expiry, seed)
        # 되읽어 검증까지 (판매자가 잘못된 코드를 주는 사고 방지)
        assert lic.verify_code(code)["valid"], "생성 코드 자체 검증 실패"
        print(code)


if __name__ == "__main__":
    main()
