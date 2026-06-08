"""
data_snapshot.py - 처리 단계별 데이터 스냅샷 저장
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
도완님 요청: "정보를 일단 최대한 모으자"

각 상품 처리 단계마다 JSON 파일로 저장.
나중에 어디서 꺾였는지 즉시 추적 가능.

저장 경로: snapshots/{item_no}/{stage}_{timestamp}.json
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from config import SNAPSHOTS_DIR
    from logger import log
except ImportError:
    SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"
    SNAPSHOTS_DIR.mkdir(exist_ok=True)
    import logging
    log = logging.getLogger(__name__)


class SnapshotWriter:
    """
    단일 상품 처리에 대한 스냅샷 컬렉션.

    사용:
        snap = SnapshotWriter("7914900")
        snap.save("01_domeggook_raw", raw_xml_data)
        snap.save("02_domeggook_parsed", parsed_dict)
        snap.save("03_pricing_calc", pricing_result)
        snap.save("04_category_match", {"input": name, "output": cat_id})
        snap.save("05_image_pipeline", image_results)
        snap.save("06_coupang_payload", payload_dict)
        snap.save("07_coupang_response", response_dict)
        snap.finalize()  # 전체 요약 JSON 생성
    """

    def __init__(self, item_no: str):
        self.item_no = str(item_no)
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.dir = SNAPSHOTS_DIR / f"{self.item_no}_{self.timestamp}"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.saved_stages = []
        log.info(f"[SNAPSHOT] 디렉토리 생성: {self.dir}")

    def save(self, stage: str, data: Any, file_ext: str = "json") -> Path:
        """스냅샷 1개 저장"""
        safe_stage = stage.replace("/", "_").replace(" ", "_")
        path = self.dir / f"{safe_stage}.{file_ext}"

        try:
            if file_ext == "json":
                path.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8"
                )
            elif file_ext == "xml":
                path.write_text(str(data), encoding="utf-8")
            elif file_ext == "html":
                path.write_text(str(data), encoding="utf-8")
            else:
                path.write_text(str(data), encoding="utf-8")

            self.saved_stages.append({
                "stage": stage,
                "path": str(path.relative_to(SNAPSHOTS_DIR.parent)),
                "size_bytes": path.stat().st_size,
                "saved_at": datetime.now().isoformat(),
            })
            log.info(f"[SNAPSHOT] {stage} 저장 ({path.stat().st_size:,}B)")
        except Exception as e:
            log.error(f"[SNAPSHOT] {stage} 저장 실패: {e}")

        return path

    def save_binary(self, stage: str, data: bytes, ext: str = "bin") -> Path:
        """바이너리 데이터 (예: 이미지) 저장"""
        safe_stage = stage.replace("/", "_").replace(" ", "_")
        path = self.dir / f"{safe_stage}.{ext}"
        try:
            path.write_bytes(data)
            self.saved_stages.append({
                "stage": stage,
                "path": str(path.relative_to(SNAPSHOTS_DIR.parent)),
                "size_bytes": path.stat().st_size,
                "saved_at": datetime.now().isoformat(),
            })
        except Exception as e:
            log.error(f"[SNAPSHOT] 바이너리 저장 실패: {e}")
        return path

    def finalize(self, status: str = "completed", summary: dict = None):
        """
        _summary.json 파일 생성.
        처리 전체 요약 + 각 단계별 파일 경로.
        """
        summary_data = {
            "item_no": self.item_no,
            "timestamp": self.timestamp,
            "status": status,
            "stages": self.saved_stages,
            "stage_count": len(self.saved_stages),
            "total_bytes": sum(s.get("size_bytes", 0) for s in self.saved_stages),
            "summary": summary or {},
            "finalized_at": datetime.now().isoformat(),
        }

        summary_path = self.dir / "_summary.json"
        summary_path.write_text(
            json.dumps(summary_data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        log.info(f"[SNAPSHOT] 요약 저장: {summary_path}")
        log.info(f"[SNAPSHOT] 총 {len(self.saved_stages)}단계 스냅샷, "
                 f"{summary_data['total_bytes']:,}B")
        return summary_path


def load_latest_snapshot(item_no: str, stage: str = None) -> dict:
    """
    특정 상품의 최신 스냅샷 로드 (재시작·디버깅용).

    Args:
        item_no: 도매꾹 상품번호
        stage: 특정 단계명 (없으면 _summary.json 반환)
    """
    # 해당 상품번호의 디렉토리 검색
    matches = sorted(SNAPSHOTS_DIR.glob(f"{item_no}_*"), reverse=True)
    if not matches:
        return {}

    latest_dir = matches[0]
    if stage:
        path = latest_dir / f"{stage}.json"
    else:
        path = latest_dir / "_summary.json"

    if not path.exists():
        return {}

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        log.error(f"[SNAPSHOT] 로드 실패: {e}")
        return {}
