"""Minimal bot integration example.

Run with environment variables:
    SERVER_URL=https://api.license.centumhi.co.kr \
    PRODUCT_CODE=centum-writer \
    PRODUCT_SECRET=... \
    LICENSE_KEY=CW-M30-... \
    python examples/usage.py
"""
import os
import sys

from centumhi_license import LicenseClient


def main() -> int:
    client = LicenseClient(
        product_code=os.environ["PRODUCT_CODE"],
        product_secret=os.environ["PRODUCT_SECRET"],
        server_url=os.environ["SERVER_URL"],
    )

    result = client.verify_or_activate(os.environ["LICENSE_KEY"])
    if not result.valid:
        print(f"라이선스 오류: {result.reason}")
        return 1

    suffix = " (오프라인)" if result.offline else ""
    if result.days_remaining is None:
        print(f"라이선스 정상 (무제한){suffix}")
    else:
        print(f"라이선스 정상, 만료까지 {result.days_remaining}일 남음{suffix}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
