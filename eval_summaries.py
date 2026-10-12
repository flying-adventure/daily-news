#!/usr/bin/env python3
"""요약 품질 평가(evals): 고정 테스트셋으로 요약을 돌리고 LLM-as-judge로 채점.

사용:
  python3 eval_summaries.py build   # 현재 피드에서 기사 10개+본문을 테스트셋으로 저장
  python3 eval_summaries.py run     # 테스트셋 요약 → 채점 → 평균 출력 + 결과 축적

왜 필요한가: 프롬프트/모델을 바꿨을 때 "좋아졌나?"를 감이 아니라 점수로 비교하기 위해.
주의: 같은 모델이 채점하므로 자기 출력에 후한 편 — 절대점수보다 A/B 비교용으로 볼 것.
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import digest

SET_PATH = Path(__file__).parent / "eval-set.jsonl"
RESULTS_PATH = Path(__file__).parent / "eval-results.jsonl"
SET_SIZE = 10

CRITERIA = ["accuracy", "format", "coverage", "korean"]

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        **{c: {"type": "integer", "minimum": 1, "maximum": 5} for c in CRITERIA},
        "rationale": {"type": "string"},
    },
    "required": [*CRITERIA, "rationale"],
}


def build():
    """현재 피드에서 기사 SET_SIZE개를 골라 제목+본문을 고정 저장."""
    items = digest.collect()
    out = []
    for it in items[:SET_SIZE]:
        try:
            body = digest.article_text(it["link"]) if it["link"] else ""
        except Exception:
            body = ""
        out.append(
            {"title": it["title"], "link": it["link"], "desc": it["desc"], "body": body or it["desc"]}
        )
        print(f"  [{len(out)}] {it['title'][:60]} (본문 {len(body)}자)", file=sys.stderr)
    SET_PATH.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in out) + "\n")
    print(f"테스트셋 저장: {SET_PATH} ({len(out)}건)")


def judge(article, summary):
    """기사 본문 + 요약을 채점자 LLM에게 주고 기준별 1~5점을 받는다."""
    ans = digest.llm(
        f"""아래는 뉴스 기사와 그 한국어 요약이다. 채점자로서 기준별로 1~5점을 매겨라.
- accuracy: 요약이 기사 내용과 일치하는가 (날조·왜곡 없음)
- format: '- '로 시작하는 5줄이며 마지막 줄이 완성된 문장인가
- coverage: 기사의 핵심 사실이 빠짐없이 담겼는가
- korean: 한국어가 자연스러운가
- rationale: 채점 근거 한두 문장
기사 제목: {article['title']}
기사 본문: {article['body'][:4000]}

요약:
{summary}""",
        2000,
        schema=JUDGE_SCHEMA,
    )
    return json.loads(ans)


def run(model=None):
    entries = [json.loads(l) for l in SET_PATH.read_text().splitlines()]
    digest.ensure_model()
    orig_model = digest.MODEL
    results = []
    for i, e in enumerate(entries, 1):
        it = {"title": e["title"], "link": e["link"], "desc": e["desc"]}
        t0 = time.time()
        if model:
            digest.MODEL = model  # 요약만 비교 대상 모델로
        summary = digest.summarize_article(it, body=e["body"])  # 저장된 본문으로 (재현성)
        digest.MODEL = orig_model  # 채점은 항상 같은 모델로 — 공정 비교
        secs = round(time.time() - t0, 1)
        scores = judge(e, summary)
        results.append({"title": e["title"][:50], "secs": secs, "summary": summary, **scores})
        avg = sum(scores[c] for c in CRITERIA) / len(CRITERIA)
        print(f"[{i}/{len(entries)}] {e['title'][:45]}  평균{avg:.1f} ({secs}s)", file=sys.stderr)
    print(f"\n{'기사':<48} acc fmt cov kor  sec")
    for r in results:
        print(
            f"{r['title']:<48} {r['accuracy']}   {r['format']}   {r['coverage']}   {r['korean']}  {r['secs']}"
        )
    means = {c: round(sum(r[c] for r in results) / len(results), 2) for c in CRITERIA}
    total_sec = round(sum(r["secs"] for r in results), 1)
    print(f"\n평균  accuracy {means['accuracy']}  format {means['format']}  "
          f"coverage {means['coverage']}  korean {means['korean']}  | 총 {total_sec}s")
    with RESULTS_PATH.open("a") as f:
        f.write(json.dumps(
            {"ts": datetime.now().isoformat(), "n": len(results), "model": model or digest.MODEL,
             "mean": means, "total_sec": total_sec, "detail": results},
            ensure_ascii=False) + "\n")
    print(f"결과 축적: {RESULTS_PATH}")


if __name__ == "__main__":
    if "build" in sys.argv:
        build()
    elif "run" in sys.argv:
        mi = sys.argv.index("--model") + 1 if "--model" in sys.argv else 0
        run(model=sys.argv[mi] if mi else None)
    else:
        print(__doc__)
