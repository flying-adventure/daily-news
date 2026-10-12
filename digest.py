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


PICK_N = 5  # 취향 기반 4개 + 취향 밖 와일드카드 1개


def pick(items, chat_id=None):
    import random
    import re

    listing = "\n".join(
        f"{i + 1}. [{it['source']}] {it['title']} — {it['desc'][:150]}"
        for i, it in enumerate(items)
    )
    ans = llm(
        f"""아래 AI/개발 뉴스 목록에서 개발자에게 가장 중요한 {PICK_N - 1}개의 번호를 "picks"에 골라라.
중복(같은 사건)·홍보성 글은 제외.
{preference_block(chat_id)}
추가로 "wildcard"에는 picks와 겹치지 않는 번호 하나를 골라라 — 이 사용자의 평소 취향과 다른 주제로,
시야를 넓혀줄 만한 의외의 기사. 양질이되 취향 예시와 다른 분야일수록 좋다.
{listing}""",
        3000,
        schema={
            "type": "object",
            "properties": {
                "picks": {"type": "array", "items": {"type": "integer"}},
                "wildcard": {"type": "integer"},
            },
            "required": ["picks", "wildcard"],
        },
    )
    nums = []
    wild = None
    try:
        data = json.loads(ans)
        raw = data["picks"]
        wild = data.get("wildcard")
    except (ValueError, KeyError, TypeError):
        raw = [int(x) for x in re.findall(r"\d+", ans or "")]  # 스키마 실패 시 폴백
    for n in raw:
        if 1 <= n <= len(items) and n not in nums:
            nums.append(n)
    nums = nums[: PICK_N - 1]
    if not nums:  # 파싱 실패 시 앞에서부터
        nums = list(range(1, min(PICK_N - 1, len(items)) + 1))
    picked = [items[n - 1] for n in nums]
    # 와일드카드: picks와 겹치지 않는 유효 번호면 그것, 아니면 남은 것 중 랜덤
    if wild and 1 <= wild <= len(items) and wild not in nums:
        w = items[wild - 1]
    elif len(nums) < len(items):
        pool = [it for i, it in enumerate(items) if (i + 1) not in nums]
        w = random.choice(pool)
    else:
        w = None
    if w:
        w = dict(w)  # items는 구독자별로 재사용 — 공유 dict에 표시 남기지 않게 복사
        w["wild"] = True
        picked.append(w)
    return picked


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


def summarize_article(item, body=None):
    if body is None:  # eval에서 저장된 본문을 넘길 수 있게
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
            sent[e["hash"]] = e
            if "mid" in e:
                sent_mid[e["mid"]] = e
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
                                "title": sent[h]["title"],
                                "link": sent[h].get("link", ""),
                                "chat": chat_id,
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
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
                        timeout=10,
                    )
                except Exception:
                    pass
            elif mr:
                # 메시지 리액션 👍/👎/⭐ — message_id로 기사 역추적
                # (mid는 sent-log에 2026-09-24부터 기록 — 그 이전 기사는 매핑 불가)
                entry = sent_mid.get(mr.get("message_id"))
                emojis = {
                    r.get("emoji")
                    for r in mr.get("new_reaction", [])
                    if r.get("type") == "emoji"
                }
                label = (
                    "good" if "👍" in emojis
                    else "bad" if "👎" in emojis
                    else "bookmark" if "⭐" in emojis  # ⭐ = 나중에 읽기
                    else ""
                )
                if entry and label:
                    f.write(
                        json.dumps(
                            {
                                "ts": dt.now().isoformat(),
                                "label": label,
                                "title": entry["title"],
                                "link": entry.get("link", ""),
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
                if reply.startswith(("📌", "🎲")):
                    # 기사에 대한 답장 = 단어장 요청 (🎲은 취향 밖 와일드카드 기사)
                    lines = reply.splitlines()
                    title = lines[0].lstrip("📌🎲 ").strip()
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
    state["offset"] = offset  # 다른 키(site_hash 등)는 보존
    STATE_PATH.write_text(json.dumps(state))
    if count:
        print(f"[info] 피드백 {count}건 수집", file=sys.stderr)
    # 같은 사람이 같은 기사에 여러 번 누른 것(연타/의견 변경)은 최신만 유지
    dedupe_ratings()
    # 신규 구독자 등록 + 환영 메시지
    if subs != subs_before:
        SUBS_PATH.write_text(json.dumps(sorted(subs)))
        for cid in subs - subs_before:
            try:
                welcome = """📰 dailyoscarnews 봇이에요

매일 아침 8시, AI/개발 뉴스 중 중요한 것만 골라 한국어 5줄 요약으로 보내드려요.

• 기사 밑 [👍 관심] [👎 별로] 버튼이나 메시지 더블탭 👍 리액션으로 취향을 기록할 수 있어요.
• 기사에 모르는 단어가 나오면, 그 기사 메시지에 '답장'으로 단어만 적어주세요. 초보용 설명을 만들어 보내드려요."""
                if site_url(env):
                    welcome += "\n• 🔖 저장 버튼으로 나중에 읽을 기사를 모아두면, 다이제스트 첫 메시지의 📚 내 저장함에서 볼 수 있어요."
                send_telegram(welcome, env, chat_id=cid)
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


WEEKLY_PATH = Path(__file__).parent / "weekly.json"


def send_weekly_report(env):
    """일요일: 지난 7일 피드백·북마크를 사람별로 요약 발송. 하루 1번만."""
    from collections import Counter, defaultdict

    state = json.loads(WEEKLY_PATH.read_text()) if WEEKLY_PATH.exists() else {}
    today = datetime.now().strftime("%Y-%m-%d")
    if state.get("last") == today or not RATINGS_PATH.exists():
        return
    own = int(env.get("TELEGRAM_CHAT_ID", "0"))
    cutoff = datetime.now() - timedelta(days=7)
    per = defaultdict(lambda: {"good": 0, "bad": 0, "gt": Counter(), "bt": Counter(), "bm": []})
    for line in RATINGS_PATH.read_text().splitlines():
        e = json.loads(line)
        try:
            if datetime.fromisoformat(e["ts"]) < cutoff:
                continue
        except (KeyError, ValueError):
            continue
        cid = e.get("chat") or own  # 예전 기록 = 본인 것
        p = per[cid]
        if e["label"] == "good":
            p["good"] += 1
            p["gt"].update(e.get("tags", []))
        elif e["label"] == "bad":
            p["bad"] += 1
            p["bt"].update(e.get("tags", []))
        elif e["label"] == "bookmark":
            p["bm"].append((e["title"], e.get("link", "")))
    for cid, p in per.items():
        if not (p["good"] or p["bad"] or p["bm"]):
            continue
        lines = ["📊 이번 주 뉴스 리포트", ""]
        if p["good"]:
            tops = ", ".join(t for t, _ in p["gt"].most_common(5))
            lines.append(f"👍 {p['good']}건" + (f" — 좋아한 주제: {tops}" if tops else ""))
        if p["bad"]:
            tops = ", ".join(t for t, _ in p["bt"].most_common(5))
            lines.append(f"👎 {p['bad']}건" + (f" — 싫어한 주제: {tops}" if tops else ""))
        if p["bm"]:
            lines += ["", "⭐ 이번 주 북마크:"]
            lines += [f"• {t} {l}".rstrip() for t, l in p["bm"]]
        try:
            send_telegram("\n".join(lines), env, chat_id=cid)
        except Exception as ex:
            print(f"[warn] 주간 리포트 실패 (chat {cid}): {ex}", file=sys.stderr)
    WEEKLY_PATH.write_text(json.dumps({"last": today}))


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


def tags_pending():
    """태그가 안 달린 good/bad/bookmark 피드백이 있으면 True."""
    if not RATINGS_PATH.exists():
        return False
    for line in RATINGS_PATH.read_text().splitlines():
        e = json.loads(line)
        if e.get("label") in ("good", "bad", "bookmark") and e.get("title") and "tags" not in e:
            return True
    return False


def tag_pending_ratings():
    """good/bad 피드백의 기사에 주제 태그를 달아 취향을 주제 단위로 집계 가능하게 함."""
    if not RATINGS_PATH.exists():
        return
    entries = [json.loads(l) for l in RATINGS_PATH.read_text().splitlines()]
    pending = [
        i
        for i, e in enumerate(entries)
        if e.get("label") in ("good", "bad", "bookmark") and e.get("title") and "tags" not in e
    ]
    if not pending:
        return
    titles = [entries[i]["title"] for i in pending]
    listing = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(titles))
    try:
        ans = llm(
            f"""각 기사 제목의 주제를 나타내는 태그를 2~4개씩 뽑아라.
- 태그는 짧은 명사형 한국어 (예: AI업계, 오픈소스, 보안, 프레임워크, 하드웨어, 스타트업).
- 여러 기사가 같은 주제면 반드시 같은 태그를 써라 — 집계에 쓴다.
- items에는 번호 n과 tags만.
{listing}""",
            4000,
            schema={
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "n": {"type": "integer"},
                                "tags": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["n", "tags"],
                        },
                    }
                },
                "required": ["items"],
            },
        )
        mapping = {it["n"]: it["tags"] for it in json.loads(ans).get("items", [])}
    except Exception as ex:
        print(f"[warn] 태그 추출 실패: {ex}", file=sys.stderr)
        return
    n = 0
    for pos, i in enumerate(pending):
        tags = mapping.get(pos + 1)
        if tags:
            entries[i]["tags"] = tags
            n += 1
    if n:
        RATINGS_PATH.write_text(
            "\n".join(json.dumps(e, ensure_ascii=False) for e in entries) + "\n"
        )
        print(f"[info] 피드백 {n}건에 태그 부여", file=sys.stderr)


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


def preference_block(chat_id=None):
    """쌓인 피드백을 pick 프롬프트용 취향 블록으로 변환. chat_id별로 그 사람 것만.
    주제 태그 카운트(장기 취향) + 최근 제목(단기 취향) 둘 다 준다."""
    if not RATINGS_PATH.exists():
        return ""
    from collections import Counter

    own = load_env().get("TELEGRAM_CHAT_ID", "")
    cid = str(chat_id) if chat_id is not None else own
    good, bad, notes = [], [], []
    good_tags, bad_tags = Counter(), Counter()
    for line in RATINGS_PATH.read_text().splitlines():
        e = json.loads(line)
        # chat 없는 예전 기록 = 본인 것. 다른 사람 피드백은 이 사람 취향에 안 섞임
        e_chat = str(e["chat"]) if e.get("chat") else own
        if e_chat != cid:
            continue
        if e["label"] in ("good", "bookmark"):  # 저장 = 👍보다 강한 관심 신호
            if e["title"] in good:  # 👍와 저장이 겹치면 한 번만
                continue
            good.append(e["title"])
            good_tags.update(e.get("tags", []))
        elif e["label"] == "bad":
            bad.append(e["title"])
            bad_tags.update(e.get("tags", []))
        elif e["label"] == "note":
            notes.append(e["text"])
    parts = []
    if good_tags:
        parts.append(
            "좋아하는 주제: " + ", ".join(f"{t}({n})" for t, n in good_tags.most_common(8))
        )
    if bad_tags:
        parts.append(
            "싫어하는 주제: " + ", ".join(f"{t}({n})" for t, n in bad_tags.most_common(8))
        )
    if good:
        parts.append("최근 좋아한 기사: " + " / ".join(good[-5:]))
    if bad:
        parts.append("최근 싫어한 기사: " + " / ".join(bad[-5:]))
    if notes:
        parts.append("사용자 요청사항: " + " / ".join(notes[-10:]))
    return ("\n이 사용자의 취향을 최우선으로 반영하라:\n" + "\n".join(parts) + "\n") if parts else ""


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
        # 일요일 9시 이후 첫 실행 때 주간 리포트 발송
        if not dry:
            now = datetime.now()
            if now.weekday() == 6 and now.hour >= 9:
                try:
                    send_weekly_report(env)
                except Exception as e:
                    print(f"[warn] 주간 리포트 실패: {e}", file=sys.stderr)
        # 다이제스트 없이 피드백·단어장·태그만 처리하는 추가 실행용 (5분 주기 잡)
        if not dry and (vocab_pending() or tags_pending()):
            ensure_model()
            try:
                process_vocab()
            except Exception as e:
                print(f"[warn] 단어장 처리 실패: {e}", file=sys.stderr)
            try:
                tag_pending_ratings()
            except Exception as e:
                print(f"[warn] 태그 부여 실패: {e}", file=sys.stderr)
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
        try:
            tag_pending_ratings()  # 피드백 기사에 주제 태그 부여 → 취향 주제 집계
        except Exception as e:
            print(f"[warn] 태그 부여 실패: {e}", file=sys.stderr)
    date = datetime.now().strftime("%m/%d")
    if dry:
        # 터미널 테스트는 본인 취향 한 세트만 출력
        for it in pick(items):
            try:
                summary = summarize_article(it)
            except Exception as e:
                print(f"[warn] 요약 실패 ({it['title'][:30]}): {e}", file=sys.stderr)
                summary = f"- {it['desc'][:200]}"
            emoji = "🎲" if it.get("wild") else "📌"
            print(f"{emoji} {it['title']}\n\n{summary}\n\n🔗 {it['link']}", "\n" + "─" * 30)
        return
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
        except Exception as e:
            print(f"[warn] 헤더 전송 실패 (chat {cid}): {e}", file=sys.stderr)
            if any(s in str(e) for s in ("403", "chat not found", "blocked")):
                subs.discard(cid)
            continue
        for it in picked:
            key = it["link"] or it["title"]
            if key not in summary_cache:
                try:
                    summary_cache[key] = summarize_article(it)
                except Exception as e:
                    print(f"[warn] 요약 실패 ({it['title'][:30]}): {e}", file=sys.stderr)
                    summary_cache[key] = f"- {it['desc'][:200]}"
            summary = summary_cache[key]
            if site and key not in one_cache:
                one_cache[key] = one_liner(it, summary)
            emoji = "🎲" if it.get("wild") else "📌"  # 와일드카드 = 취향 밖 기사 표시
            msg = f"{emoji} {it['title']}\n\n{summary}\n\n🔗 {it['link']}"
            h = title_hash(it["title"])
            buttons = [[
                {"text": "👍 관심", "callback_data": f"g:{h}"},
                {"text": "👎 별로", "callback_data": f"b:{h}"},
            ]]
            if site:
                buttons[0].append({"text": "🔖 저장", "callback_data": f"s:{h}"})
            try:
                mid = send_telegram(msg, env, buttons=buttons, chat_id=cid)
            except Exception as e:
                print(f"[warn] 기사 전송 실패 (chat {cid}): {e}", file=sys.stderr)
                # 봇을 차단했거나 채팅이 사라진 구독자는 제외
                if any(s in str(e) for s in ("403", "chat not found", "blocked")):
                    subs.discard(cid)
                continue
            # mid = 구독자별 메시지의 message_id. 리액션(👍/⭐ 더블탭) 역추적용
            with SENTLOG_PATH.open("a") as f:
                f.write(
                    json.dumps(
                        {"hash": h, "title": it["title"], "link": it["link"], "mid": mid, "one": one_cache.get(key, "")},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
    SUBS_PATH.write_text(json.dumps(sorted(subs)))
    print(f"전송 완료 ({len(items)}건, 구독자 {len(subs)}명)")


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
