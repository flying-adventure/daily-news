# daily-news 🗞

로컬 LLM이 매일 아침 AI/개발 뉴스를 골라 요약해서 텔레그램으로 보내주는 개인 자동화 프로젝트.

외부 AI API 없이 **모든 추론이 내 맥에서** 돌아갑니다 — API 요금 0원, 무제한, 데이터가 컴퓨터 밖으로 나가지 않습니다.

```
RSS 수집  →  로컬 LLM 선별·요약  →  텔레그램 발송  →  매일 08:00 자동 실행
(파이썬)     (Qwen3.6-27B via         (봇 API)          (launchd)
              LM Studio)
                        ↕
              5분 간격 피드백 수집 (버튼·리액션·구독·단어 요청)
```

## 특징

- **뉴스 소스**: 긱뉴스, Hacker News(100점+), TechCrunch AI — 지난 24시간 글 수집
- **선별**: LLM이 중요한 5건만 선택 (JSON 스키마 강제 출력으로 파싱 안정성 확보)
- **요약**: trafilatura로 기사 본문을 추출해 건당 5줄 한국어 요약 + 링크
- **피드백 루프**: 기사마다 👍/👎 버튼 또는 메시지 더블탭 리액션 → 다음날 선별에 취향 반영 (few-shot). 쌓이면 LoRA 파인튜닝 데이터로 사용 예정
- **구독자**: 누구든 봇에게 `/start`하면 구독 — 소개 메시지를 보내고 다음날부터 다이제스트 수신. 봇 차단자는 자동 제외. 피드백은 발신자별로 구분해 모으되 취향 학습엔 소유자 것만 사용
- **단어장**: 기사에 답장으로 모르는 단어를 남기면, LLM이 초보용 설명을 만들어 텔레그램으로 답장 + 옵시디언 볼트에 노트로 저장 (출처 링크 포함)
- **준실시간 응답**: 5분 간격 피드백 전용 실행으로 `/start` 환영, 버튼 확인, 단어 답장이 몇 분 안에 처리 (상시 대기 데몬 없음)
- **실패 알림**: 실행이 죽으면 에러가 텔레그램으로 옴 — 조용한 실패 없음
- **의존성**: 파이썬 표준 라이브러리 + `trafilatura` 하나

## 요구 사항

- Apple Silicon Mac (통합메모리 32GB+ 권장 — 27B 4bit 모델 기준)
- [LM Studio](https://lmstudio.ai) + 모델 (기본값: `qwen3.6-27b` GGUF Q4_K_M)
- 텔레그램 봇 토큰 ([@BotFather](https://t.me/BotFather)에서 1분)
- (선택) 옵시디언 + Local REST API 플러그인 — 단어장 기능용

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

(선택) 5분 간격 피드백 실행 — 같은 plist에서 `StartCalendarInterval` 대신 아래를 쓰고 `--feedback-only` 인자를 추가:

```xml
<key>StartInterval</key><integer>300</integer>
```

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

## 로드맵

- [ ] 요약 품질 평가 체계 (LLM-as-judge evals)
- [ ] 👍👎 데이터로 소형 모델(4B) LoRA 파인튜닝 → 취향 분류기
- [ ] 기사 아카이브 + RAG — "지난주 그 기사 뭐였지?" 질문 봇
- [x] ~~long polling 데몬으로 실시간 응답~~ → 5분 간격 폴링으로 준실시간 달성 (데몬 없이)
- [ ] 모델 크기·양자화 벤치마크 (27B가 정말 필요한가?)

## 라이선스

MIT
