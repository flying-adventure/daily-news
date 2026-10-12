#!/usr/bin/env python3
"""상시 폴링 데몬 — 텔레그램 long-polling으로 반응을 거의 즉시 처리.

5분 주기 잡 대신 상시 프로세스로 돌린다. getUpdates timeout=30초라
업데이트가 오면 즉시 처리하고, 없으면 텔레그램 서버가 연결을 들고 대기.
launchd KeepAlive로 등록해 죽어도 자동 재시작.
맥이 잠들면 데몬도 멈춘다 — 깨어나면 다시 붙어서 쌓인 것부터 처리.
"""

import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import digest


def main():
    env = digest.load_env()
    while True:
        try:
            digest.collect_feedback(env, timeout=30)  # long-poll — 오면 즉시 리턴
            digest.dedupe_ratings()
            try:
                digest.publish(env)  # 🔖 저장이 들어왔으면 저장함 페이지 갱신 (안 바뀌면 아무것도 안 함)
            except Exception as e:
                print(f"[warn] 저장함 갱신 실패: {e}", file=sys.stderr, flush=True)
            now = datetime.now()
            if now.weekday() == 6 and now.hour >= 9:
                digest.send_weekly_report(env)  # weekly.json이 중복 발송 막음
            try:
                digest.embed_archive()
            except Exception as e:
                print(f"[warn] 임베딩 실패: {e}", file=sys.stderr, flush=True)
            if digest.vocab_pending() or digest.tags_pending() or digest.asks_pending():
                digest.ensure_model()
                for name, fn in (
                    ("단어장", digest.process_vocab),
                    ("태그", digest.tag_pending_ratings),
                ):
                    try:
                        fn()
                    except Exception as e:
                        print(f"[warn] {name} 실패: {e}", file=sys.stderr, flush=True)
                try:
                    digest.answer_asks(env)
                except Exception as e:
                    print(f"[warn] 질문 답변 실패: {e}", file=sys.stderr, flush=True)
        except Exception as e:
            print(f"[warn] 수집 루프 에러: {e}", file=sys.stderr, flush=True)
            time.sleep(15)
        time.sleep(1)


if __name__ == "__main__":
    main()
