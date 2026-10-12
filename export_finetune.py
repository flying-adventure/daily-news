#!/usr/bin/env python3
"""ratings.jsonl → 파인튜닝 학습 데이터로 변환.

텔레그램 👍👎 라벨을 MLX LoRA instruction 형식으로 export:
{"prompt": "이 기사에 관심이 있을까? 제목: X", "completion": "관심"/"관심없음"}

사용:
  python3 export_finetune.py           # 본인(기본) 데이터로 export
  python3 export_finetune.py <chat_id> # 특정 구독자 데이터로 export

100건 이상 모이면: mlx_lm.lora --model <qwen-4b> --train --data <이 파일이 있는 디렉터리>
"""

import json
import sys
from pathlib import Path

RATINGS = Path(__file__).parent / "ratings.jsonl"
OUT = Path(__file__).parent / "finetune-data.jsonl"


def main():
    import digest

    env = digest.load_env()
    own = int(env["TELEGRAM_CHAT_ID"])  # 기본은 본인 데이터만 — 남의 취향 안 섞임
    chat = int(sys.argv[1]) if len(sys.argv) > 1 else own
    rows = []
    for line in RATINGS.read_text().splitlines():
        e = json.loads(line)
        if e.get("label") not in ("good", "bad") or not e.get("title"):
            continue
        # chat 필드 없는 예전 기록은 본인 것으로 간주
        if (e.get("chat") or own) != chat:
            continue
        rows.append(
            {
                "prompt": f"이 뉴스 기사에 관심이 있을까? 제목: {e['title']}",
                "completion": "관심" if e["label"] == "good" else "관심없음",
            }
        )
    OUT.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")
    print(f"{len(rows)}건 → {OUT}")
    if len(rows) < 100:
        print("데이터가 적습니다 — 100건 이상 모이면 학습하세요.")
    else:
        print("학습: mlx_lm.lora --model <qwen-4b> --train --data <디렉터리>")


if __name__ == "__main__":
    main()
