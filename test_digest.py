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


# ---- Task 3: 한줄요약 · 비밀 토큰 · 발송 ----


def test_one_liner_falls_back_when_llm_fails():
    setup()

    def boom(*a, **k):
        raise RuntimeError("LM Studio 꺼짐")

    patch(llm=boom)
    assert digest.one_liner({"title": "T"}, "- 첫 줄 사실\n- 둘째") == "첫 줄 사실"
    patch(llm=lambda *a, **k: "")
    assert digest.one_liner({"title": "T"}, "- ") == "T"
    patch(llm=lambda *a, **k: "짧은 한 문장\n군더더기")
    assert digest.one_liner({"title": "T"}, "- x") == "짧은 한 문장"


def test_token_is_stable_and_different_per_person():
    setup()
    a1, a2, b = digest.get_token(111), digest.get_token("111"), digest.get_token(222)
    assert a1 == a2 and a1 != b and len(a1) >= 22, (a1, a2, b)
    assert json.loads(digest.TOKENS_PATH.read_text()) == {"111": a1, "222": b}


def run_digest(site_url):
    """가짜 기사 1건으로 다이제스트 발송을 돌리고 보낸 메시지 목록을 돌려준다."""
    if site_url is not None:
        digest.ENV_PATH.write_text(f"TELEGRAM_TOKEN=x\nTELEGRAM_CHAT_ID=111\nSITE_URL={site_url}\n")
    item = {"source": "HN", "title": "기사", "link": "https://ex.com/1", "desc": "d"}
    sent = []

    def fake_send(text, env, buttons=None, chat_id=None):
        sent.append((text, buttons, chat_id))
        return 77

    urllib.request.urlopen = fake_telegram([], [])
    patch(
        collect=lambda: [item],
        ensure_model=lambda: None,
        process_vocab=lambda: None,
        tag_pending_ratings=lambda: None,
        pick=lambda items, chat_id=None: [item],
        summarize_article=lambda it, body=None: "- 사실",
        one_liner=lambda it, summary: "한줄",
        send_telegram=fake_send,
    )
    digest.main()
    return sent


def test_digest_adds_save_button_and_my_page_link():
    setup()
    sent = run_digest("https://news.example.com/")
    (_, header_buttons, _), (_, article_buttons, _) = sent
    token = json.loads(digest.TOKENS_PATH.read_text())["111"]
    assert header_buttons == [[{"text": "📚 내 저장함", "url": f"https://news.example.com/u/{token}/"}]]
    assert {"text": "🔖 저장", "callback_data": "s:" + digest.title_hash("기사")} in article_buttons[0]
    log = read_jsonl(digest.SENTLOG_PATH)[-1]
    assert (log["link"], log["one"], log["mid"]) == ("https://ex.com/1", "한줄", 77), log


def test_digest_without_valid_site_url_still_sends():
    for bad in (None, "news.example.com"):  # 없음 / https:// 빠짐
        setup()
        sent = run_digest(bad)
        (_, header_buttons, _), (_, article_buttons, _) = sent
        assert header_buttons is None, header_buttons
        assert all(b["text"] != "🔖 저장" for b in article_buttons[0]), article_buttons


# ---- Task 4: 페이지 생성 ----


def test_page_escapes_html_and_blocks_script_links():
    setup()
    page = digest.render_page([
        {"ts": "2026-10-12T09:00:00", "title": "<script>alert(1)</script>", "link": "javascript:alert(1)", "one": "a & b"},
        {"ts": "2026-10-13T09:00:00", "title": "새 기사", "link": "https://ex.com/?a=1&b=2", "one": "요약"},
    ])
    assert "<script>" not in page and "&lt;script&gt;" in page
    assert "javascript:" not in page
    assert 'href="https://ex.com/?a=1&amp;b=2"' in page
    assert "a &amp; b" in page
    assert page.index("2026-10-13") < page.index("2026-10-12")  # 최신 날짜가 위
    assert '<meta name="robots" content="noindex">' in page
    assert '<meta name="referrer" content="no-referrer">' in page


def test_build_site_one_private_page_per_person():
    setup()
    me, friend = digest.get_token(111), digest.get_token(222)
    write_jsonl(digest.RATINGS_PATH, [
        {"ts": "2026-10-12T09:00:00", "label": "bookmark", "title": "내꺼", "link": "https://a", "one": "x", "chat": 111},
        {"ts": "2026-10-12T09:00:00", "label": "good", "title": "좋아요만", "chat": 111},
    ])
    h1 = digest.build_site()
    mine = (digest.SITE_DIR / f"u/{me}/index.html").read_text()
    other = (digest.SITE_DIR / f"u/{friend}/index.html").read_text()
    assert "내꺼" in mine and "좋아요만" not in mine
    assert "내꺼" not in other and "아직 저장한 기사가 없어요" in other
    assert (digest.SITE_DIR / "index.html").exists()
    assert digest.build_site() == h1  # 내용이 같으면 해시도 같음
    digest.TOKENS_PATH.write_text(json.dumps({"111": me}))  # 친구 토큰 폐기
    assert digest.build_site() != h1
    assert not (digest.SITE_DIR / f"u/{friend}").exists()  # 옛 주소 페이지는 사라짐


if __name__ == "__main__":
    names = sys.argv[1:]
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and (not names or k in names)]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"전부 통과 ({len(tests)}개)")
