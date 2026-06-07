# AI 모듈 - 텍스트 추출 전처리

## 파일 구조
```
ai-module/
  text_extractor.py    ← 이 파일
```

## 설치
```bash
pip install beautifulsoup4
```

## run.js 수정 (3줄 추가)

`src/run.js`의 `run()` 함수에서 axe-core 실행 직전에 아래를 추가:

```js
// ── 렌더링된 HTML 저장 (Python AI 모듈용) ──
const renderedHtml = await page.content();
const htmlOutput = (outputPath || `result_${new Date().toISOString().slice(0, 10)}`).replace('.json', '.html');
fs.writeFileSync(htmlOutput, renderedHtml, 'utf-8');
console.log(`3. 렌더링된 HTML 저장: ${htmlOutput}`);
```

## 사용법

```bash
# 1단계: run.js로 검사 + HTML 저장
node src/run.js https://www.gov.kr result.json
#  → result.json (axe-core 결과)
#  → result.html (렌더링된 HTML) ← 새로 생김

# 2단계: Python 전처리
python ai-module/text_extractor.py result.html
#  → result_text.json (추출된 텍스트)
```

## 출력 JSON 구조

```json
{
  "meta": {
    "total_blocks": 33,
    "total_sentences": 34,
    "categories": {
      "heading": 5,
      "paragraph": 3,
      "button": 2,
      "link": 1,
      "label": 2,
      "form_guide": 5,
      "table": 10,
      "list": 4,
      "alert": 1
    }
  },
  "blocks": [
    {
      "text": "본 서비스의 이용에 관한 제반 사항은...",
      "category": "paragraph",
      "tag": "p",
      "selector": "html > body > main > section > p",
      "attributes": {},
      "sentences": ["본 서비스의 이용에...", "이용자는..."]
    }
  ]
}
```

## 카테고리 설명

| 카테고리 | 설명 | 다음 단계(난이도 분석) 적용 |
|----------|------|--------------------------|
| heading | h1~h6 제목 | 명확성 검사 |
| paragraph | 본문 텍스트 | **문장 난이도 분석 (핵심)** |
| button | 버튼 텍스트 | 명확성 검사 (짧아야 정상) |
| link | 링크 텍스트 | 명확성 검사 |
| label | 폼 레이블 | 명확성 검사 |
| form_guide | placeholder, aria-label, title | 안내 문구 명확성 |
| table | 표 내용 | 기본 난이도만 |
| list | 목록 항목 | 기본 난이도만 |
| alert | 알림 텍스트 | 명확성 + 긴급성 |
| other | 기타 | 기본 난이도만 |

## 제외되는 것들

- `<script>`, `<style>`, `<noscript>`, `<iframe>`, `<svg>` 등 비표시 요소
- `<nav>`, `<footer>`, `<header>` 내 반복 텍스트 (메뉴, 저작권 등)
- `<code>`, `<pre>` 코드 블록 (자연어 분석 대상 아님)
- 2글자 미만 텍스트

## 다음 단계 연결

이 모듈의 출력(`result_text.json`)이 Phase 2(KoNLPy/Mecab 한국어 난이도 엔진)의 입력이 됩니다.
특히 `category: "paragraph"`인 블록의 `sentences`가 난이도 분석의 주요 대상입니다.
