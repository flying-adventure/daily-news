# 저장함 웹페이지 (news.starhana.kr) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 텔레그램 기사에 `🔖 저장` 버튼을 달고, 저장한 기사의 링크와 한줄요약을 사람별 비밀 주소(`https://news.starhana.kr/u/<토큰>/`)의 웹페이지로 보여준다.

**Architecture:** 맥에서 도는 `digest.py`가 🔖 클릭을 기존 피드백 로그(`ratings.jsonl`)에 `bookmark`로 기록한다. 사람별 정적 HTML을 `site/`에 생성하고, 내용이 바뀌었을 때만 `npx wrangler@4 pages deploy`로 Cloudflare Pages에 올린다. 서버 코드는 없고, 맥이 잠들어 있어도 페이지는 열린다.

**Tech Stack:** Python 3 표준 라이브러리(`html`, `secrets`, `hashlib`, `shutil`, `subprocess`, `os`), Cloudflare Pages(무료), wrangler 4(이미 설치된 Node 24의 `npx`로 실행), 가비아 DNS의 CNAME.

**Spec:** `docs/superpowers/specs/2026-10-12-saved-page-design.md`

## Global Constraints

- 새 pip 의존성 금지. 파이썬은 표준 라이브러리 + 기존 `trafilatura`만 쓴다.
- `digest.py` 한 파일 구조를 유지한다. 테스트는 `test_digest.py` 한 파일에 assert로 쓰고, 프레임워크 없이 `python3 test_digest.py`로 실행한다.
- 코드 주석은 한국어로 쓴다.
- `SITE_URL`이 비었거나 `http://`·`https://`로 시작하지 않으면 저장 기능 전체가 꺼진다. 🔖 버튼, 📚 버튼, 한줄요약 생성, 업로드가 모두 해당하며, 나머지는 기존 동작과 똑같아야 한다.
- 저장 기록의 라벨은 `bookmark`로 한다. 기존 ⭐ 리액션 북마크와 같은 라벨이고, 주간 리포트가 이미 이 라벨을 집계한다.
- 고정 문구: 기사 버튼 `🔖 저장`(callback_data `s:<해시>`), 헤더 버튼 `📚 내 저장함`, 콜백 응답 `저장됨 🔖`, 빈 페이지 문구 `아직 저장한 기사가 없어요. 텔레그램에서 🔖 저장을 눌러보세요.`
- 페이지 주소 형식: `{SITE_URL}/u/{토큰}/`. 토큰은 `secrets.token_urlsafe(16)`.
- 커밋은 오스카가 명시적으로 요청할 때만 한다. 각 Task 끝의 커밋 단계도 요청이 있을 때만 실행한다. 커밋 메시지에 AI 흔적(`Co-Authored-By`, `Generated with ...`)을 넣지 않는다.
- 개발은 `~/orca/daily-news`에서 한다. 실제 실행본은 `~/news-digest`이고 `cp`로 반영한다(Task 6).
- 브라우저·웹 작업은 전부 Aside(`aside-browser` 스킬, `aside` CLI)로 한다.
- 시작 전과 각 Task 전에 `git status --short && git log --oneline -3`을 확인한다. 다른 세션(Devin)이 같은 저장소의 `digest.py`를 고치고 있어서, 아래 "찾을 코드"가 그대로 있는지 확인한 뒤 수정해야 한다.

## Review Focus

1. **`SITE_URL` 오타(예: `https://` 빠짐)**: 다이제스트는 정상 발송되고 📚·🔖 버튼만 빠져야 한다. 잘못된 URL 버튼을 보내면 텔레그램이 메시지 전체를 거부해 그 구독자의 다이제스트가 통째로 끊긴다. → Task 3 `test_digest_without_valid_site_url_still_sends`
2. **launchd 자동 실행의 짧은 PATH**: `node`를 못 찾아 업로드가 자동 실행에서만 실패하면 안 된다. `NPX` 폴더를 PATH 앞에 붙인다. → Task 5 `test_publish_uploads_only_changes_and_retries_failures`
3. **업로드 실패·타임아웃**: 다이제스트·피드백 수집은 계속 돌고, 다음 실행에서 자동으로 다시 시도해야 한다. → Task 5 `test_publish_uploads_only_changes_and_retries_failures`, `test_publish_never_raises`
4. **외부 RSS 제목·링크에 섞인 HTML이나 `javascript:` 주소**: 우리 도메인에서 스크립트가 실행되면 안 된다. → Task 4 `test_page_escapes_html_and_blocks_script_links`
5. **남의 저장이 내 페이지에 섞이거나, 폐기한 토큰의 옛 페이지가 남는 경우** → Task 4 `test_build_site_one_private_page_per_person`

---

### Task 1: 테스트 하네스 + 🔖 저장 버튼 수집

**Files:**
- Create: `test_digest.py`
- Modify: `digest.py`의 `collect_feedback()` 안 콜백 처리부(현재 약 326~352행)와 `STATE_PATH.write_text(...)`(약 424행)

**Interfaces:**
- Consumes: 기존 `collect_feedback(env)`. sent-log 줄은 `{"hash", "title", "link", "mid", "one"?}` 형식이고, `sent[h]`는 그 dict 전체다.
- Produces: `ratings.jsonl`에 `{"ts", "label": "bookmark", "title", "link", "one", "chat"}` 줄. `state.json`은 기존 키를 보존한 채 `offset`만 갱신한다(Task 5의 `site_hash`가 여기에 같이 산다). 테스트 하네스의 `setup()`, `patch()`, `fake_telegram()`, `write_jsonl()`, `read_jsonl()`, `EXTERNAL`.

- [ ] **Step 1: 테스트 파일 생성 (하네스 + 첫 테스트)**

`test_digest.py` 전체 내용:

```python
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


if __name__ == "__main__":
    names = sys.argv[1:]
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and (not names or k in names)]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"전부 통과 ({len(tests)}개)")
```

이후 Task들은 새 테스트를 `if __name__ == "__main__":` 줄 **바로 위**에 추가한다.

- [ ] **Step 2: 실패 확인**

Run: `cd ~/orca/daily-news && python3 test_digest.py`
Expected: FAIL, `ValueError: not enough values to unpack (expected 1, got 0)` (아직 `s:` 콜백을 기록하지 않음)

- [ ] **Step 3: `collect_feedback`에 🔖 처리 추가**

찾을 코드(👍👎 기록 직후 ~ 콜백 응답):

```python
                    count += 1
                # 버튼 로딩 표시 해제
                try:
                    urllib.request.urlopen(
                        f"https://api.telegram.org/bot{token}/answerCallbackQuery",
                        data=urllib.parse.urlencode(
                            {"callback_query_id": cq["id"], "text": "기록됨 ✅"}
                        ).encode(),
```

바꿀 코드:

```python
                    count += 1
                elif label == "s" and h in sent:
                    # 🔖 저장 버튼 = 나중에 읽기 북마크 → 저장함 페이지에 표시
                    f.write(
                        json.dumps(
                            {
                                "ts": dt.now().isoformat(),
                                "label": "bookmark",
                                "title": sent[h]["title"],
                                "link": sent[h].get("link", ""),
                                "one": sent[h].get("one", ""),
                                "chat": chat_id,
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                    count += 1
                # 버튼 로딩 표시 해제
                try:
                    urllib.request.urlopen(
                        f"https://api.telegram.org/bot{token}/answerCallbackQuery",
                        data=urllib.parse.urlencode(
                            {
                                "callback_query_id": cq["id"],
                                "text": "저장됨 🔖" if label == "s" else "기록됨 ✅",
                            }
                        ).encode(),
```

- [ ] **Step 4: `state.json`을 덮어쓰지 않고 병합 저장**

찾을 코드:

```python
    STATE_PATH.write_text(json.dumps({"offset": offset}))
```

바꿀 코드:

```python
    state["offset"] = offset  # 다른 키(site_hash 등)는 보존
    STATE_PATH.write_text(json.dumps(state))
```

(`state`는 함수 맨 위에서 이미 `json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}`로 읽어둔 dict다.)

- [ ] **Step 5: 통과 확인**

Run: `python3 test_digest.py`
Expected: `ok test_bookmark_button_records_bookmark` / `전부 통과 (1개)`

- [ ] **Step 6: 커밋 (오스카가 요청한 경우에만)**

```bash
git add test_digest.py digest.py
git commit -m "🔖 저장 버튼 수집: bookmark로 기록 + state.json 병합 저장"
```

---

### Task 2: 북마크를 중복 제거·취향·주제 태그에 반영

**Files:**
- Modify: `digest.py`의 `dedupe_ratings()`(약 610행), `tags_pending()`(약 630행), `tag_pending_ratings()`(약 641행), `preference_block()`(약 718행)
- Test: `test_digest.py`

**Interfaces:**
- Consumes: Task 1의 `bookmark` 기록.
- Produces: `dedupe_ratings()`가 (사람, 기사)마다 👍/👎 하나와 북마크 하나를 남긴다. `preference_block(chat_id)`가 북마크를 "최근 좋아한 기사"와 "좋아하는 주제"에 넣는다. `tag_pending_ratings()`가 북마크에도 `tags`를 단다.

- [ ] **Step 1: 실패하는 테스트 추가** (`if __name__` 줄 바로 위)

```python
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
```

- [ ] **Step 2: 실패 확인**

Run: `python3 test_digest.py test_dedupe_keeps_one_bookmark_and_one_rating_per_person`
Expected: FAIL, `AssertionError: [('bookmark', 1), ('bookmark', 1), ('bad', 1), ('bookmark', 2), ('note', 1)]`

Run: `python3 test_digest.py test_bookmarks_get_topic_tags`
Expected: FAIL, `AssertionError` (`tags_pending()`이 False)

- [ ] **Step 3: `dedupe_ratings` 교체**

찾을 코드(함수 전체):

```python
def dedupe_ratings():
    """ratings.jsonl에서 (사람, 기사) 단위로 good/bad 중복 제거 — 최신 것만 남김."""
    if not RATINGS_PATH.exists():
        return
    lines = RATINGS_PATH.read_text().splitlines()
    last = {}
    for i, line in enumerate(lines):
        e = json.loads(line)
        if e.get("label") in ("good", "bad"):
            last[(e.get("chat"), e["title"])] = i  # 같은 키면 나중 인덱스로 덮어씀
    keep = [
        line
        for i, line in enumerate(lines)
        if json.loads(line).get("label") not in ("good", "bad")
        or last[(json.loads(line).get("chat"), json.loads(line)["title"])] == i
    ]
    if len(keep) != len(lines):
        RATINGS_PATH.write_text("\n".join(keep) + "\n")
```

바꿀 코드:

```python
def dedupe_ratings():
    """ratings.jsonl에서 (사람, 기사) 단위로 중복 제거 — 최신 것만 남김.
    👍/👎는 서로 덮어쓰고(의견 변경), 🔖 북마크는 따로 하나만 남김."""
    if not RATINGS_PATH.exists():
        return
    lines = RATINGS_PATH.read_text().splitlines()
    group = {"good": "rate", "bad": "rate", "bookmark": "bookmark"}

    def key(e):
        g = group.get(e.get("label"))
        return (g, e.get("chat"), e["title"]) if g else None

    keys = [key(json.loads(line)) for line in lines]
    last = {k: i for i, k in enumerate(keys) if k}  # 같은 키면 나중 인덱스로 덮어씀
    keep = [line for i, (line, k) in enumerate(zip(lines, keys)) if not k or last[k] == i]
    if len(keep) != len(lines):
        RATINGS_PATH.write_text("\n".join(keep) + "\n")
```

- [ ] **Step 4: 태그 대상에 북마크 추가**

`tags_pending()`에서 찾을 코드:

```python
    """태그가 안 달린 good/bad 피드백이 있으면 True."""
    if not RATINGS_PATH.exists():
        return False
    for line in RATINGS_PATH.read_text().splitlines():
        e = json.loads(line)
        if e.get("label") in ("good", "bad") and e.get("title") and "tags" not in e:
```

바꿀 코드:

```python
    """태그가 안 달린 good/bad/bookmark 피드백이 있으면 True."""
    if not RATINGS_PATH.exists():
        return False
    for line in RATINGS_PATH.read_text().splitlines():
        e = json.loads(line)
        if e.get("label") in ("good", "bad", "bookmark") and e.get("title") and "tags" not in e:
```

`tag_pending_ratings()`에서 찾을 코드:

```python
        if e.get("label") in ("good", "bad") and e.get("title") and "tags" not in e
    ]
```

바꿀 코드:

```python
        if e.get("label") in ("good", "bad", "bookmark") and e.get("title") and "tags" not in e
    ]
```

- [ ] **Step 5: `preference_block`에서 북마크 = 좋아한 기사**

찾을 코드:

```python
        if e["label"] == "good":
            good.append(e["title"])
            good_tags.update(e.get("tags", []))
```

바꿀 코드:

```python
        if e["label"] in ("good", "bookmark"):  # 저장 = 👍보다 강한 관심 신호
            if e["title"] in good:  # 👍와 저장이 겹치면 한 번만
                continue
            good.append(e["title"])
            good_tags.update(e.get("tags", []))
```

- [ ] **Step 6: 통과 확인**

Run: `python3 test_digest.py`
Expected: 4개 모두 `ok` / `전부 통과 (4개)`

- [ ] **Step 7: 커밋 (요청 시에만)**

```bash
git add test_digest.py digest.py
git commit -m "북마크를 중복 제거·취향·주제 태그에 반영"
```

---

### Task 3: 한줄요약 · 비밀 토큰 · 발송 버튼 · 환영 문구

**Files:**
- Modify: `digest.py`. `summarize_article()` 바로 아래에 `one_liner` 추가. `def main():` 바로 위에 저장함 섹션 신설(`TOKENS_PATH`, `site_url`, `get_token`). `collect_feedback()`의 환영 메시지와 `main()`의 발송 루프 수정.
- Modify: `.gitignore`
- Test: `test_digest.py`

**Interfaces:**
- Consumes: Task 1의 `s:` 콜백 처리.
- Produces:
  - `one_liner(item: dict, summary: str) -> str`
  - `site_url(env: dict) -> str`: 끝 `/`를 뗀 주소, 무효하면 `""`
  - `get_token(chat_id: int | str) -> str`: `tokens.json`의 `{"<chat_id 문자열>": 토큰}`
  - `TOKENS_PATH`
  - sent-log 줄에 `"one"` 추가

- [ ] **Step 1: 실패하는 테스트 추가** (`if __name__` 줄 바로 위)

```python
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
```

- [ ] **Step 2: 실패 확인**

Run: `python3 test_digest.py`
Expected: FAIL, `AttributeError: module 'digest' has no attribute 'one_liner'`

- [ ] **Step 3: `one_liner` 추가**

`summarize_article()` 끝의 아래 코드 **바로 다음**에 넣는다:

```python
    # 생각 토큰이 한도를 다 먹어 빈 답이 오면 설명문으로 대체
    return out or f"- {item['desc'][:200]}"
```

추가할 코드:

```python


def one_liner(item, summary):
    """저장함 페이지용 한 문장 요약. LLM이 실패하면 5줄 요약 첫 줄로 대체."""
    first = summary.strip().splitlines()[0] if summary.strip() else ""
    fallback = first.lstrip("- ").strip() or item["title"]
    try:
        out = llm(
            f"""다음 기사 요약을 한국어 한 문장(60자 이내)으로 줄여라. 문장만 출력.

제목: {item['title']}
요약:
{summary}""",
            300,
        )
    except Exception as e:
        print(f"[warn] 한줄요약 실패 ({item['title'][:30]}): {e}", file=sys.stderr)
        return fallback
    return out.splitlines()[0].strip() if out else fallback
```

- [ ] **Step 4: 저장함 섹션 신설 (`def main():` 바로 위)**

`def main():` 줄 바로 위에 추가:

```python
# ---- 저장함 웹페이지: 사람별 비밀 주소에 🔖 저장한 기사 목록 ----
TOKENS_PATH = Path(__file__).parent / "tokens.json"


def site_url(env):
    """저장함 사이트 주소. 없거나 http(s)로 시작하지 않으면 "" — 저장 기능 전체 꺼짐."""
    url = env.get("SITE_URL", "").strip().rstrip("/")
    return url if url.startswith(("https://", "http://")) else ""


def get_token(chat_id):
    """사람별 저장함 비밀 주소 토큰. 없으면 새로 만들어 tokens.json에 보관."""
    import secrets

    tokens = json.loads(TOKENS_PATH.read_text()) if TOKENS_PATH.exists() else {}
    key = str(chat_id)
    if key not in tokens:
        tokens[key] = secrets.token_urlsafe(16)  # 22자 — 추측 불가
        TOKENS_PATH.write_text(json.dumps(tokens))
    return tokens[key]


```

- [ ] **Step 5: 발송 루프 수정 (`main()`)**

(a) 찾을 코드:

```python
    subs = load_subs(env)
    summary_cache = {}  # 구독자끼리 겹치는 기사는 요약 재사용
    for cid in subs:
        picked = pick(items, chat_id=cid)  # 구독자별 취향으로 따로 선별
        try:
            send_telegram(f"🗞 AI/개발 다이제스트 {date} — 오늘 {len(picked)}건", env, chat_id=cid)
```

바꿀 코드:

```python
    subs = load_subs(env)
    site = site_url(env)  # 비어 있으면 🔖 저장·📚 저장함 기능 꺼짐
    summary_cache = {}  # 구독자끼리 겹치는 기사는 요약 재사용
    one_cache = {}  # 한줄요약도 같은 방식으로 재사용
    for cid in subs:
        picked = pick(items, chat_id=cid)  # 구독자별 취향으로 따로 선별
        header_buttons = None
        if site:
            header_buttons = [[{"text": "📚 내 저장함", "url": f"{site}/u/{get_token(cid)}/"}]]
        try:
            send_telegram(
                f"🗞 AI/개발 다이제스트 {date} — 오늘 {len(picked)}건",
                env,
                buttons=header_buttons,
                chat_id=cid,
            )
```

(b) 찾을 코드:

```python
            summary = summary_cache[key]
            emoji
```

바꿀 코드:

```python
            summary = summary_cache[key]
            if site and key not in one_cache:
                one_cache[key] = one_liner(it, summary)
            emoji
```

(c) 찾을 코드:

```python
                {"text": "👎 별로", "callback_data": f"b:{h}"},
            ]]
```

바꿀 코드:

```python
                {"text": "👎 별로", "callback_data": f"b:{h}"},
            ]]
            if site:
                buttons[0].append({"text": "🔖 저장", "callback_data": f"s:{h}"})
```

(d) 찾을 코드:

```python
                f.write(json.dumps({"hash": h, "title": it["title"], "link": it["link"], "mid": mid}, ensure_ascii=False) + "\n")
```

바꿀 코드:

```python
                f.write(
                    json.dumps(
                        {"hash": h, "title": it["title"], "link": it["link"], "mid": mid, "one": one_cache.get(key, "")},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
```

- [ ] **Step 6: 환영 메시지에 저장 안내 (`collect_feedback()`)**

찾을 코드:

```python
                send_telegram(
                    """📰 dailyoscarnews 봇이에요
```

바꿀 코드:

```python
                welcome = """📰 dailyoscarnews 봇이에요
```

그리고 찾을 코드(같은 문자열의 끝):

```python
• 기사에 모르는 단어가 나오면, 그 기사 메시지에 '답장'으로 단어만 적어주세요. 초보용 설명을 만들어 보내드려요.""",
                    env,
                    chat_id=cid,
                )
```

바꿀 코드:

```python
• 기사에 모르는 단어가 나오면, 그 기사 메시지에 '답장'으로 단어만 적어주세요. 초보용 설명을 만들어 보내드려요."""
                if site_url(env):
                    welcome += "\n• 🔖 저장 버튼으로 나중에 읽을 기사를 모아두면, 다이제스트 첫 메시지의 📚 내 저장함에서 볼 수 있어요."
                send_telegram(welcome, env, chat_id=cid)
```

(`site_url`은 모듈 뒤쪽에 정의돼 있어도 호출 시점에는 이미 존재하므로 문제없다.)

- [ ] **Step 7: `.gitignore`에 토큰 파일 추가**

`# 개인 데이터` 묶음의 `state.json` 줄 아래에 추가:

```
tokens.json
```

- [ ] **Step 8: 통과 확인**

Run: `python3 test_digest.py`
Expected: 8개 모두 `ok` / `전부 통과 (8개)` (중간에 `전송 완료 (1건, 구독자 1명)` 출력은 정상)

- [ ] **Step 9: 커밋 (요청 시에만)**

```bash
git add test_digest.py digest.py .gitignore
git commit -m "한줄요약·비밀 토큰 + 🔖 저장/📚 내 저장함 버튼"
```

---

### Task 4: 저장함 페이지 생성

**Files:**
- Modify: `digest.py`. 저장함 섹션에 `SITE_DIR`, `page_html`, `render_page`, `build_site`를 추가한다.
- Modify: `.gitignore`
- Test: `test_digest.py`

**Interfaces:**
- Consumes: `TOKENS_PATH`, `get_token()`(Task 3), `ratings.jsonl`의 `bookmark` 줄(Task 1)
- Produces:
  - `SITE_DIR`
  - `page_html(title: str, body: str) -> str`
  - `render_page(saves: list[dict]) -> str`
  - `build_site() -> str`: 생성한 전체 파일 내용의 sha256 hex. `site/index.html`과 `site/u/<토큰>/index.html`을 만든다.

- [ ] **Step 1: 실패하는 테스트 추가** (`if __name__` 줄 바로 위)

```python
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
```

- [ ] **Step 2: 실패 확인**

Run: `python3 test_digest.py test_page_escapes_html_and_blocks_script_links`
Expected: FAIL, `AttributeError: module 'digest' has no attribute 'render_page'`

- [ ] **Step 3: 페이지 함수 추가**

Task 3에서 만든 `get_token()` 함수 **바로 아래**(`def main():` 위)에 추가:

```python
SITE_DIR = Path(__file__).parent / "site"


def page_html(title, body):
    return f"""<!doctype html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<meta name="referrer" content="no-referrer">
<title>{title}</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo",sans-serif;max-width:680px;margin:0 auto;padding:20px 16px;line-height:1.6;color:#1a1a1a;background:#fafafa}}
h1{{font-size:1.4rem}}
h2{{font-size:.85rem;color:#888;margin:28px 0 4px;font-weight:600}}
article{{padding:12px 0;border-bottom:1px solid #e5e5e5}}
h3{{font-size:1rem;margin:0 0 4px}}
p{{margin:0;color:#555}}
a{{color:#1a5fd0;text-decoration:none}}
@media (prefers-color-scheme:dark){{body{{color:#e8e8e8;background:#121212}}article{{border-color:#2a2a2a}}p{{color:#aaa}}a{{color:#8ab4ff}}}}
</style></head><body>
<h1>{title}</h1>
{body}
</body></html>
"""


def render_page(saves):
    """저장 기록 목록 → 저장함 HTML. 최신 저장이 위, 날짜별로 묶음."""
    import html

    rows, day = [], None
    for e in sorted(saves, key=lambda e: e["ts"], reverse=True):
        if e["ts"][:10] != day:
            day = e["ts"][:10]
            rows.append(f"<h2>{day}</h2>")
        title = html.escape(e["title"])
        link = e.get("link", "")
        # 제목·링크는 외부 RSS에서 온 값 — javascript: 주소가 우리 도메인에서 실행되지 않게 http(s)만 링크로
        if link.startswith(("https://", "http://")):
            title = f'<a href="{html.escape(link)}" target="_blank" rel="noopener noreferrer">{title}</a>'
        rows.append(f"<article><h3>{title}</h3><p>{html.escape(e.get('one', ''))}</p></article>")
    body = "\n".join(rows) or "<p>아직 저장한 기사가 없어요. 텔레그램에서 🔖 저장을 눌러보세요.</p>"
    return page_html("📚 내 저장함", body)


def build_site():
    """tokens.json의 모든 사람에게 저장함 페이지를 site/에 새로 만든다. 내용 해시를 반환."""
    import hashlib
    import shutil

    tokens = json.loads(TOKENS_PATH.read_text()) if TOKENS_PATH.exists() else {}
    saves = {}
    if RATINGS_PATH.exists():
        for line in RATINGS_PATH.read_text().splitlines():
            e = json.loads(line)
            if e.get("label") == "bookmark":
                saves.setdefault(str(e.get("chat")), []).append(e)
    pages = {"index.html": page_html("daily-news", "<p>개인 저장함 주소는 텔레그램 봇이 보내드려요.</p>")}
    for chat, token in tokens.items():
        pages[f"u/{token}/index.html"] = render_page(saves.get(chat, []))
    shutil.rmtree(SITE_DIR, ignore_errors=True)  # 폐기된 토큰의 옛 페이지까지 지움
    h = hashlib.sha256()
    for rel, content in sorted(pages.items()):
        path = SITE_DIR / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        h.update(rel.encode() + content.encode())
    return h.hexdigest()


```

- [ ] **Step 4: `.gitignore`에 빌드 폴더 추가**

`tokens.json` 줄 아래에 추가:

```
site/
```

- [ ] **Step 5: 통과 확인 + 눈으로 확인**

Run: `python3 test_digest.py`
Expected: `전부 통과 (10개)`

눈으로 확인(스크래치패드에 임시 페이지를 만들어 Aside로 연다):

```bash
cd ~/orca/daily-news && python3 -c "import digest,pathlib; p=pathlib.Path('$TMPDIR/saved-preview.html'); p.write_text(digest.render_page([{'ts':'2026-10-12T09:00:00','title':'예시 기사 제목','link':'https://news.hada.io','one':'한 문장 요약 예시'}])); print(p)"
open -a Aside "$TMPDIR/saved-preview.html"
```

Expected: 제목 링크, 한줄요약, 날짜 머리글이 보이고 모바일 폭에서도 읽기 편하다. (임시 파일은 실행 환경의 스크래치패드 경로로 바꿔도 된다.)

- [ ] **Step 6: 커밋 (요청 시에만)**

```bash
git add test_digest.py digest.py .gitignore
git commit -m "사람별 저장함 HTML 생성 (이스케이프·noindex·no-referrer)"
```

---

### Task 5: Cloudflare Pages 업로드 + 실행 흐름 연결

**Files:**
- Modify: `digest.py`. 맨 위 import에 `os`를 추가하고, 저장함 섹션에 `publish`를 추가하고, `main()` 세 곳에 연결한다.
- Modify: `.env.example`
- Test: `test_digest.py`. Task 3의 `run_digest`와 `test_digest_adds_save_button_and_my_page_link`를 교체하고 새 테스트를 추가한다.

**Interfaces:**
- Consumes: `site_url`, `get_token`(Task 3), `build_site`, `SITE_DIR`(Task 4), `state.json` 병합 저장(Task 1)
- Produces: `publish(env: dict, dry: bool = False) -> None`. 예외를 절대 밖으로 내지 않는다. 업로드에 성공해야만 `state.json`의 `site_hash`를 갱신한다.

- [ ] **Step 1: Task 3의 발송 테스트 2개를 publish 기록 버전으로 교체**

`test_digest.py`에서 `def run_digest(site_url):`부터 `test_digest_without_valid_site_url_still_sends` 함수 끝까지를 아래로 통째로 바꾼다:

```python
def run_digest(site_url):
    """가짜 기사 1건으로 다이제스트 발송을 돌리고 (보낸 메시지들, publish 호출 기록)을 돌려준다."""
    if site_url is not None:
        digest.ENV_PATH.write_text(f"TELEGRAM_TOKEN=x\nTELEGRAM_CHAT_ID=111\nSITE_URL={site_url}\n")
    item = {"source": "HN", "title": "기사", "link": "https://ex.com/1", "desc": "d"}
    sent, published = [], []

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
        publish=lambda env, dry=False: published.append(dry),
    )
    digest.main()
    return sent, published


def test_digest_adds_save_button_and_my_page_link():
    setup()
    sent, published = run_digest("https://news.example.com/")
    (_, header_buttons, _), (_, article_buttons, _) = sent
    token = json.loads(digest.TOKENS_PATH.read_text())["111"]
    assert header_buttons == [[{"text": "📚 내 저장함", "url": f"https://news.example.com/u/{token}/"}]]
    assert {"text": "🔖 저장", "callback_data": "s:" + digest.title_hash("기사")} in article_buttons[0]
    log = read_jsonl(digest.SENTLOG_PATH)[-1]
    assert (log["link"], log["one"], log["mid"]) == ("https://ex.com/1", "한줄", 77), log
    assert published == [False]


def test_digest_without_valid_site_url_still_sends():
    for bad in (None, "news.example.com"):  # 없음 / https:// 빠짐
        setup()
        sent, _ = run_digest(bad)
        (_, header_buttons, _), (_, article_buttons, _) = sent
        assert header_buttons is None, header_buttons
        assert all(b["text"] != "🔖 저장" for b in article_buttons[0]), article_buttons
```

- [ ] **Step 2: 업로드 테스트 추가** (`if __name__` 줄 바로 위)

```python
# ---- Task 5: 업로드 ----

ENV = {
    "SITE_URL": "https://news.example.com",
    "TELEGRAM_CHAT_ID": "111",
    "CLOUDFLARE_API_TOKEN": "t",
    "CLOUDFLARE_ACCOUNT_ID": "a",
    "NPX": "/opt/node/bin/npx",
}


class Done:
    def __init__(self, code):
        self.returncode, self.stdout, self.stderr = code, "", "boom"


def test_publish_uploads_only_changes_and_retries_failures():
    setup()
    digest.get_token(111)
    runs, codes = [], [1, 0]

    def fake_run(cmd, **kw):
        runs.append((cmd, kw["env"]))
        return Done(codes.pop(0))

    subprocess.run = fake_run
    digest.publish(ENV)  # 1차: 업로드 실패 → 해시 저장 안 함
    assert not digest.STATE_PATH.exists()
    digest.publish(ENV)  # 2차: 재시도 성공 → 해시 저장
    digest.publish(ENV)  # 3차: 바뀐 게 없음 → 업로드 생략
    assert len(runs) == 2, runs
    cmd, run_env = runs[1]
    assert cmd[:5] == ["/opt/node/bin/npx", "--yes", "wrangler@4", "pages", "deploy"], cmd
    assert run_env["CLOUDFLARE_API_TOKEN"] == "t" and run_env["CLOUDFLARE_ACCOUNT_ID"] == "a"
    assert run_env["PATH"].startswith("/opt/node/bin:"), run_env["PATH"]
    assert json.loads(digest.STATE_PATH.read_text())["site_hash"]
    digest.publish({**ENV, "SITE_URL": ""})  # 기능 꺼짐
    assert len(runs) == 2


def test_publish_never_raises():
    setup()
    digest.get_token(111)

    def hang(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 180)

    subprocess.run = hang
    digest.publish(ENV)  # 예외가 밖으로 새면 다이제스트·피드백이 같이 죽음
    assert not digest.STATE_PATH.exists()


def test_dry_run_builds_own_preview_without_upload():
    setup()
    digest.publish(ENV, dry=True)
    token = json.loads(digest.TOKENS_PATH.read_text())["111"]
    assert (digest.SITE_DIR / f"u/{token}/index.html").exists()
    assert EXTERNAL == []


def test_feedback_only_run_publishes():
    setup()
    published = []
    urllib.request.urlopen = fake_telegram([], [])
    patch(publish=lambda env, dry=False: published.append(dry))
    sys.argv = ["digest.py", "--feedback-only"]
    digest.main()
    assert published == [False], published
```

- [ ] **Step 3: 실패 확인**

Run: `python3 test_digest.py`
Expected: FAIL, `AttributeError: module 'digest' has no attribute 'publish'`

- [ ] **Step 4: `import os` 추가**

찾을 코드(파일 맨 위):

```python
import json
import subprocess
```

바꿀 코드:

```python
import json
import os
import subprocess
```

- [ ] **Step 5: `publish` 추가**

Task 4의 `build_site()` 함수 **바로 아래**(`def main():` 위)에 추가:

```python
def publish(env, dry=False):
    """저장함 사이트를 만들고, 지난 업로드 이후 바뀌었으면 Cloudflare Pages에 올린다.
    부가 기능이라 절대 예외를 밖으로 내지 않음. 실패하면 다음 실행에서 자동 재시도."""
    if not site_url(env):
        return
    try:
        if dry and env.get("TELEGRAM_CHAT_ID"):
            get_token(env["TELEGRAM_CHAT_ID"])  # 미리보기용 본인 페이지
        site_hash = build_site()
        state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}
        if dry or state.get("site_hash") == site_hash:
            return
        npx = env.get("NPX", "npx")
        run_env = dict(
            os.environ,
            CLOUDFLARE_API_TOKEN=env.get("CLOUDFLARE_API_TOKEN", ""),
            CLOUDFLARE_ACCOUNT_ID=env.get("CLOUDFLARE_ACCOUNT_ID", ""),
            WRANGLER_SEND_METRICS="false",
        )
        if "/" in npx:
            # launchd는 PATH가 짧아 node를 못 찾음 → npx가 있는 폴더를 앞에 붙임
            run_env["PATH"] = str(Path(npx).parent) + ":" + run_env.get("PATH", "")
        r = subprocess.run(
            [
                npx, "--yes", "wrangler@4", "pages", "deploy", str(SITE_DIR),
                "--project-name", env.get("PAGES_PROJECT", "daily-news"),
                "--branch", "main", "--commit-dirty=true",
            ],
            capture_output=True,
            text=True,
            timeout=180,
            env=run_env,
            cwd=str(Path(__file__).parent),  # launchd 기본 작업 폴더는 / — wrangler 임시 파일이 쓰기 실패하지 않게
        )
        if r.returncode != 0:
            print(f"[warn] 저장함 업로드 실패: {(r.stderr or r.stdout)[-300:]}", file=sys.stderr)
            return
        state["site_hash"] = site_hash
        STATE_PATH.write_text(json.dumps(state))
        print("[info] 저장함 업로드 완료", file=sys.stderr)
    except Exception as e:
        print(f"[warn] 저장함 업로드 실패: {e}", file=sys.stderr)


```

- [ ] **Step 6: `main()` 세 곳에 연결**

(a) `--feedback-only` 분기 끝. 찾을 코드:

```python
            try:
                tag_pending_ratings()
            except Exception as e:
                print(f"[warn] 태그 부여 실패: {e}", file=sys.stderr)
        return
```

바꿀 코드:

```python
            try:
                tag_pending_ratings()
            except Exception as e:
                print(f"[warn] 태그 부여 실패: {e}", file=sys.stderr)
        publish(env, dry)  # 🔖 저장이 들어왔으면 저장함 페이지 갱신
        return
```

(b) `--dry` 출력 끝. 찾을 코드:

```python
            print(f"{emoji} {it['title']}\n\n{summary}\n\n🔗 {it['link']}", "\n" + "─" * 30)
        return
```

바꿀 코드:

```python
            print(f"{emoji} {it['title']}\n\n{summary}\n\n🔗 {it['link']}", "\n" + "─" * 30)
        publish(env, dry=True)  # 업로드 없이 site/에 본인 저장함 미리보기 생성
        return
```

(c) 발송 끝. 찾을 코드:

```python
    SUBS_PATH.write_text(json.dumps(sorted(subs)))
    print(f"전송 완료
```

바꿀 코드:

```python
    SUBS_PATH.write_text(json.dumps(sorted(subs)))
    publish(env)  # 새 구독자 토큰이 생겼으면 저장함 페이지 갱신
    print(f"전송 완료
```

- [ ] **Step 7: `.env.example`에 항목 추가** (파일 끝)

```
# (선택) 저장함 웹페이지 — Cloudflare Pages. SITE_URL이 없으면 🔖 저장 기능 전체가 꺼짐
SITE_URL=https://news.example.com
PAGES_PROJECT=daily-news
CLOUDFLARE_API_TOKEN=your-cloudflare-api-token
CLOUDFLARE_ACCOUNT_ID=your-cloudflare-account-id
# launchd 자동 실행은 PATH가 짧음 — npx 절대경로 (which npx)
NPX=/opt/homebrew/bin/npx
```

- [ ] **Step 8: 전체 통과 + 문법 확인**

Run: `python3 test_digest.py && python3 -m py_compile digest.py eval_summaries.py && echo OK`
Expected: `전부 통과 (14개)` 다음에 `OK`

- [ ] **Step 9: 커밋 (요청 시에만)**

```bash
git add test_digest.py digest.py .env.example
git commit -m "저장함 Cloudflare Pages 업로드: 바뀐 때만, 실패 시 다음 실행에서 재시도"
```

---

### Task 6: README + 실행본 반영 + 도메인 연결 + 실전 확인

외부에 보이는 변경(Cloudflare 설정, 가비아 DNS)이 들어 있다. **각 Aside 작업은 실행 직전에 오스카에게 무엇을 바꾸는지 보여주고 OK를 받은 뒤** 실행한다. 토큰·비밀번호는 채팅이나 로그에 출력하지 않는다.

**Files:**
- Modify: `README.md`
- 실행본: `~/news-digest/digest.py`(복사), `~/news-digest/.env`(오스카가 직접 편집)

- [ ] **Step 1: README 갱신**

(a) `## 특징` 목록의 `- **실패 알림**:` 줄 위에 추가:

```markdown
- **저장함 웹페이지**: 기사 밑 🔖 저장 → 사람별 비밀 주소(`/u/<토큰>/`)에 링크 + 한줄요약 목록. Cloudflare Pages(무료)에 바뀐 때만 자동 업로드 — 맥이 꺼져 있어도 열림. `SITE_URL`이 없으면 기능 전체 꺼짐
```

(b) `## 최근 개선 (2026-10-12)` 목록 끝에 추가:

```markdown
- **🔖 저장 + 저장함 웹페이지**: 기사 버튼에 🔖 저장, 다이제스트 첫 메시지에 📚 내 저장함 링크. 저장은 👍보다 강한 취향 신호로 선별·주제 태그에 반영
```

(c) `(선택) 5분 간격 피드백 실행` 단락과 그 아래 코드블록 다음(`## 최근 개선` 위)에 추가:

````markdown
(선택) 저장함 웹페이지 — Cloudflare 무료 계정이면 됨 (카드 등록·도메인 추가 불필요):

```bash
# .env에 SITE_URL, PAGES_PROJECT, CLOUDFLARE_API_TOKEN(권한: Account → Cloudflare Pages → Edit),
# CLOUDFLARE_ACCOUNT_ID, NPX(which npx 결과) 추가 후 — 프로젝트는 처음 한 번만 생성
set -a; source <(grep -E '^CLOUDFLARE_' .env); set +a
npx --yes wrangler@4 pages project create daily-news --production-branch main
```

자기 도메인을 쓰려면 Pages 프로젝트의 Custom domains에 서브도메인을 추가하고, 도메인 업체 DNS에 `CNAME <서브도메인> → <프로젝트>.pages.dev`를 넣는다.
````

(d) `## 만들면서 겪은 문제들` 표의 마지막 줄 아래에 추가:

```markdown
| ⭐ 리액션 북마크가 하나도 안 쌓임 | ⭐는 텔레그램이 허용하는 리액션 이모지 목록(73개)에 없음 — 애초에 누를 수 없음 | 기사 버튼에 🔖 저장 추가, 같은 `bookmark` 라벨로 기록 |
```

- [ ] **Step 2: 실행본 반영**

```bash
diff -q ~/news-digest/digest.py <(git -C ~/orca/daily-news show 311d396:digest.py) && echo "실행본 = 작업 전 원본"
cp ~/orca/daily-news/digest.py ~/news-digest/digest.py
```

Expected: 첫 줄이 `실행본 = 작업 전 원본`(311d396 = 이 계획을 쓸 때의 HEAD). 다르면 다른 세션이 실행본을 따로 고친 것이니 **복사하지 말고 오스카에게 보고**한다.

- [ ] **Step 3: Cloudflare 계정 ID·API 토큰 받기 (오스카, Aside)**

오스카가 Aside에서 직접 한다. 결제·도메인 추가·Zero Trust·Registrar 메뉴에는 들어가지 않는다.
1. 계정 ID: 대시보드 주소 `dash.cloudflare.com/<32자리>/...`의 32자리
2. API 토큰: My Profile → API Tokens → Create Token → Create Custom Token → Permissions `Account / Cloudflare Pages / Edit` → Continue to summary → Create Token(한 번만 보이므로 복사)

- [ ] **Step 4: 실행본 `.env`에 항목 추가 (오스카가 직접)**

Run: `open -e ~/news-digest/.env`

오스카가 끝에 붙여넣는다. 토큰 값은 채팅에 쓰지 않는다:

```
SITE_URL=https://news.starhana.kr
PAGES_PROJECT=daily-news
CLOUDFLARE_API_TOKEN=<복사한 토큰>
CLOUDFLARE_ACCOUNT_ID=<32자리 계정 ID>
NPX=/opt/homebrew/opt/node@24/bin/npx
```

확인(값은 숨기고 키만 출력):

```bash
grep -oE '^(SITE_URL|PAGES_PROJECT|CLOUDFLARE_API_TOKEN|CLOUDFLARE_ACCOUNT_ID|NPX)=' ~/news-digest/.env
```

Expected: 다섯 줄 모두 출력

- [ ] **Step 5: Pages 프로젝트 생성**

```bash
cd ~/news-digest && set -a && source <(grep -E '^CLOUDFLARE_' .env) && set +a && \
  WRANGLER_SEND_METRICS=false /opt/homebrew/opt/node@24/bin/npx --yes wrangler@4 pages project create daily-news --production-branch main
```

Expected: 생성 성공 메시지와 `https://daily-news-<무언가>.pages.dev` 또는 `https://daily-news.pages.dev` 주소. **이 pages.dev 주소를 기록**한다(Step 7의 CNAME 값). 이름이 이미 쓰이고 있으면 다른 이름(예: `starhana-news`)으로 만들고 `.env`의 `PAGES_PROJECT`도 같이 바꾼다.

- [ ] **Step 6: 본인 토큰 생성 + 첫 업로드**

```bash
cd ~/news-digest && venv/bin/python3 -c "
import digest
e = digest.load_env()
print(digest.site_url(e) + '/u/' + digest.get_token(e['TELEGRAM_CHAT_ID']) + '/')
digest.publish(e)
"
```

Expected: 오스카의 저장함 주소가 한 줄 출력되고, 이어서 `[info] 저장함 업로드 완료`가 나온다. 이 주소는 오스카에게만 알려준다. 확인: `curl -s -o /dev/null -w '%{http_code}\n' https://<pages.dev 주소>/` → `200`

- [ ] **Step 7: 커스텀 도메인 연결 (Aside, 실행 전 오스카 OK 필수)**

(a) Cloudflare 쪽:

```bash
aside "Cloudflare 대시보드에서 Workers & Pages → daily-news 프로젝트 → Custom domains → Set up a custom domain → news.starhana.kr 입력 → Continue. 결제·플랜 업그레이드·'Add a site/도메인 추가' 화면이 나오면 아무것도 누르지 말고 멈춰서 보고. 끝나면 화면에 안내되는 CNAME 대상 값을 알려줘."
```

(b) 가비아 쪽. CNAME 대상은 (a)에서 안내된 값이고, 보통 Step 5의 pages.dev 주소다:

```bash
aside "가비아(gabia.com) My가비아 → 도메인 → starhana.kr → DNS 관리툴(DNS 설정) → 레코드 수정 → 레코드 추가: 타입 CNAME, 호스트 news, 값/위치 <pages.dev 주소>. (값 끝에 점(.)을 붙이라고 안내하면 붙임), TTL 기본값. 기존 레코드(@, www 등 GitHub Pages용 A/CNAME)는 절대 수정·삭제하지 말 것. 저장 버튼 누르기 직전 화면을 보고하고 멈춰."
```

보고된 화면을 오스카와 확인한 뒤 저장한다: `aside session resume <id> "저장해"`

- [ ] **Step 8: 연결 확인**

```bash
dig +short CNAME news.starhana.kr
curl -s -o /dev/null -w '%{http_code}\n' https://news.starhana.kr/
dig +short starhana.kr   # 기존 GitHub Pages IP 4개(185.199.108~111.153) 그대로인지
```

Expected: 첫 줄에 pages.dev 주소, 둘째 줄 `200`, 셋째는 기존 IP 4개. HTTPS 인증서 발급에 수 분~수십 분 걸릴 수 있다. 그 사이에는 `000`이나 `526`이 나오니 잠시 뒤 다시 확인한다. 이어서 Step 6의 본인 주소를 Aside로 열어 본다: `aside "https://news.starhana.kr/u/<토큰>/"` → "아직 저장한 기사가 없어요" 화면.

- [ ] **Step 9: 실전 확인 (다음 08:00 다이제스트)**

1. 첫 메시지에 `📚 내 저장함` 버튼이 있고, 누르면 본인 페이지가 열린다.
2. 기사 하나에서 `🔖 저장`을 누르면 5분 안에 "저장됨 🔖"이 뜬다.
3. `tail -5 ~/news-digest/feedback.log`에 `[info] 저장함 업로드 완료`가 있다.
4. 페이지를 새로고침하면 그 기사의 제목 링크와 한줄요약이 보인다.
5. 친구(다른 구독자) 주소에는 오스카의 저장이 보이지 않는다(친구 토큰은 `~/news-digest/tokens.json`에 있음, 출력 금지).

- [ ] **Step 10: 커밋 (요청 시에만)**

```bash
git -C ~/orca/daily-news add README.md docs/
git -C ~/orca/daily-news commit -m "README: 저장함 웹페이지 설정법 + ⭐ 리액션 트러블슈팅"
```
