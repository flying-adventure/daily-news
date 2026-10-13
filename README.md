# daily-news 🗞

**매일 아침 8시, 텔레그램으로 IT·AI 뉴스 5개를 한국어 요약으로 받아보는 서비스.**
👍/👎를 누를수록 내 취향에 맞는 기사를 골라줍니다.

뉴스를 고르고 요약하는 AI는 전부 만든 사람의 맥에서 돌아갑니다. 외부 AI 서비스를 쓰지 않아 요금이 없고, 내 반응이 다른 회사로 넘어가지 않습니다.

## 써보고 싶다면

1. 텔레그램에서 **`@ITnews_oscarthegrouch_bot`** 을 검색하거나 [t.me/ITnews_oscarthegrouch_bot](https://t.me/ITnews_oscarthegrouch_bot) 을 엽니다. 대화방 이름은 `dailyoscarnews`로 보여요.
2. 아래쪽 **시작** 버튼을 누릅니다. `/start`를 보내도 같아요.
3. 환영 메시지가 오면 가입 끝. **다음날 아침 8시부터** 뉴스가 옵니다.

그만 받고 싶으면 봇을 **차단**하면 됩니다. 다음 발송 때 명단에서 자동으로 빠져요.

## 매일 받는 것

```
🗞 AI/개발 다이제스트 10/14 — 오늘 5건            [🏠 내 뉴스방]

📌 기사 제목
- 한국어 5줄 요약
🔗 원문 링크                        [👍 관심] [👎 별로] [🔖 저장]

  … 📌 4개 (내 취향 기반)

🎲 기사 제목                        ← 1개는 일부러 취향 밖에서
```

- **어디서 고르나**: 긱뉴스, Hacker News(추천 100점 이상), TechCrunch AI에 지난 24시간 동안 올라온 글
- **📌 4개는 내 취향, 🎲 1개는 새로움 칸**: 좋아하는 것만 받다 보면 보는 세상이 좁아져서(필터 버블), 하나는 평소 취향과 다른 주제로 골라요
- **사람마다 따로 골라요**: 내가 누른 👍/👎는 내 선별에만 쓰이고, 다른 구독자 취향과 섞이지 않아요. 같은 날이어도 사람마다 받는 기사가 다를 수 있어요

## 이렇게 쓰면 더 좋아요

| 하고 싶은 것 | 방법 |
|---|---|
| 취향 알려주기 | 기사 밑 **👍 관심 / 👎 별로** 버튼, 또는 메시지를 두 번 탭해서 👍 리액션. 다음날 선별부터 반영 |
| 나중에 읽기 | **🔖 저장**. 뉴스방 저장함에 모이고, 👍보다 강한 관심으로 취급 |
| 모르는 단어 묻기 | 그 기사 메시지에 **답장**으로 단어만 적기. 초보용 설명이 답장으로 옴 |
| 지난 기사 찾기 | "지난주 오픈AI 기사 뭐였지?"처럼 질문. 그동안 보낸 기사에서 찾아 답해줌 |
| 주제 빼기 / 챙기기 | `/skip 코인`이면 그 주제 제외, `/more 보안`이면 우선 선별 |
| 그 밖의 요청 | "보안 기사 더 많이"처럼 자유롭게 보내기. 30일 동안 선별에 참고 |

**🏠 내 뉴스방**: 매일 첫 메시지의 버튼을 누르면 나만의 웹페이지가 열려요. 📚 저장함, 🗞 지난 다이제스트(30일), 👍 좋아요 탭이 있고, 매일 다른 기니피그가 화면에서 놀고 있어요. 주소를 아는 사람은 누구나 열 수 있으니 공유하지 마세요.

**📊 주간 리포트**: 일요일 오전에 지난 7일 동안 좋아한/싫어한 주제와 저장한 기사를 정리해서 보내줘요.

## 알아두면 좋은 것

- 개인 맥에서 돌아가는 취미 프로젝트예요. 맥이 잠들어 있으면 8시 발송이나 버튼 반응이 늦어질 수 있고, 깨어나면 밀린 것부터 처리해요. 뉴스방 웹페이지는 맥이 꺼져 있어도 열려요.
- 누른 버튼과 보낸 메시지는 취향 반영을 위해 만든 사람의 맥에 저장돼요. 다른 AI 회사로 보내지 않아요.

---

# 직접 만들어 돌리고 싶다면 (개발자용)

로컬 LLM이 뉴스를 골라 요약해서 텔레그램으로 보내는 파이썬 프로젝트입니다. 외부 AI API 없이 **모든 추론이 맥에서** 돌아갑니다. API 요금이 0원이고 무제한이며, 데이터가 컴퓨터 밖으로 나가지 않습니다.

```
RSS 수집  →  로컬 LLM 선별·요약  →  텔레그램 발송  →  매일 08:00 자동 실행
(파이썬)     (Qwen3.6-27B via         (봇 API)          (launchd)
              LM Studio)
                        ↕
              상시 데몬 (버튼·리액션·구독·단어·질문 즉시 처리)
```

## 기술 특징

- **선별**: LLM이 취향 기반 4건과 취향 밖 와일드카드 1건(🎲)을 고름. JSON 스키마로 출력을 강제해 파싱이 안정적임
- **요약**: trafilatura로 기사 본문을 추출해 건당 5줄 한국어 요약과 링크를 만듦
- **피드백 루프**: 👍/👎 버튼, 리액션, 🔖 저장으로 구독자별 취향을 수집함. 주제 태그 집계(장기 취향)와 최근 제목(단기 취향)을 선별 프롬프트에 넣음. 쌓인 데이터는 LoRA 파인튜닝에 쓸 예정
- **구독자**: `/start`하거나 말을 건 사람을 자동 등록함. 봇 차단자는 자동으로 제외. 피드백은 `chat` 단위로 나눠 사람마다 따로 선별함
- **단어장**: 기사에 답장으로 단어를 받으면 LLM이 초보용 설명을 만듦. 텔레그램으로 답장하고, 옵시디언 볼트에도 노트로 저장함(출처 링크 포함)
- **질문 답변 (RAG)**: 보낸 기사를 `archive.jsonl`에 쌓아 임베딩함. 질문이 오면 코사인 유사도 top3 기사를 근거로 답변함
- **실시간 응답**: `daemon.py`는 상시 떠 있는 long-poll 프로세스로, 위 반응을 즉시 처리함 (launchd KeepAlive)
- **뉴스방 웹페이지**: 사람별 비밀 주소(`/u/<토큰>/`)에 저장함, 지난 다이제스트, 좋아요 탭이 있음. 다크+초록 픽셀 테마, 시간대·서울 날씨 배너, 오늘의 기니피그(6마리)를 넣었음. 내용이 바뀐 때만 Cloudflare Pages(무료)에 자동 업로드함. `SITE_URL`이 없으면 이 기능 전체가 꺼짐
- **실패 알림**: 실행이 죽으면 에러를 텔레그램으로 보냄. 조용히 실패하지 않음
- **의존성**: 파이썬 표준 라이브러리와 `trafilatura` 하나

## 요구 사항

- Apple Silicon Mac (통합메모리 32GB+ 권장 — 27B 4bit 모델 기준)
- [LM Studio](https://lmstudio.ai) + 모델 (기본값: `qwen3.6-27b` GGUF Q4_K_M)
- 텔레그램 봇 토큰 ([@BotFather](https://t.me/BotFather)에서 1분)
- (선택) 옵시디언 + Local REST API 플러그인 — 단어장 기능용
- (선택) Cloudflare 무료 계정 — 뉴스방 웹페이지용

## 설치

```bash
git clone https://github.com/flying-adventure/daily-news.git ~/news-digest
cd ~/news-digest
python3 -m venv venv && venv/bin/pip install trafilatura
cp .env.example .env   # 토큰 채우기
```

모델 준비 (LM Studio 설치 후):

```bash
lms get qwen3.6-27b --gguf -y
lms load qwen3.6-27b -y --context-length 16384
```

테스트:

```bash
venv/bin/python3 digest.py --dry             # 전송 없이 터미널 출력
venv/bin/python3 digest.py                   # 텔레그램 발송
venv/bin/python3 digest.py --feedback-only   # 피드백 수집 + 단어장만 처리
```

매일 08:00 자동 실행 (`~/Library/LaunchAgents/com.example.news-digest.plist`):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.example.news-digest</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/YOU/news-digest/venv/bin/python3</string>
        <string>/Users/YOU/news-digest/digest.py</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict><key>Hour</key><integer>8</integer><key>Minute</key><integer>0</integer></dict>
    <key>StandardOutPath</key><string>/Users/YOU/news-digest/digest.log</string>
    <key>StandardErrorPath</key><string>/Users/YOU/news-digest/digest.log</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.example.news-digest.plist
```

버튼·답장에 바로 반응하는 상시 데몬 (`com.example.news-daemon.plist`) — 위 plist에서 `Label`, 실행 파일(`daemon.py`), 로그 파일 이름만 바꾸고, `StartCalendarInterval` 대신 아래 두 줄을 넣습니다. 꺼지면 launchd가 다시 띄워줍니다:

```xml
<key>RunAtLoad</key><true/>
<key>KeepAlive</key><true/>
```

코드나 `.env`를 바꾼 뒤엔 데몬을 재시작해야 반영됩니다: `launchctl kickstart -k gui/$(id -u)/com.example.news-daemon`

(선택) 뉴스방 웹페이지 — Cloudflare 무료 계정이면 됨 (카드 등록·도메인 추가 불필요):

```bash
# .env에 SITE_URL, PAGES_PROJECT, CLOUDFLARE_API_TOKEN(권한: Account → Cloudflare Pages → Edit),
# CLOUDFLARE_ACCOUNT_ID, NPX(which npx 결과) 추가 후 — 프로젝트는 처음 한 번만 생성
set -a; source <(grep -E '^CLOUDFLARE_' .env); set +a
npx --yes wrangler@4 pages project create daily-news --production-branch main
```

페이지 틀과 그림은 `web/` 폴더에 있습니다 — 저장소를 통째로 받으면 같이 옵니다. 내 페이지 제목에 이름을 넣으려면 `.env`에 `SITE_NAME=이름`을 추가합니다.

자기 도메인을 쓰려면 Pages 프로젝트의 Custom domains에 서브도메인을 추가하고, 도메인 업체 DNS에 `CNAME <서브도메인> → (Pages가 알려준 *.pages.dev 주소)`를 넣는다 — 프로젝트 이름이 이미 쓰이고 있으면 뒤에 글자가 붙으므로 꼭 대시보드에 나온 주소를 쓸 것.

## 최근 개선 (2026-10-13)

- **📚 저장함 → 🏠 뉴스방**: 다크+초록 픽셀 테마, 저장함·지난 다이제스트·좋아요 3탭, 시간대·날씨(비) 배너
- **오늘의 기니피그**: 6마리 중 매일 1마리. 세수·상추 먹기·팝콘 점프·식빵 자세 등 9가지 동작. PC에선 가끔 커서를 따라오고, 휴대폰에선 화면을 돌아다님

## 최근 개선 (2026-10-12)

- **구독자별 개인화 선별**: 구독자마다 자기 피드백으로 따로 선별 — 사람마다 다른 5개 수신. 겹치는 기사는 요약 캐시로 재사용
- **피드백 중복 제거**: 같은 사람이 같은 기사에 연타/의견 변경(👍→👎)하면 최신 것만 유지 (`dedupe_ratings`)
- **취향 주제 태그**: 피드백 기사마다 LLM이 주제 태그 2~4개 추출 → "좋아하는 주제: 보안(6), 오픈소스(3)" 형태로 집계해 선별 프롬프트에 주입. 제목 나열 대신 장기 취향(태그 카운트)+단기 취향(최근 제목) 조합
- **~~⭐ 북마크 리액션~~ → 🔖 저장 버튼**: ⭐는 텔레그램이 허용하는 리액션이 아니라 애초에 누를 수 없었음 (아래 트러블슈팅) — 기사 밑 🔖 저장 버튼으로 대체
- **요약 품질 evals** (`eval_summaries.py`): 고정 테스트셋 + LLM-as-judge 4개 기준 채점 (accuracy/format/coverage/korean, 1~5점). `build`로 테스트셋 생성, `run`으로 평가 — 프롬프트·모델 변경 시 점수 비교용. 첫 베이스라인: acc 5.0 / fmt 5.0 / cov 4.3 / kor 4.9
- **정형 명령어**: `/skip 주제` → 그 주제 기사 제외, `/more 주제` → 우대 선별
- **질문 답변 (RAG)**: 봇에 "기사 제목 뭐였지?"식 질문 → 아카이브 임베딩 검색(코사인 유사도 top3) → 근거 기사로 답변. 발송 기사는 `archive.jsonl`에 자동 축적
- **상시 폴링 데몬** (`daemon.py`): launchd KeepAlive 상시 프로세스 — 5분 폴링 대체, getUpdates long-poll로 반응 즉시 처리
- **그 외**: 요청사항 30일 유효기간, sent-log 2000건 상한, 가입 7일+무활동 구독자 1회 리마인드
- **주간 리포트**: 일요일 오전에 지난 7일간 평가 수치·좋아한/싫어한 주제·북마크 목록을 사람별로 발송
- **🔖 저장 + 저장함 웹페이지**: 기사 버튼에 🔖 저장, 다이제스트 첫 메시지에 저장함 링크(지금은 🏠 내 뉴스방). 저장은 👍보다 강한 취향 신호로 선별·주제 태그에 반영

## 최근 개선 (2026-09-24)

- **피드백 수집 시점 버그 수정**: 새 글이 없는 날 early return으로 수집이 스킵돼, 누른 반응이 텔레그램 서버의 ~24시간 보관 기한을 넘겨 소실되던 문제 → 수집을 `main()` 맨 앞으로 이동
- **리액션 수집**: 메시지 더블탭 👍/👎도 피드백으로 인식 (`getUpdates`의 `allowed_updates`에 `message_reaction` 명시 + `message_id`로 기사 역추적)
- **구독자 기능**: `/start`한 사람에게 자동 등록 + 소개 메시지 + 다이제스트 발송. 차단자 자동 정리
- **피드백 발신자 구분**: 모든 피드백에 `chat` 기록 — 남의 취향이 내 학습 데이터를 오염하지 않게
- **단어 설명 답장**: 단어 요청 시 설명을 물어본 사람에게도 전송 (기존엔 볼트에만 저장)
- **5분 간격 피드백 실행**: `--feedback-only` 모드 추가 — 환영 메시지·단어 답장이 사실상 실시간
- **요약 품질·속도**: 추론 모드 끄기(`reasoning_effort: "none"`)로 요약 338초 → ~20초, 마지막 줄 끊김 수정
- **취향 밖 와일드카드**: 5개 중 4개는 취향 기반, 1개는 취향과 다른 주제의 기사(🎲 표시) — 피드백 루프가 강해질수록 생기는 필터 버블 완화

## 만들면서 겪은 문제들

실제로 부딪힌 순서대로. 같은 삽질을 아낄 수 있길.

| 문제 | 원인 | 해결 |
|---|---|---|
| `lms get` 다운로드가 1~2분마다 타임아웃 | HF 연결당 속도 제한 + 클라이언트 타임아웃 | HF에서 curl 병렬 / aria2c 분할 다운로드 (3배 빨라짐) |
| MLX 모델이 `lms ls`에 안 나타남 | LM Studio 스캐너가 신형 qwen3_5 아키텍처 MLX를 인덱스 못 하는 버그 | GGUF 포맷으로 우회 |
| LLM 요청이 HTTP 400 | 컨텍스트 8192로 로드됨 — 한국어(글자당 ~1토큰) 기사에서 초과 | `--context-length 16384`로 로드 |
| 추론(thinking) 모델이 빈 답 반환 | 생각 토큰이 `max_tokens`를 전부 소모 | max_tokens 넉넉히 + 빈 답 폴백 |
| 긱뉴스 RSS 파싱 0건 | RSS 2.0이 아니라 Atom 형식 | 파서에 Atom 지원 추가 |
| 기사 본문 페이지 403 | 봇 User-Agent 차단 (RSS는 허용) | 브라우저 UA 사용 |
| launchd 자동 실행에서만 옵시디언 저장 실패 | macOS TCC가 백그라운드 프로세스의 Documents 접근 차단 | Obsidian Local REST API 경유로 우회 |
| 8시에 다이제스트가 안 옴 | 맥이 잠들어 있으면 launchd가 대기 | 다음 깨어날 때 자동 실행됨 (정상 동작) |
| 요약 마지막 줄이 미완성 문장으로 끝남 | 프롬프트 `"마지막 줄은 '왜 중요한지'로 마무리"`를 모델이 글자 그대로 해석해 문자열 '왜 중요한지'로 문장을 끝냄 (토큰 절단 아님) | 지시를 "중요한 이유를 한 문장으로"로 명확히 수정 |
| 요약 1건에 338초 | 추론 모드가 답변 전 추론에 토큰 2,400+개 소모 | `reasoning_effort: "none"` 파라미터로 추론 끄기 → ~20초 (`/no_think`, `chat_template_kwargs`는 이 모델에서 무효) |
| 버튼을 눌렀는데 피드백이 안 쌓임 | 새 글 없는 날 `collect()` early return으로 `collect_feedback` 스킵 + 텔레그램 미수집 업데이트 ~24시간 뒤 폐기 | 피드백 수집을 파이프라인 맨 앞, 무조건 실행으로 이동 |
| 메시지 리액션(더블탭 👍)이 수집 안 됨 | `getUpdates`가 `message_reaction`을 기본값에서 제외 | `allowed_updates`에 3종 전부 명시 |
| `/start`가 "사용자 요청사항"으로 들어감 | 명령어도 일반 메시지로 기록됨 | `/`로 시작하는 메시지는 피드백에서 제외 |
| ⭐ 리액션 북마크가 하나도 안 쌓임 | ⭐는 텔레그램이 허용하는 리액션 이모지 목록(73개)에 없음 — 애초에 누를 수 없음 | 기사 버튼에 🔖 저장 추가, 같은 `bookmark` 라벨로 기록 |

## 로드맵

- [x] 요약 품질 평가 체계 (LLM-as-judge evals) — `eval_summaries.py`
- [ ] 👍👎 데이터로 소형 모델(4B) LoRA 파인튜닝 → 취향 분류기
- [x] 기사 아카이브 + RAG — "지난주 그 기사 뭐였지?" 질문 봇
- [x] long polling 데몬으로 실시간 응답 — `daemon.py`
- [ ] 모델 크기·양자화 벤치마크 (27B가 정말 필요한가?)

## 라이선스

MIT
