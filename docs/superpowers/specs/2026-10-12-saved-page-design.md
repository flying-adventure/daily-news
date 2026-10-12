# 저장함 웹페이지 설계 (news.starhana.kr)

작성일: 2026-10-12

## 목표

텔레그램 다이제스트의 기사를 "나중에 읽기"로 저장하고, 저장한 기사의 **링크 + 한줄요약**을 사람별 개인 웹페이지에서 본다.

성공 기준:
- 기사 메시지의 `🔖 저장` 버튼을 누르면 5분 안에 내 저장함 페이지에 반영된다.
- 다이제스트 첫 메시지의 `📚 내 저장함` 버튼으로 내 페이지가 열린다.
- 각 구독자는 자기가 저장한 것만 본다. 남의 저장함 주소는 알 수 없다.
- 맥이 잠들어 있어도 페이지는 열린다.

## 확정된 결정

| 항목 | 결정 | 이유 |
|---|---|---|
| 사람별 구분 | 개인 비밀 링크 `news.starhana.kr/u/<랜덤 토큰>/` | 로그인 없이 가장 단순. 내용이 공개 뉴스 링크라 유출 피해가 작음. 토큰은 재발급 가능 |
| 호스팅 | Cloudflare Pages (무료), 정적 HTML 직접 업로드 | 맥이 꺼져도 열림. 서버 코드 없음 |
| 주소 | 서브도메인 `news.starhana.kr` (가비아 DNS에 CNAME 1줄) | `starhana.kr` 본 주소는 이미 GitHub Pages에 연결돼 있어 건드리지 않음. 네임서버 이전 불필요 |
| 한줄요약 | 발송 시 LLM으로 별도 생성 | 5줄 요약의 한 줄을 재사용하는 것보다 품질이 좋음. 짧은 입력이라 건당 몇 초 |
| 취향 학습 | 저장 = 👍로 취급 (주제 태그도 부여) | 저장은 👍보다 강한 관심 신호 |
| 저장 기록 형식 | 기존 `bookmark` 라벨 재사용 | 다른 세션이 만든 "⭐ 리액션 = 북마크"가 이미 `bookmark`로 기록·주간 리포트에 집계됨. 단 ⭐는 텔레그램이 허용하는 리액션 이모지 73개에 없어 실제로는 발생 불가(2026-10-12 Bot API 문서 확인) → 🔖 버튼이 같은 라벨로 그 기능을 대신 살림 |

검토했지만 고르지 않은 것: 텔레그램 미니앱 + 서명 검증(서버·저장소 추가로 설정이 2~3배), 이메일 로그인(Cloudflare Access, 네임서버 이전 필요).

## 전체 흐름

```
[08:00 다이제스트 · 맥]
  첫 메시지: 🗞 헤더 + [📚 내 저장함] (URL 버튼)
  기사 메시지: 요약 + [👍 관심] [👎 별로] [🔖 저장]
  sent-log.jsonl에 링크·한줄요약까지 기록
  끝에 publish() — 바뀐 게 있으면 업로드

[5분마다 --feedback-only · 맥]
  collect_feedback(): s:<해시> 콜백 → ratings.jsonl에 label=save 기록
  끝에 publish()

[Cloudflare Pages · 상시]
  /u/<토큰>/index.html — 그 사람의 저장 목록
  /index.html — 안내 페이지
```

## 데이터

새 파일은 `tokens.json` 하나와 빌드 결과물 폴더 `site/`. 둘 다 `.gitignore`에 추가한다.

- **`tokens.json`**: `{"<chat_id>": "<토큰>"}`. 토큰은 `secrets.token_urlsafe(16)`(22자, 추측 불가). 그 사람에게 처음 필요할 때 생성(헤더 발송 시).
- **`sent-log.jsonl`** (기존 확장): `{"hash", "title", "link", "mid"}` 에 `"one"`(한줄요약) 추가. 예전 줄에는 없음 → 예전 기사는 저장 버튼 자체가 없으므로 문제없음.
- **`ratings.jsonl`** (기존 재사용): 저장 이벤트를 `{"ts", "label": "bookmark", "title", "link", "one", "chat"}` 로 기록. 피드백 로그를 한 곳에 모으는 기존 설계를 따르고, 새 로그 파일은 만들지 않는다.
- **`state.json`** (기존 확장): `{"offset"}` 에 `"site_hash"`(마지막으로 업로드 성공한 사이트 내용의 해시) 추가. 현재 `collect_feedback`이 `{"offset": ...}`으로 **덮어쓰므로** 기존 키를 보존하도록 병합 저장으로 바꾼다.

## 코드 변경 (`digest.py`)

1. **`one_liner(item, summary)`** — 5줄 요약을 입력으로 "한국어 한 문장(60자 이내)" 생성. 실패하거나 빈 답이면 요약 첫 줄에서 `- `를 뗀 것으로 대체. `main()`의 `summary_cache`와 같은 키로 캐시해 구독자 간 재사용.
2. **발송** — 기사 버튼 줄에 `{"text": "🔖 저장", "callback_data": f"s:{h}"}` 추가. sent-log에 `link`, `one` 기록. 헤더 메시지에 `.env`의 `SITE_URL`이 있을 때만 `[📚 내 저장함]` URL 버튼(`{SITE_URL}/u/{token}/`) 추가.
3. **`collect_feedback`** — `s:` 콜백이면 sent-log의 해당 기사로 `label: bookmark` 기록 후 `answerCallbackQuery` 텍스트를 "저장됨 🔖"으로(👍👎는 기존 "기록됨 ✅" 유지).
4. **`dedupe_ratings`** — 북마크도 (사람, 기사) 단위로 최신 하나만 유지. 북마크와 👍/👎는 서로 다른 그룹으로 취급해 서로 지우지 않는다.
5. **`preference_block`** — `bookmark`를 `good`과 같이 "좋아한 기사"·좋아하는 주제에 포함. 같은 제목이 👍와 저장으로 두 번 들어가지 않게 중복 제거. `tags_pending`·`tag_pending_ratings`도 `bookmark`에 태그를 단다.
6. **`build_site()`** — `site/`를 새로 만들고, `tokens.json`의 모든 사람에 대해 `site/u/<토큰>/index.html` 생성(저장 0건이면 "아직 저장한 기사가 없어요" 문구). 루트 `site/index.html`은 짧은 안내만. 반환값: 생성한 파일 전체 내용의 해시.
7. **`publish(env)`** — `SITE_URL`이 없거나 `http(s)://`로 시작하지 않으면 아무것도 안 함(기능 꺼짐, 오픈소스 사용자 배려). 잘못된 주소로 버튼을 만들면 텔레그램이 메시지 전체를 거부해 다이제스트가 끊기므로, 버튼·한줄요약·업로드 모두 같은 검사(`site_url(env)`)를 거친다. `build_site()` 해시가 `state.json`의 `site_hash`와 같으면 업로드 생략. 다르면 `wrangler pages deploy` 실행 → 성공 시에만 `site_hash` 갱신(실패하면 다음 실행에서 자동 재시도). 다이제스트 실행과 `--feedback-only` 실행 모두 끝에서 호출하며, 실패해도 다른 기능은 계속된다(try/except + 경고 로그).
8. **환영 메시지** — "🔖 저장 버튼으로 나중에 읽을 기사를 모아두고, 다이제스트의 📚 내 저장함에서 볼 수 있어요" 한 줄 추가.

## 페이지

- 한 파일 HTML, 외부 리소스 없음. 모바일 우선, 시스템 폰트, `prefers-color-scheme`로 다크 모드.
- 내용: 저장 날짜별 묶음, 최신순. 항목마다 제목(원문 링크, 새 탭) + 한줄요약.
- `<meta name="robots" content="noindex">` — 검색엔진 수집 차단.
- `<meta name="referrer" content="no-referrer">` + 링크에 `rel="noopener noreferrer"` — 기사 클릭 시 비밀 주소가 뉴스 사이트로 전달되지 않게.

## 보안

- 제목·한줄요약·링크는 전부 `html.escape` 후 삽입한다. RSS(특히 Hacker News)는 외부인이 쓴 글이므로 신뢰 경계로 취급.
- 링크는 `http://` 또는 `https://`로 시작할 때만 `href`로 넣는다(`javascript:` 주소로 우리 도메인에서 스크립트가 실행되는 것 방지). 아니면 제목만 텍스트로 표시.
- `CLOUDFLARE_API_TOKEN`은 `.env`에만 둔다(이미 gitignore). 토큰 권한은 "Cloudflare Pages: Edit"만.
- 토큰 유출 시: `tokens.json`에서 그 사람 줄을 지우면 다음 발송 때 새 토큰이 발급되고, 다음 업로드에서 옛 주소 페이지가 사라진다.

## 업로드 (wrangler)

```
<NPX> --yes wrangler@4 pages deploy site --project-name <PAGES_PROJECT> --branch main
```

- 환경변수로 `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` 전달.
- launchd 자동 실행은 PATH가 짧아 `npx`를 못 찾는다(과거 TCC 문제와 같은 "자동 실행에서만 터지는" 부류). `.env`의 `NPX` 절대경로를 쓰고, 같은 폴더를 PATH 앞에 붙여 `node`도 찾게 한다.
- 타임아웃 180초(첫 실행은 wrangler 다운로드로 느림).

`.env` 추가 항목:
```
SITE_URL=https://news.starhana.kr
PAGES_PROJECT=daily-news
CLOUDFLARE_API_TOKEN=...
CLOUDFLARE_ACCOUNT_ID=...
NPX=/opt/homebrew/opt/node@24/bin/npx
```

## 1회 설정 (오스카가 직접)

1. Cloudflare 가입 → 계정 ID 확인.
2. API 토큰 발급: 권한 "Account → Cloudflare Pages → Edit".
3. 프로젝트 생성: `npx wrangler pages project create daily-news --production-branch main`
4. Pages 프로젝트 → Custom domains → `news.starhana.kr` 추가.
5. 가비아 DNS 관리 → 레코드 추가: 타입 `CNAME`, 호스트 `news`, 값 `daily-news.pages.dev`.
6. `.env`에 위 항목 추가.

## 반영 방식

개발은 `~/orca/daily-news`, 실제 실행은 `~/news-digest`(launchd가 가리키는 곳). 지금처럼 `digest.py`를 복사해 반영하고, `~/news-digest/.env`에 새 항목을 추가한다. `tokens.json`·`site/`는 `~/news-digest`에 생긴다.

## 검증

- `test_digest.py`(assert 기반, 프레임워크 없음) 하나: 페이지 렌더링 시 HTML 특수문자 이스케이프, `javascript:` 링크 차단, 저장 중복 제거, 저장이 취향(good)에 반영되는지.
- `--dry` 실행 시 본인(`TELEGRAM_CHAT_ID`) 토큰을 포함해 `site/`를 로컬에 만들고 업로드는 안 함 → 브라우저로 열어 눈으로 확인.
- 실제 확인: 텔레그램에서 🔖 누르기 → 5분 내 "저장됨 🔖" → 📚 버튼으로 페이지에 뜨는지.

## 범위 밖 (필요해지면 추가)

저장 취소, 페이지에서 삭제·메모·검색, 텔레그램 미니앱 전환, 저장 기사 출처(긱뉴스/HN) 표시.

## 리스크

- Cloudflare Pages 무료 플랜 "빌드 월 500회"에 직접 업로드가 포함되는지 공식 문서에 명시가 없다. 바뀐 게 있을 때만 업로드하므로 하루 몇 번 수준이라 예상하지만, 넘치면 업로드 최소 간격(예: 30분)을 둔다.
- 파일 수 한도 2만 개(사람당 1개)는 현재 구독자 2명 기준으로 여유가 충분하다.
- 저장 반응이 최대 5분 늦다(기존 👍👎와 동일한 폴링 구조의 한계).
