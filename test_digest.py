#!/usr/bin/env python3
# digest.py 자가검증 — 네트워크·LLM·Cloudflare 없이 동작
# 실행: python3 test_digest.py             (전체)
#       python3 test_digest.py test_이름    (하나만)
import json
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

import digest

TMP = Path(tempfile.mkdtemp())
EXTERNAL = []  # 테스트 중 시도된 실제 네트워크·외부 명령 호출 기록
_ORIG = {}


def no_external(*args, **kwargs):
    EXTERNAL.append(args)
    raise AssertionError("테스트 중 네트워크/외부 명령 호출 금지")


def patch(**attrs):
    """digest 모듈 함수를 가짜로 바꿔 끼움. 다음 setup()이 원래대로 되돌림."""
    for name, value in attrs.items():
        _ORIG.setdefault(name, getattr(digest, name))
        setattr(digest, name, value)


def setup():
    """데이터 파일을 전부 빈 임시 폴더로 돌리고 외부 호출을 막는다."""
    for name, value in _ORIG.items():
        setattr(digest, name, value)
    _ORIG.clear()
    EXTERNAL.clear()
    shutil.rmtree(TMP, ignore_errors=True)
    TMP.mkdir()
    digest.ENV_PATH = TMP / ".env"
    digest.ENV_PATH.write_text("TELEGRAM_TOKEN=x\nTELEGRAM_CHAT_ID=111\n")
    digest.STATE_PATH = TMP / "state.json"
    digest.RATINGS_PATH = TMP / "ratings.jsonl"
    digest.SENTLOG_PATH = TMP / "sent-log.jsonl"
    digest.SUBS_PATH = TMP / "subscribers.json"
    digest.WEEKLY_PATH = TMP / "weekly.json"
    digest.TOKENS_PATH = TMP / "tokens.json"
    digest.SITE_DIR = TMP / "site"
    urllib.request.urlopen = no_external
    subprocess.run = no_external
    sys.argv = ["digest.py"]


class FakeResp:
    def __init__(self, data):
        self._data = json.dumps(data).encode()

    def read(self):
        return self._data


def fake_telegram(updates, calls):
    """getUpdates는 updates를 돌려주고, 나머지 텔레그램 호출은 calls에 (url, data)로 기록."""

    def urlopen(url, data=None, timeout=None):
        if "getUpdates" in url:
            return FakeResp({"ok": True, "result": updates})
        calls.append((url, data))
        return FakeResp({"ok": True, "result": {"message_id": 1}})

    return urlopen


def write_jsonl(path, rows):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


# ---- Task 1: 🔖 저장 버튼 수집 ----


def test_bookmark_button_records_bookmark():
    setup()
    write_jsonl(digest.SENTLOG_PATH, [
        {"hash": "abc", "title": "제목", "link": "https://ex.com/a", "mid": 5, "one": "한줄"},
    ])
    digest.STATE_PATH.write_text(json.dumps({"offset": 0, "site_hash": "keep"}))
    calls = []
    urllib.request.urlopen = fake_telegram([
        {"update_id": 10, "callback_query": {"id": "q1", "data": "s:abc", "message": {"chat": {"id": 111}}}},
    ], calls)
    digest.collect_feedback({"TELEGRAM_TOKEN": "x", "TELEGRAM_CHAT_ID": "111"})
    [row] = read_jsonl(digest.RATINGS_PATH)
    assert (row["label"], row["title"], row["link"], row["one"], row["chat"]) == (
        "bookmark", "제목", "https://ex.com/a", "한줄", 111), row
    # 다른 키(site_hash)를 지우지 않고 offset만 갱신
    assert json.loads(digest.STATE_PATH.read_text()) == {"offset": 11, "site_hash": "keep"}
    [(url, data)] = calls
    assert "answerCallbackQuery" in url
    assert urllib.parse.parse_qs(data.decode())["text"] == ["저장됨 🔖"]


# ---- Task 2: 중복 제거 + 취향 반영 ----


def test_dedupe_keeps_one_bookmark_and_one_rating_per_person():
    setup()
    write_jsonl(digest.RATINGS_PATH, [
        {"label": "good", "title": "A", "chat": 1},
        {"label": "bookmark", "title": "A", "chat": 1, "link": "https://a", "one": "x"},
        {"label": "bookmark", "title": "A", "chat": 1, "link": "https://a", "one": "x"},
        {"label": "bad", "title": "A", "chat": 1},
        {"label": "bookmark", "title": "A", "chat": 2, "link": "https://a", "one": "x"},
        {"label": "note", "text": "메모", "chat": 1},
    ])
    digest.dedupe_ratings()
    left = [(r["label"], r["chat"]) for r in read_jsonl(digest.RATINGS_PATH)]
    assert left == [("bookmark", 1), ("bad", 1), ("bookmark", 2), ("note", 1)], left


def test_bookmark_counts_as_liked_once():
    setup()
    write_jsonl(digest.RATINGS_PATH, [
        {"label": "good", "title": "A", "chat": 111, "tags": ["보안"]},
        {"label": "bookmark", "title": "A", "chat": 111, "tags": ["보안"]},
        {"label": "bookmark", "title": "B", "chat": 111, "tags": ["AI업계"]},
        {"label": "bookmark", "title": "C", "chat": 222},
    ])
    block = digest.preference_block(111)
    assert "최근 좋아한 기사: A / B\n" in block, block
    assert "보안(1)" in block and "AI업계(1)" in block, block


def test_bookmarks_get_topic_tags():
    setup()
    write_jsonl(digest.RATINGS_PATH, [{"label": "bookmark", "title": "B", "chat": 111}])
    assert digest.tags_pending()
    patch(llm=lambda *a, **k: json.dumps({"items": [{"n": 1, "tags": ["AI업계"]}]}))
    digest.tag_pending_ratings()
    assert read_jsonl(digest.RATINGS_PATH)[0]["tags"] == ["AI업계"]


if __name__ == "__main__":
    names = sys.argv[1:]
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and (not names or k in names)]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"전부 통과 ({len(tests)}개)")
