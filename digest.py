#!/usr/bin/env python3
# AI/개발 뉴스 일일 요약 → 텔레그램
# 사용: python3 digest.py        (텔레그램 전송)
#       python3 digest.py --dry  (전송 없이 터미널 출력)
import json
import subprocess
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

FEEDS = {
    "긱뉴스": "https://news.hada.io/rss/news",
    "Hacker News": "https://hnrss.org/frontpage?points=100",
    "TechCrunch AI": "https://techcrunch.com/category/artificial-intelligence/feed/",
}
LM_URL = "http://localhost:1234/v1/chat/completions"
MODEL = "qwen3.6-27b"
LMS = str(Path.home() / ".lmstudio/bin/lms")
HOURS = 24
MAX_ITEMS = 25
ENV_PATH = Path(__file__).parent / ".env"


def load_env():
    if not ENV_PATH.exists():
        return {}
    return dict(
        line.strip().split("=", 1)
        for line in ENV_PATH.read_text().splitlines()
        if "=" in line and not line.startswith("#")
    )


def fetch(url, timeout=30):
    req = urllib.request.Request(
        url,
        headers={
            # 일부 사이트(긱뉴스 등)가 봇 UA를 403 차단해서 브라우저 UA 사용
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        },
    )
    return urllib.request.urlopen(req, timeout=timeout).read()


ATOM = "{http://www.w3.org/2005/Atom}"


def parse_rss(name, xml_bytes, cutoff):
    items = []
    root = ET.fromstring(xml_bytes)
    # RSS 2.0 (item/pubDate) 과 Atom (entry/updated) 둘 다 지원
    entries = list(root.iter("item")) or list(root.iter(f"{ATOM}entry"))
    for it in entries:
        title = (it.findtext("title") or it.findtext(f"{ATOM}title") or "").strip()
        link = (it.findtext("link") or "").strip()
        if not link:
            el = it.find(f"{ATOM}link")
            link = el.get("href", "") if el is not None else ""
        desc = (
            it.findtext("description")
            or it.findtext(f"{ATOM}summary")
            or it.findtext(f"{ATOM}content")
            or ""
        ).strip()
        pub = it.findtext("pubDate") or it.findtext(f"{ATOM}updated")
        if not title or not pub:
            continue
        try:
            dt = parsedate_to_datetime(pub) if "," in pub else datetime.fromisoformat(pub)
        except (TypeError, ValueError):
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt < cutoff:
            continue
        # 설명에서 HTML 태그 대충 제거
        import re
        desc = re.sub(r"<[^>]+>", " ", desc)
        desc = re.sub(r"\s+", " ", desc).strip()[:300]
        items.append({"source": name, "title": title, "link": link, "desc": desc})
    return items


def collect():
    cutoff = datetime.now(timezone.utc) - timedelta(hours=HOURS)
    items = []
    for name, url in FEEDS.items():
        try:
            items.extend(parse_rss(name, fetch(url), cutoff)[: MAX_ITEMS // len(FEEDS)])
        except Exception as e:
            print(f"[warn] {name} 피드 실패: {e}", file=sys.stderr)
    return items


def ensure_model():
    ps = subprocess.run([LMS, "ps"], capture_output=True, text=True).stdout
    if MODEL not in ps:
        subprocess.run([LMS, "server", "start"], capture_output=True)
        subprocess.run(
            [LMS, "load", MODEL, "-y", "--context-length", "16384"],
            capture_output=True,
            timeout=300,
        )


def llm(prompt, max_tokens=6000, schema=None):
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.3,
        # 추론(thinking) 끄기 — 요약·선별 같은 간단한 작업에 추론 토큰 수천 개를 태우던 문제 해결
        # (/no_think, chat_template_kwargs는 이 모델에서 안 먹힘. 이 파라미터만 유효)
        "reasoning_effort": "none",
    }
    if schema:  # 답 형식을 JSON 스키마로 강제 (structured output)
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "out", "strict": True, "schema": schema},
        }
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        LM_URL, data=body, headers={"Content-Type": "application/json"}
    )
    resp = json.load(urllib.request.urlopen(req, timeout=900))
    return resp["choices"][0]["message"]["content"].strip()


PICK_N = 5


def pick(items):
    import re

    listing = "\n".join(
        f"{i + 1}. [{it['source']}] {it['title']} — {it['desc'][:150]}"
        for i, it in enumerate(items)
    )
    ans = llm(
        f"""아래 AI/개발 뉴스 목록에서 개발자에게 가장 중요한 {PICK_N}개의 번호를 골라라.
중복(같은 사건)·홍보성 글은 제외.
{preference_block()}
{listing}""",
        3000,
        schema={
            "type": "object",
            "properties": {
                "picks": {"type": "array", "items": {"type": "integer"}}
            },
            "required": ["picks"],
        },
    )
    nums = []
    try:
        raw = json.loads(ans)["picks"]
    except (ValueError, KeyError, TypeError):
        raw = [int(x) for x in re.findall(r"\d+", ans or "")]  # 스키마 실패 시 폴백
    for n in raw:
        if 1 <= n <= len(items) and n not in nums:
            nums.append(n)
    if not nums:  # 파싱 실패 시 앞에서부터
        nums = list(range(1, PICK_N + 1))
    return [items[n - 1] for n in nums[:PICK_N]]


def article_text(url):
    import html as html_module
    import re

    raw = None
    # 1차: trafilatura (본문만 깔끔하게 추출, 광고·메뉴 제거)
    try:
        import trafilatura

        raw = fetch(url).decode("utf-8", "ignore")
        text = trafilatura.extract(raw)
        if text:
            return text[:2500]
    except Exception:
        pass
    # 2차 폴백: <p> 태그 정규식
    try:
        if raw is None:
            raw = fetch(url).decode("utf-8", "ignore")
    except Exception:
        return ""
    paras = re.findall(r"<p[^>]*>(.*?)</p>", raw, re.S)
    text = " ".join(re.sub(r"<[^>]+>", " ", p) for p in paras)
    text = html_module.unescape(re.sub(r"\s+", " ", text)).strip()
    return text[:2500]


def summarize_article(item):
    body = article_text(item["link"]) or item["desc"]
    out = llm(
        f"""다음 기사를 한국어 5줄로 요약하라.
- 각 줄은 "- "로 시작, 한 문장씩.
- 앞 4줄: 기사의 핵심 사실.
- 마지막 줄: 이 뉴스가 중요한 이유를 한 문장으로 (문장을 완성할 것).
- 다른 말·헤더·마크다운 금지. 딱 5줄만.

제목: {item['title']}
본문: {body}""",
        6000,
    )
    # 생각 토큰이 한도를 다 먹어 빈 답이 오면 설명문으로 대체
    return out or f"- {item['desc'][:200]}"


def send_telegram(text, env, buttons=None, chat_id=None):
    token = env["TELEGRAM_TOKEN"]
    chat_id = chat_id if chat_id is not None else env["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    # 텔레그램 메시지 한도 4096자 → 3500자 단위로 분할
    chunks = [text[i : i + 3500] for i in range(0, len(text), 3500)]
    last_mid = None
    for idx, chunk in enumerate(chunks):
        params = {
            "chat_id": chat_id,
            "text": chunk,
            "disable_web_page_preview": "true",
        }
        if buttons and idx == len(chunks) - 1:  # 버튼은 마지막 조각에만
            params["reply_markup"] = json.dumps({"inline_keyboard": buttons})
        data = urllib.parse.urlencode(params).encode()
        resp = json.load(urllib.request.urlopen(url, data=data, timeout=30))
        last_mid = resp.get("result", {}).get("message_id")
    return last_mid  # 버튼이 붙는 마지막 조각의 message_id — 리액션↔기사 매핑에 사용


# ---- 피드백 수집 (👍👎 버튼 + 자유 답장) ----
STATE_PATH = Path(__file__).parent / "state.json"
RATINGS_PATH = Path(__file__).parent / "ratings.jsonl"
SENTLOG_PATH = Path(__file__).parent / "sent-log.jsonl"
SUBS_PATH = Path(__file__).parent / "subscribers.json"


def load_subs(env):
    """구독자 chat_id 목록. .env의 본인 채팅은 항상 포함."""
    subs = set()
    if SUBS_PATH.exists():
        subs = {int(c) for c in json.loads(SUBS_PATH.read_text())}
    own = env.get("TELEGRAM_CHAT_ID")
    if own:
        subs.add(int(own))
    return subs


def title_hash(title):
    import hashlib

    return hashlib.md5(title.encode()).hexdigest()[:10]


def collect_feedback(env):
    """어젯밤 이후 쌓인 버튼 클릭·리액션·답장을 ratings.jsonl에 저장."""
    token = env["TELEGRAM_TOKEN"]
    state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}
    offset = state.get("offset", 0)
    sent, sent_mid = {}, {}
    if SENTLOG_PATH.exists():
        for line in SENTLOG_PATH.read_text().splitlines():
            e = json.loads(line)
            sent[e["hash"]] = e["title"]
            if "mid" in e:
                sent_mid[e["mid"]] = e["title"]
    # allowed_updates를 주면 그 타입만 옴 → 리액션 추가하되 기존 것도 전부 명시
    allowed = urllib.parse.quote('["message","callback_query","message_reaction"]')
    try:
        resp = json.load(
            urllib.request.urlopen(
                f"https://api.telegram.org/bot{token}/getUpdates?offset={offset}&allowed_updates={allowed}",
                timeout=30,
            )
        )
    except Exception as e:
        print(f"[warn] 피드백 수집 실패: {e}", file=sys.stderr)
        return
    from datetime import datetime as dt

    subs_before = load_subs(env)
    subs = set(subs_before)
    count = 0
    with RATINGS_PATH.open("a") as f:
        for u in resp.get("result", []):
            offset = u["update_id"] + 1
            cq = u.get("callback_query")
            mr = u.get("message_reaction")
            msg = u.get("message")
            # 말을 건/반응한 채팅 = 구독자로 자동 등록 (피드백엔 누구 것인지 chat 기록)
            chat_id = (
                (cq or {}).get("message", {}).get("chat", {}).get("id")
                or (mr or {}).get("chat", {}).get("id")
                or (msg or {}).get("chat", {}).get("id")
            )
            if chat_id:
                subs.add(chat_id)
            if cq:
                label, _, h = cq.get("data", "").partition(":")
                if label in ("g", "b") and h in sent:
                    f.write(
                        json.dumps(
                            {
                                "ts": dt.now().isoformat(),
                                "label": "good" if label == "g" else "bad",
                                "title": sent[h],
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
                            {"callback_query_id": cq["id"], "text": "기록됨 ✅"}
                        ).encode(),
                        timeout=10,
                    )
                except Exception:
                    pass
            elif mr:
                # 메시지 더블탭 리액션 👍/👎 — message_id로 기사 역추적
                # (mid는 sent-log에 2026-09-24부터 기록 — 그 이전 기사는 매핑 불가)
                title = sent_mid.get(mr.get("message_id"))
                emojis = {
                    r.get("emoji")
                    for r in mr.get("new_reaction", [])
                    if r.get("type") == "emoji"
                }
                label = "good" if "👍" in emojis else "bad" if "👎" in emojis else ""
                if title and label:
                    f.write(
                        json.dumps(
                            {
                                "ts": dt.now().isoformat(),
                                "label": label,
                                "title": title,
                                "via": "reaction",
                                "chat": chat_id,
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                    count += 1
            elif msg and msg.get("text"):
                m = msg
                if m["text"].startswith("/"):
                    continue  # /start 같은 명령어는 피드백 아님 — 요청사항으로 오염 방지
                reply = m.get("reply_to_message", {}).get("text", "")
                if reply.startswith("📌"):
                    # 기사에 대한 답장 = 단어장 요청
                    lines = reply.splitlines()
                    title = lines[0].lstrip("📌 ").strip()
                    link = next(
                        (l.lstrip("🔗 ").strip() for l in lines if l.startswith("🔗")),
                        "",
                    )
                    f.write(
                        json.dumps(
                            {
                                "ts": dt.now().isoformat(),
                                "label": "vocab",
                                "text": m["text"],
                                "title": title,
                                "link": link,
                                "chat": chat_id,
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                else:
                    f.write(
                        json.dumps(
                            {
                                "ts": dt.now().isoformat(),
                                "label": "note",
                                "text": m["text"],
                                "chat": chat_id,
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                count += 1
    STATE_PATH.write_text(json.dumps({"offset": offset}))
    if count:
        print(f"[info] 피드백 {count}건 수집", file=sys.stderr)
    # 신규 구독자 등록 + 환영 메시지
    if subs != subs_before:
        SUBS_PATH.write_text(json.dumps(sorted(subs)))
        for cid in subs - subs_before:
            try:
                send_telegram(
                    """📰 dailyoscarnews 봇이에요

매일 아침 8시, AI/개발 뉴스 중 중요한 것만 골라 한국어 5줄 요약으로 보내드려요.

• 기사 밑 [👍 관심] [👎 별로] 버튼이나 메시지 더블탭 👍 리액션으로 취향을 기록할 수 있어요.
• 기사에 모르는 단어가 나오면, 그 기사 메시지에 '답장'으로 단어만 적어주세요. 초보용 설명을 만들어 보내드려요.""",
                    env,
                    chat_id=cid,
                )
                print(f"[info] 신규 구독자: {cid}", file=sys.stderr)
            except Exception:
                pass


# ---- 단어장: 기사 답장으로 남긴 단어를 옵시디언에 정리 ----
# 직접 파일 쓰기는 launchd(자동 실행)에서 macOS가 Documents 접근을 막으므로,
# 옵시디언 Local REST API(앱이 대신 씀)를 1순위로 쓰고 직접 쓰기는 폴백.
VAULT_DIR = Path.home() / "Documents/Obsidian Vault"
VOCAB_REL = "사이드프로젝트/daily-news/단어장"


def _obsidian_request(method, relpath, data=None, content_type=None):
    env = load_env()
    url = env.get("OBSIDIAN_API", "http://127.0.0.1:27123") + "/vault/" + urllib.parse.quote(relpath)
    headers = {"Authorization": "Bearer " + env.get("OBSIDIAN_KEY", "")}
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    return urllib.request.urlopen(req, timeout=15)


def vault_read(relpath):
    try:
        return _obsidian_request("GET", relpath).read().decode()
    except Exception:
        pass
    try:
        return (VAULT_DIR / relpath).read_text()
    except Exception:
        return None


def vault_write(relpath, content):
    try:
        _obsidian_request("PUT", relpath, content.encode(), "text/markdown")
        return True
    except Exception:
        pass
    try:
        p = VAULT_DIR / relpath
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return True
    except Exception as e:
        print(f"[warn] 볼트 저장 실패 ({relpath}): {e}", file=sys.stderr)
        return False


def process_vocab():
    import re

    if not RATINGS_PATH.exists():
        return
    for line in RATINGS_PATH.read_text().splitlines():
        e = json.loads(line)
        if e.get("label") != "vocab":
            continue
        words = [w.strip() for w in re.split(r"[,\n/]+", e["text"]) if w.strip()]
        for word in words:
            safe = re.sub(r'[\\/:*?"<>|]', "_", word)[:50]
            relpath = f"{VOCAB_REL}/{safe}.md"
            src = f"- [{e.get('title', '?')}]({e.get('link', '')}) — {e['ts'][:10]}"
            existing = vault_read(relpath)
            if existing is not None:
                # 같은 단어를 다른 기사에서 또 물어보면 출처만 추가
                if e.get("link") and e["link"] not in existing:
                    vault_write(relpath, existing.rstrip() + "\n" + src + "\n")
                # 이미 있는 단어도 물어본 사람에겐 기존 설명을 보내줌
                body = existing.split(f"# {word}")[-1].split("## 출처")[0].strip()
                if body and e.get("chat"):
                    try:
                        send_telegram(f"📖 {word}\n\n{body}", load_env(), chat_id=e["chat"])
                    except Exception:
                        pass
                continue
            try:
                expl = llm(
                    f"""IT/개발 용어 '{word}'를 완전 초보에게 설명하라.
- 3~5문장, 쉬운 비유 하나 포함.
- 이 단어가 나온 뉴스 맥락: "{e.get('title', '')}"
- 마크다운 헤더·다른 말 금지. 설명만.""",
                    3000,
                )
            except Exception as ex:
                print(f"[warn] 단어 설명 실패 ({word}): {ex}", file=sys.stderr)
                continue
            if not expl:
                print(f"[warn] 단어 설명 빈 답 ({word}) — 다음 실행에서 재시도", file=sys.stderr)
                continue
            ok = vault_write(
                relpath,
                f"""---
tags: [단어장, daily-news]
created: {e['ts'][:10]}
---

# {word}

{expl}

## 출처
{src}
""",
            )
            if ok:
                print(f"[info] 단어장 저장: {word}", file=sys.stderr)
                # 물어본 사람에게 설명을 답장으로 전송
                if e.get("chat"):
                    try:
                        send_telegram(f"📖 {word}\n\n{expl}", load_env(), chat_id=e["chat"])
                    except Exception:
                        pass


def vocab_pending():
    """아직 노트가 안 만들어진 단어 요청이 있으면 True."""
    import re

    if not RATINGS_PATH.exists():
        return False
    for line in RATINGS_PATH.read_text().splitlines():
        e = json.loads(line)
        if e.get("label") != "vocab":
            continue
        for w in re.split(r"[,\n/]+", e["text"]):
            w = w.strip()
            if not w:
                continue
            safe = re.sub(r'[\\/:*?"<>|]', "_", w)[:50]
            if vault_read(f"{VOCAB_REL}/{safe}.md") is None:
                return True
    return False


def preference_block():
    """쌓인 피드백(본인 것만)을 pick 프롬프트용 취향 예시로 변환."""
    if not RATINGS_PATH.exists():
        return ""
    own = load_env().get("TELEGRAM_CHAT_ID", "")
    good, bad, notes = [], [], []
    for line in RATINGS_PATH.read_text().splitlines():
        e = json.loads(line)
        # chat 없는 예전 기록 = 본인 것. 다른 구독자 피드백은 내 취향 학습에서 제외
        if e.get("chat") and str(e["chat"]) != own:
            continue
        if e["label"] == "good":
            good.append(e["title"])
        elif e["label"] == "bad":
            bad.append(e["title"])
        elif e["label"] == "note":
            notes.append(e["text"])
    parts = []
    if good:
        parts.append("사용자가 좋아한 기사: " + " / ".join(good[-15:]))
    if bad:
        parts.append("사용자가 싫어한 기사: " + " / ".join(bad[-15:]))
    if notes:
        parts.append("사용자 요청사항: " + " / ".join(notes[-10:]))
    return ("\n이 사용자의 취향을 최우선으로 반영하라:\n" + "\n".join(parts) + "\n") if parts else ""


def main():
    dry = "--dry" in sys.argv
    env = load_env()
    if not dry:
        if "TELEGRAM_TOKEN" not in env:
            print("오류: .env에 TELEGRAM_TOKEN/TELEGRAM_CHAT_ID 필요", file=sys.stderr)
            sys.exit(1)
        # 피드백 수집은 뉴스·모델과 무관하게 항상 실행 — 안 가져간 반응은 텔레그램이 ~24시간 뒤 폐기
        try:
            collect_feedback(env)  # 어제 이후 쌓인 👍👎·리액션·답장 반영
        except Exception as e:
            print(f"[warn] 피드백 수집 실패: {e}", file=sys.stderr)
    if "--feedback-only" in sys.argv:
        # 다이제스트 없이 피드백·단어장만 처리하는 추가 실행용 (17시 잡)
        if not dry and vocab_pending():
            ensure_model()
            try:
                process_vocab()
            except Exception as e:
                print(f"[warn] 단어장 처리 실패: {e}", file=sys.stderr)
        return
    items = collect()
    if not items:
        print("지난 24시간 새 글 없음", file=sys.stderr)
        return
    ensure_model()
    if not dry:
        # 단어장은 부가 기능 — 실패해도 다이제스트 발송은 계속돼야 함
        try:
            process_vocab()  # 기사 답장으로 남긴 단어 → 옵시디언 단어장
        except Exception as e:
            print(f"[warn] 단어장 처리 실패: {e}", file=sys.stderr)
    picked = pick(items)
    date = datetime.now().strftime("%m/%d")
    subs = load_subs(env)
    if not dry:
        for cid in subs:
            try:
                send_telegram(f"🗞 AI/개발 다이제스트 {date} — 오늘 {len(picked)}건", env, chat_id=cid)
            except Exception as e:
                print(f"[warn] 헤더 전송 실패 (chat {cid}): {e}", file=sys.stderr)
    for it in picked:
        try:
            summary = summarize_article(it)
        except Exception as e:
            print(f"[warn] 요약 실패 ({it['title'][:30]}): {e}", file=sys.stderr)
            summary = f"- {it['desc'][:200]}"
        msg = f"📌 {it['title']}\n\n{summary}\n\n🔗 {it['link']}"
        if dry:
            print(msg, "\n" + "─" * 30)
            continue
        h = title_hash(it["title"])
        buttons = [[
            {"text": "👍 관심", "callback_data": f"g:{h}"},
            {"text": "👎 별로", "callback_data": f"b:{h}"},
        ]]
        for cid in subs:
            try:
                mid = send_telegram(msg, env, buttons=buttons, chat_id=cid)
            except Exception as e:
                print(f"[warn] 기사 전송 실패 (chat {cid}): {e}", file=sys.stderr)
                # 봇을 차단했거나 채팅이 사라진 구독자는 제외
                if any(s in str(e) for s in ("403", "chat not found", "blocked")):
                    subs.discard(cid)
                continue
            # mid = 구독자별 메시지의 message_id. 리액션(👍 더블탭) 역추적용
            with SENTLOG_PATH.open("a") as f:
                f.write(json.dumps({"hash": h, "title": it["title"], "mid": mid}, ensure_ascii=False) + "\n")
    if not dry:
        SUBS_PATH.write_text(json.dumps(sorted(subs)))
    print(f"전송 완료 ({len(items)}건 중 {len(picked)}건 요약, 구독자 {len(subs)}명)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # 실패를 조용히 삼키지 않고 텔레그램으로 알림
        import traceback

        traceback.print_exc()
        try:
            env = load_env()
            if "TELEGRAM_TOKEN" in env:
                send_telegram(
                    f"⚠️ daily-news 실행 실패\n{type(e).__name__}: {str(e)[:300]}\n로그: ~/news-digest/digest.log",
                    env,
                )
        except Exception:
            pass
        sys.exit(1)
