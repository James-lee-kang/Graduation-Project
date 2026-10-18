"""
select_survey_texts.py — 2차 설문(문장 난이도 검증)에 쓸 글을 고르고 설문 폼 스크립트를 만든다.

[왜 필요한가]
  문장 난이도 모듈의 핵심 검증은 "엔진 점수가 사람이 느끼는 어려움과 같이 움직이는가"다
  (README 12-16절 2차 설문 계획). 메인 페이지에는 공식을 적용할 문장형 문단이 거의 없어서,
  공공기관 본문 페이지(공지 본문, 제도 안내, 민원 신청 방법)를 돌려 글을 모아야 한다.
  글을 손으로 고르면 고른 사람의 판단이 섞이므로, 미리 정한 규칙대로 스크립트가 고른다.

[하는 일]
  1. (URL 목록을 주면) URL마다 run.js → text_extractor.py → difficulty_engine.py를 돌려
     output/survey2/sites/<번호_도메인>/에 결과를 저장한다. CV·LLM·백엔드 전송은 하지 않는다.
  2. 모든 사이트의 문단 중 조건에 맞는 글을 후보로 모은다(candidates.csv).
       - 엔진이 Jo 공식을 적용한 문단(문장 끝 부호가 있고 일반명사 5개 이상) = 긴 글
       - 40~250자, 문장 1~3개 (설문 계획 1번. 10/4에 2~3개에서 1~3개로 고침: 어려운 글은 긴 한 문장인
         경우가 많아 2개 이상으로 묶으면 GL 12 이상 구간 후보가 0개가 됐다. README 12-16절)
       - 같은 글이 겹친 블록(제목+문단, 문단만)은 안쪽 글 하나만 남김
       - 문장이 아닌 조각은 뺀다(10/16, 응답 전): 글머리표·번호·괄호로 시작(목록, 서식 항목, 그림 캡션),
         사진 저작권(ⓒ)·게시판 머리(작성자·작성일·공공누리 등)·웹 주소·전자우편 포함(주소 속 점을 엔진이 문장 끝으로 셈), 문장 부호(. ! ?)로
         끝나지 않음. 모양만 보고 내용·난이도는 보지 않는다
       - 서로 다른 페이지 2곳 이상에 똑같이 나오는 글은 누리집 공통 문구(댓글 운영 원칙 등)라 뺀다(10/16)
  3. GL 원값 구간 5개(5 미만 / 5~7 / 7~9 / 9~12 / 12 이상)에서 6개씩 고르게 뽑는다.
       - 같은 구간 안에서 짧은 글(120자 이하)과 긴 글을 반씩
       - 한 사이트에 몰리지 않게 사이트를 돌아가며
       - 폼 공통 글 2개(5~7, 9~12 구간에서 1개씩)를 따로 뽑음 → 총 32개
       - 구간에 후보가 모자라면 다른 구간으로 채우지 않고 경고만 낸다(범위가 좁아지면
         상관이 낮게 나오므로, 특히 GL 5 미만 쉬운 글이 모자라면 사이트를 더 돌린다)
  4. 폼 3개(공통 2 + 고유 10, 구간마다 2개씩)로 나누고 폼 안 순서를 섞는다. 주의 확인 문항
     1개를 가운데에 넣는다. 결과:
       - selected.csv            : 고른 32개, 폼·순서·엔진 지표
       - create_survey_forms_v2.gs: Google Apps Script. script.google.com에 붙여 넣고
                                   createForms를 실행하면 폼 3개가 생긴다
       - create_survey_form_onelink.gs: 같은 글로 폼 1개(태어난 달로 묶음 3개 중 하나로 보냄). 링크 하나로
                                   배포할 때. 응답은 split_onelink_responses.py로 묶음별로 나눈다(10/16)
  같은 입력과 같은 --seed면 항상 같은 결과가 나온다.

[실행] (run_all.py와 같은 폴더에서)
  python select_survey_texts.py urls.txt            # URL 목록 파일(한 줄에 하나, # 주석 가능)
                                                    # 다시 돌리면 결과가 있는 URL은 건너뛴다(구간이 모자라면
                                                    # 파일 끝에 URL을 더하고 같은 명령 → 새 URL만 돈다)
  python select_survey_texts.py --skip-run          # 이미 돌린 output/survey2/sites/ 결과로 다시 고르기
  python select_survey_texts.py --skip-run --seed 7      # 다른 무작위 선택(seed는 selection_log.json에 남음)

  종료 코드: 0 정상, 3 어떤 구간의 후보가 목표(6개)보다 적음(경고를 보고 사이트를 더 돌린다)

[주의]
  - 엔진 버전을 고정한 뒤에 돌린다. 설문 응답이 들어온 뒤 엔진을 고치면 검증이 아니라 맞추기가 된다.
  - 이 스크립트는 엔진 점수(GL)로만 고른다. 체감 난이도를 짐작해 손으로 바꾸지 않는다.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).parent.resolve()
RULE_BASED_DIR = PROJECT_ROOT / "rule-based-analyzer"
TEXT_LEVEL_DIR = PROJECT_ROOT / "text-level-analyzer"
DEFAULT_OUT = PROJECT_ROOT / "output" / "survey2"

# 설문 계획(README 12-16절)에 고정한 값
GL_BINS = [  # (이름, 하한 이상, 상한 미만)
    ("GL<5", float("-inf"), 5.0),
    ("GL5-7", 5.0, 7.0),
    ("GL7-9", 7.0, 9.0),
    ("GL9-12", 9.0, 12.0),
    ("GL12+", 12.0, float("inf")),
]
PER_BIN = 6
COMMON_BINS = ("GL5-7", "GL9-12")   # 폼 공통 글을 뽑는 구간
N_FORMS = 3
MIN_CHARS, MAX_CHARS = 40, 250
SHORT_CHARS = 120                   # 이하면 짧은 글, 초과면 긴 글
ATTENTION_TEXT = "이 문항은 응답 확인용입니다. 아래에서 2를 선택해 주세요."

_DECIMAL = re.compile(r"(?<=\d)\.(?=\d)")
_SPLIT = re.compile(r"[.!?。]+\s*")


def sentence_count(text: str) -> int:
    """difficulty_engine.calc_avg_sentence_length와 같은 규칙(소수점은 문장 끝이 아님)."""
    protected = _DECIMAL.sub("", text)
    return len([s for s in _SPLIT.split(protected) if s.strip()])


_ZERO_WIDTH = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")


def normalize(text: str) -> str:
    """공백을 하나로. 보이지 않는 글자(폭 없는 공백 등)도 지운다(10/16: 문장 끝 판정을 막았음)."""
    return " ".join(_ZERO_WIDTH.sub("", str(text)).split())


# 문장이 아닌 조각 거르기 (10/16 추가, 응답 받기 전). 첫 실행에서 GL 5~7 구간 선정 글 대부분이
# 그림 캡션("<그림 3. …>"), 제목("나.침.반 안전교육(…)"), 서식 항목("9. 사회보험 적용여부(해당란에 체크)"),
# 글머리표 목록("• 준비운동: …"), 사진 저작권("… ⓒ노윤지")이었다. 엔진은 문장 끝 부호가 어딘가에
# 있고 명사가 5개 이상이면 공식을 쓰므로 이런 조각도 통과한다. 사람이 "글을 읽고 얼마나 어려웠나"를
# 답할 대상이 아니므로 모양만 보고 기계적으로 뺀다(난이도·내용은 보지 않음).
_LIST_START = re.compile(
    r"^\s*(?:[•·∙▪▫■□○●◆◇◎※\-–—*▶►▷☞→<\[【〈《「『]"     # 글머리표·괄호 머리
    r"|\(?\d{1,2}\s*[.)]\s"                             # 1. / 1) / (1)
    r"|[①-⑳]"                                            # 원 숫자
    r"|[가-하]\s*[.)]\s"                                # 가. / 나)
    r"|[A-Za-z]\s*[.)]\s)")                             # Q. / A. (묻고 답하기)
_SENTENCE_END = re.compile(r"[.!?。][\"'”’」』)\]]*$")
_CREDIT = re.compile(r"[ⓒ©]")
# 게시판 머리·저작권 표시(작성자, 작성일, 첨부파일, 공공누리 …)가 든 글은 본문이 아니다(10/16)
_BOARD_META = re.compile(r"작성자|작성일|첨부파일|조회수|공공누리")
# 웹 주소·전자우편이 든 글도 뺀다(10/16). 엔진의 문장 나누기가 주소 안의 점(kid.seoul.go.kr)을 문장 끝으로
# 세어 한 문장 글을 짧은 문장 여러 개로 보고 GL을 낮게 낸다(예: GL 3.8, 실제로는 긴 한 문장).
# 엔진은 고정했으므로 고치지 않고, 이런 글을 설문 후보에서만 뺀다(README 한계에 기록).
_WEB_ADDRESS = re.compile(r"https?://|www\.|[\w.+-]+@[\w-]+\.|\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:kr|com|net|org)\b",
                          re.IGNORECASE)


def not_prose_reason(text: str) -> str | None:
    """문장 글이 아니면 이유, 맞으면 None."""
    if _LIST_START.match(text):
        return "list_or_caption_start"
    if _CREDIT.search(text):
        return "photo_credit"
    if _WEB_ADDRESS.search(text):
        return "web_address"
    if _BOARD_META.search(text):
        return "board_meta"
    if not _SENTENCE_END.search(text.rstrip()):
        return "no_sentence_end"
    return None


def site_slug(index: int, url: str) -> str:
    host = urlparse(url).netloc or "site"
    return f"{index:02d}_{re.sub(r'[^0-9A-Za-z.-]', '_', host)}"


def read_urls(path: Path) -> list[str]:
    urls = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            urls.append(line)
    return urls


# ── 1. 사이트별 실행 ─────────────────────────────────────────────────────────

def plan_site_dirs(urls: list[str], sites_dir: Path) -> list[tuple[str, Path, bool]]:
    """URL마다 결과 폴더를 정한다(10/16 추가).

    이미 돌린 URL(url.txt가 같은 폴더)은 그 폴더를 다시 쓰고, 결과(result_text_difficulty.json)가
    있으면 건너뛴다. 새 URL은 기존 폴더 번호 다음부터 번호를 붙인다. 그래서 구간이 모자랄 때
    URL 파일 끝에 줄을 더하고 같은 명령을 다시 돌리면 새 URL만 돈다(예전에는 번호가 1부터 다시
    매겨져, 같은 번호·같은 도메인 폴더를 다른 페이지 결과로 덮어쓸 수 있었다).
    처음 돌릴 때(폴더 없음)는 예전과 같이 01, 02, …다.
    """
    existing, last = {}, 0
    if sites_dir.exists():
        for directory in sorted(p for p in sites_dir.iterdir() if p.is_dir()):
            match = re.match(r"(\d+)_", directory.name)
            if match:
                last = max(last, int(match.group(1)))
            url_file = directory / "url.txt"
            if url_file.exists():
                existing.setdefault(url_file.read_text(encoding="utf-8").strip(), directory)
    plan, used = [], set()
    for url in urls:
        directory = existing.get(url)
        if directory is None or directory in used:
            last += 1
            directory = sites_dir / site_slug(last, url)
        used.add(directory)
        plan.append((url, directory, (directory / "result_text_difficulty.json").exists()))
    return plan


def run_site(url: str, site_dir: Path) -> bool:
    """run.js → text_extractor.py → difficulty_engine.py. CV·LLM·백엔드는 돌리지 않는다."""
    from run_all import RULE_BASED_STEP_TIMEOUT_SECONDS, run_command

    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "url.txt").write_text(url, encoding="utf-8")
    result_json = site_dir / "result.json"
    if not run_command(["node", "run.js", url, str(result_json)], cwd=str(RULE_BASED_DIR),
                       description=f"규칙 기반 + DOM 저장 ({url})",
                       timeout_seconds=RULE_BASED_STEP_TIMEOUT_SECONDS):
        return False
    html = site_dir / "result.html"
    if not html.exists():
        return False
    text_json = site_dir / "result_text.json"
    if not run_command([sys.executable, str(TEXT_LEVEL_DIR / "text_extractor.py"), str(html), str(text_json)],
                       cwd=str(site_dir), description="텍스트 추출"):
        return False
    return run_command([sys.executable, str(TEXT_LEVEL_DIR / "difficulty_engine.py"), str(text_json),
                        str(site_dir / "result_text_difficulty.json")],
                       cwd=str(site_dir), description="난이도 분석")


# ── 2. 후보 모으기 ───────────────────────────────────────────────────────────

def collect_candidates(sites_dir: Path, min_sentences: int, max_sentences: int,
                       min_chars: int = MIN_CHARS) -> tuple[list[dict], dict]:
    stats = {"sites": 0, "paragraphs_with_formula": 0, "length_out": 0, "sentences_out": 0,
             "nested_duplicates": 0, "exact_duplicates": 0, "not_prose": 0}
    raw = []
    for site_dir in sorted(p for p in sites_dir.iterdir() if p.is_dir()):
        difficulty = site_dir / "result_text_difficulty.json"
        if not difficulty.exists():
            continue
        stats["sites"] += 1
        url_file = site_dir / "url.txt"
        url = url_file.read_text(encoding="utf-8").strip() if url_file.exists() else ""
        data = json.loads(difficulty.read_text(encoding="utf-8"))
        for block in data.get("results", []):
            if block.get("exclusion_reason") or block.get("category") != "paragraph":
                continue
            if block.get("difficulty_score") is None:   # 공식을 적용하지 않은 글(짧은 글, 부호 없는 목록)
                continue
            stats["paragraphs_with_formula"] += 1
            text = normalize(block.get("text", ""))
            if not (min_chars <= len(text) <= MAX_CHARS):
                stats["length_out"] += 1
                continue
            n_sent = sentence_count(text)
            if not (min_sentences <= n_sent <= max_sentences):
                stats["sentences_out"] += 1
                continue
            if not_prose_reason(text):
                stats["not_prose"] += 1
                continue
            metrics = block.get("metrics") or {}
            raw.append({
                "site": site_dir.name,
                "url": url,
                "selector": block.get("selector", ""),
                "text": text,
                "chars": len(text),
                "eojeols": len(text.split()),
                "sentences": n_sent,
                "gl_raw": metrics.get("gl_score"),
                "difficulty_score": block.get("difficulty_score"),
                "difficulty_score_v2": block.get("difficulty_score_v2"),
                "avg_sentence_length": metrics.get("avg_sentence_length"),
                "easy_word_ratio": metrics.get("easy_word_ratio"),
                "noun_eojeol_run": metrics.get("noun_eojeol_run"),
                "hard_noun_count": metrics.get("hard_noun_count"),
                "flags": " | ".join(block.get("flags", [])),
            })

    # 누리집 공통 문구 빼기(10/16, 응답 전): 서로 다른 페이지 2곳 이상에 똑같이 나오는 글은 본문이 아니라
    # 누리집 틀(댓글 운영 원칙, "이 누리집은 대한민국 공식 전자정부 누리집입니다" 등)이다.
    sites_of: dict[str, set] = {}
    for item in raw:
        sites_of.setdefault(item["text"], set()).add(item["site"])
    boilerplate = {text for text, sites in sites_of.items() if len(sites) >= 2}
    stats["boilerplate"] = sum(item["text"] in boilerplate for item in raw)
    raw = [item for item in raw if item["text"] not in boilerplate]

    # 같은 글 중복 제거: 완전히 같은 글은 하나만, 다른 후보를 품은 바깥 글(제목+문단)은 뺀다
    unique, seen = [], set()
    for item in raw:
        if item["text"] in seen:
            stats["exact_duplicates"] += 1
            continue
        seen.add(item["text"])
        unique.append(item)
    texts = [item["text"] for item in unique]
    candidates = []
    for item in unique:
        if any(other != item["text"] and other in item["text"] for other in texts):
            stats["nested_duplicates"] += 1
            continue
        candidates.append(item)

    for item in candidates:
        item["gl_bin"] = next(name for name, lo, hi in GL_BINS if lo <= item["gl_raw"] < hi)
        item["length_group"] = "short" if item["chars"] <= SHORT_CHARS else "long"
    candidates.sort(key=lambda c: (c["site"], c["selector"], c["text"]))
    for number, item in enumerate(candidates, 1):
        item["candidate_id"] = f"C{number:03d}"
    return candidates, stats


# ── 3. 구간별 고르기 ─────────────────────────────────────────────────────────

def pick_spread(pool: list[dict], count: int, rng: random.Random) -> list[dict]:
    """짧은 글·긴 글을 번갈아, 사이트를 돌아가며 고른다."""
    pool = pool[:]
    rng.shuffle(pool)
    groups = {"short": [c for c in pool if c["length_group"] == "short"],
              "long": [c for c in pool if c["length_group"] == "long"]}
    chosen, site_use = [], {}
    order = ["short", "long"] if rng.random() < 0.5 else ["long", "short"]
    turn = 0
    while len(chosen) < count and (groups["short"] or groups["long"]):
        group = groups[order[turn % 2]] or groups[order[(turn + 1) % 2]]
        turn += 1
        group.sort(key=lambda c: site_use.get(c["site"], 0))   # 덜 쓴 사이트 먼저 (안정 정렬)
        item = group.pop(0)
        site_use[item["site"]] = site_use.get(item["site"], 0) + 1
        chosen.append(item)
    return chosen


def select(candidates: list[dict], seed: int) -> tuple[list[dict], list[dict], list[str]]:
    rng = random.Random(seed)
    warnings = []
    by_bin = {name: [c for c in candidates if c["gl_bin"] == name] for name, _, _ in GL_BINS}

    common = []
    for name in COMMON_BINS:
        pool = sorted(by_bin[name], key=lambda c: abs(c["chars"] - SHORT_CHARS))[:5]  # 중간 길이
        if pool:
            item = rng.choice(pool)
            common.append(item)
            by_bin[name].remove(item)
        else:
            warnings.append(f"공통 글을 뽑을 {name} 후보가 없습니다.")

    unique = []
    for name, _, _ in GL_BINS:
        chosen = pick_spread(by_bin[name], PER_BIN, rng)
        if len(chosen) < PER_BIN:
            warnings.append(f"{name} 구간 후보가 {len(chosen)}개뿐입니다(목표 {PER_BIN}개). "
                            "이 구간 글이 있을 만한 사이트를 더 돌리세요.")
        unique.extend(chosen)
    return common, unique, warnings


def assign_forms(common: list[dict], unique: list[dict], seed: int) -> list[dict]:
    """구간마다 고유 글을 폼에 돌아가며 나누고, 폼 안 순서를 섞어 주의 확인 문항을 넣는다."""
    rng = random.Random(seed + 1)
    forms = {f: [] for f in range(1, N_FORMS + 1)}
    pointer = rng.randrange(N_FORMS)   # 구간을 넘어 이어서 돌려, 후보가 모자란 구간이 있어도 폼별 개수 차이가 1 이하
    for name, _, _ in GL_BINS:
        for item in [c for c in unique if c["gl_bin"] == name]:
            forms[pointer % N_FORMS + 1].append(item)
            pointer += 1

    rows = []
    for form, items in forms.items():
        entries = [dict(item, role="common") for item in common] + [dict(item, role="unique") for item in items]
        rng.shuffle(entries)
        entries.insert(len(entries) // 2, {"role": "attention", "text": ATTENTION_TEXT, "candidate_id": "ATTN"})
        for position, entry in enumerate(entries, 1):
            rows.append(dict(entry, form=form, position=position))
    return rows


# ── 4. 출력 ──────────────────────────────────────────────────────────────────

CANDIDATE_FIELDS = ["candidate_id", "gl_bin", "length_group", "gl_raw", "difficulty_score", "difficulty_score_v2",
                    "avg_sentence_length", "easy_word_ratio", "noun_eojeol_run", "hard_noun_count",
                    "chars", "eojeols", "sentences", "site", "url", "selector", "flags", "text"]
SELECTED_FIELDS = ["form", "position", "role"] + CANDIDATE_FIELDS


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:   # 엑셀에서 한글이 깨지지 않게 BOM
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})


GS_TEMPLATE = r"""/**
 * Uniaccess 2차 설문 — 문장 난이도 엔진 검증 (select_survey_texts.py가 만든 파일, 손으로 고치지 말 것)
 *
 * 사용법: script.google.com → 새 프로젝트 → 이 내용 전체를 붙여넣기 → createForms 실행(▶)
 *        → 로그에 폼 3개의 편집·응답 URL이 나온다.
 * 설계 (README 12-16절 2차 설문 계획):
 *  - 폼마다 글 12개(공통 2 + 고유 10) + 주의 확인 1개. 글을 하나씩 보여 주고 1문항만 묻는다.
 *  - 문항 제목의 "글 N" 번호는 폼 안 순서다. 어떤 글인지는 selected.csv의 form·position으로 맞춘다.
 *  - 응답자에게 내부 식별자(C001 등)와 엔진 점수는 보이지 않는다.
 *  - 다시 실행하면 새 폼 3개가 또 생긴다(기존 폼을 덮어쓰지 않음).
 */

const TEXT_DATA = __TEXT_DATA__;

function buildIntro(form) {
  form.setDescription(
    '안녕하세요. 홍익대학교 졸업작품 "Uniaccess: 공공 디지털 서비스 접근성 자동평가 플랫폼"의 ' +
    '문장 난이도 엔진 검증을 위한 설문입니다.\n\n' +
    '공공기관 웹사이트에 실제로 실린 글을 하나씩 보여 드립니다. 각 글을 읽고 이해하기 얼마나 ' +
    '어려웠는지 느낀 대로 답해 주세요. 정답은 없습니다. 응답은 통계 분석 목적으로만 사용되며 ' +
    '개인을 특정하지 않습니다. 소요시간은 약 7~10분입니다.\n\n' +
    '참여해 주셔서 감사합니다.'
  );
  form.addPageBreakItem().setTitle('응답자 정보 (선택)');
  form.addMultipleChoiceItem()
    .setTitle('평소 공공기관 웹사이트(정부24, 건강보험공단 등)를 이용하는 빈도는 어느 정도인가요?')
    .setChoiceValues(['거의 이용 안 함', '가끔 이용(연 1~2회)', '종종 이용(분기 1회 이상)', '자주 이용(월 1회 이상)'])
    .setRequired(false);
}

function buildTextItem(form, entry, total) {
  form.addPageBreakItem().setTitle(`글 ${entry.position} / ${total}`);
  // 구글 폼 제목은 마크다운을 그리지 않아 ** 가 그대로 보였다(10/16 수정). 글은 머리글 제목에 그대로 둔다.
  form.addSectionHeaderItem().setTitle(entry.text);
  const title = entry.role === 'attention'
    ? `글 ${entry.position}. 응답 확인 문항입니다. 2를 선택해 주세요.`
    : `글 ${entry.position}. 이 글을 이해하기 얼마나 어려웠나요?`;
  form.addScaleItem()
    .setTitle(title)
    .setBounds(1, 5)
    .setLabels('매우 쉬웠다', '매우 어려웠다')
    .setRequired(true);
}

function buildOneForm(number, entries) {
  const form = FormApp.create(`[Uniaccess 2차 설문 ${number}/${Object.keys(TEXT_DATA).length}] 공공기관 웹 글 난이도 평가`);
  form.setIsQuiz(false);
  form.setProgressBar(true);
  form.setShuffleQuestions(false); // 순서는 select_survey_texts.py가 이미 섞었고 selected.csv에 기록됨
  buildIntro(form);
  entries.forEach(entry => buildTextItem(form, entry, entries.length));
  form.setConfirmationMessage('설문을 마쳐 주셔서 감사합니다.'); // 빈 마지막 페이지 대신 제출 후 안내(10/16)
  return form;
}

function createForms() {
  Object.keys(TEXT_DATA).forEach(key => {
    const form = buildOneForm(key.replace('form', ''), TEXT_DATA[key]);
    Logger.log(`${key} 편집 URL: ${form.getEditUrl()}`);
    Logger.log(`${key} 응답 URL: ${form.getPublishedUrl()}`);
  });
}
"""


def write_gs(path: Path, rows: list[dict]) -> None:
    data = {}
    for row in sorted(rows, key=lambda r: (r["form"], r["position"])):
        data.setdefault(f"form{row['form']}", []).append(
            {"position": row["position"], "role": row["role"], "text": row["text"]})
    path.write_text(GS_TEMPLATE.replace("__TEXT_DATA__", json.dumps(data, ensure_ascii=False, indent=2)),
                    encoding="utf-8")


# 한 링크 배포용(10/16 추가): 폼 하나 안에 묶음 3개를 넣고, 태어난 달로 한 묶음에만 보낸다.
# 카톡방·인스타 스토리에 링크 하나만 올릴 수 있게. 글·순서·묶음 나눔은 3폼 방식과 똑같고(selected.csv의
# form = 묶음 번호), 응답 CSV는 split_onelink_responses.py가 묶음별 3개로 나눠 analyze_survey2.py에 넘긴다.
# 10/17: 첫 페이지에 연구 안내(목적·수집 항목·파기 시점·참여 자율성)와 동의 문항을 넣고, 경품 추첨 응모(이름·휴대전화 번호)는
# 설문과 다른 폼으로 분리했다. 설문 폼에는 개인을 알아볼 수 있는 정보를 받지 않는다.
# (10/16 문구 "저장·분석하지 않습니다"는 틀렸다 — 구글폼은 답을 저장한다. "묶음을 나누는 데만 씁니다"로 고침)
ONELINK_GROUP_QUESTION = "태어난 달을 골라 주세요. (글 묶음을 나누는 데만 씁니다)"
ONELINK_GROUP_CHOICES = ["1~4월", "5~8월", "9~12월"]   # 순서대로 묶음 1, 2, 3
ONELINK_TITLE_PREFIX = "묶음 {group} · "               # 문항 제목 앞에 붙여 묶음끼리 제목이 겹치지 않게
ONELINK_CONSENT_QUESTION = "위 안내를 읽고 설문 참여에 동의하십니까?"
ONELINK_CONSENT_YES = "동의합니다"
ONELINK_CONSENT_NO = "동의하지 않습니다 (설문이 끝납니다)"

ONELINK_GS_TEMPLATE = r"""/**
 * Uniaccess 2차 설문 — 한 링크 배포판 (select_survey_texts.py가 만든 파일)
 *
 * 사용법
 *  1. 아래 SETTINGS의 【…】 칸을 채운다(채우지 않으면 실행이 멈춘다). SETTINGS 말고는 고치지 않는다.
 *  2. script.google.com → 새 프로젝트 → 이 내용 전체를 붙여넣기 → createOneLinkForm 실행(▶)
 *  3. 로그에 설문 폼과 추첨 응모 폼의 URL이 나온다. 올리는 링크는 "설문 응답 URL" 하나뿐이다.
 *     (추첨 응모 링크는 설문을 제출한 뒤 안내 화면에 나온다)
 *
 * 설계
 *  - 1페이지: 연구 안내(목적·수집 항목·파기 시점·참여 자율성과 거부 권리·문의)와 동의 문항.
 *    "동의하지 않습니다"를 고르면 바로 끝난다(빈 응답 한 줄이 남고, 분석에서는 빠진다).
 *  - 2페이지: 이용 빈도(선택), 태어난 달 → 묶음 1·2·3 중 한 곳으로만 보낸다. 묶음 끝에서 바로 제출.
 *  - 글·순서는 3폼 방식(create_survey_forms_v2.gs)과 똑같다. 문항 제목 "묶음 K · 글 N. …"으로
 *    split_onelink_responses.py가 묶음별 CSV를 만든다.
 *  - 경품 추첨 응모(이름·휴대전화 번호)는 별도 폼에 저장한다. 두 폼의 응답을 서로 맞춰 보지 않는다
 *    (제출 시각으로 맞춰 보는 것도 하지 않는다).
 *  - 다시 실행하면 새 폼이 또 생긴다(기존 폼을 덮어쓰지 않음).
 */

const SETTINGS = {
  researcher: '홍익대학교 소프트웨어융합학과 졸업작품 Uniaccess 팀',
  contact: '【문의 이메일 (예: 팀 대표 이메일)】',
  deleteBy: '2026년 12월 31일',          // 설문 원자료 파기 날짜
  lottery: {
    enabled: true,                       // 추첨을 안 하면 false
    prize: '【경품 (예: 커피 기프티콘 10명)】',
    drawDate: '【추첨·발송 날짜 (예: 2026년 11월 2일)】',
  },
};

const TEXT_DATA = __TEXT_DATA__;
const GROUP_QUESTION = __GROUP_QUESTION__;
const GROUP_CHOICES = __GROUP_CHOICES__;
const CONSENT_QUESTION = __CONSENT_QUESTION__;
const CONSENT_YES = __CONSENT_YES__;
const CONSENT_NO = __CONSENT_NO__;

function checkSettings() {
  const unfilled = JSON.stringify(SETTINGS.lottery.enabled ? SETTINGS : { ...SETTINGS, lottery: {} }).includes('【');
  if (unfilled) throw new Error('SETTINGS의 【…】 칸을 채운 뒤 다시 실행하세요.');
}

function consentNotice() {
  const lines = [
    '■ 연구 목적',
    `${SETTINGS.researcher}이 만든 문장 난이도 평가 엔진이 사람이 느끼는 글의 난이도와 얼마나 일치하는지 ` +
      '검증하기 위한 설문입니다. 결과는 졸업작품 보고서와 발표에 평균·상관계수 같은 통계로만 쓰입니다.',
    '',
    '■ 수집 항목',
    '① 글마다 느낀 난이도(1~5점)  ② 공공기관 웹사이트 이용 빈도(선택)  ' +
      '③ 태어난 달 구간(1~4월 / 5~8월 / 9~12월, 글 묶음을 나누는 데만 씀)  ④ 제출 시각(구글폼 자동 기록)',
    '이름·이메일·전화번호 등 개인을 알아볼 수 있는 정보는 이 설문에서 받지 않습니다. ' +
      '구글 로그인도 필요 없고 이메일 주소도 수집하지 않습니다.',
    '',
    '■ 보관과 파기',
    `응답은 연구자의 구글 계정에만 보관하고, 분석이 끝나면 ${SETTINGS.deleteBy}까지 원자료를 파기합니다. ` +
      '보고서에는 개인별 응답이 아니라 통계만 싣습니다.',
    '',
    '■ 참여 자율성과 거부 권리',
    '참여는 자유입니다. 동의하지 않거나 중간에 창을 닫아도 아무런 불이익이 없으며, 제출하기 전에 닫으면 응답은 저장되지 않습니다. ' +
      '다만 익명으로 받기 때문에 제출한 뒤에는 개인의 응답을 골라 지울 수 없습니다.',
    '',
    '■ 소요 시간: 약 7~10분 (글 12개)',
  ];
  if (SETTINGS.lottery.enabled) {
    lines.push('', '■ 경품 추첨',
      `설문을 마치면 경품 추첨 응모 링크가 나옵니다(${SETTINGS.lottery.prize}, ${SETTINGS.lottery.drawDate}). ` +
      '응모는 선택이며, 응모할 때 받는 이름·휴대전화 번호는 이 설문과 다른 폼에 따로 저장되어 설문 응답과 연결되지 않습니다.');
  }
  lines.push('', `■ 문의: ${SETTINGS.contact}`);
  return lines.join('\n');
}

function createLotteryForm() {
  const form = FormApp.create('[Uniaccess 2차 설문] 경품 추첨 응모');
  form.setCollectEmail(false);
  form.setDescription([
    '설문에 참여해 주셔서 감사합니다. 이 폼은 설문 응답과 따로 저장되며, 두 응답을 서로 연결하지 않습니다.',
    '',
    '■ 개인정보 수집·이용 안내',
    '· 목적: 경품 추첨과 당첨자 연락·카카오톡 기프티콘 발송',
    '· 항목: 이름, 휴대전화 번호',
    `· 보유 기간: 경품 발송이 끝나면 바로 파기 (경품: ${SETTINGS.lottery.prize}, 추첨·발송: ${SETTINGS.lottery.drawDate})`,
    '· 동의를 거부할 권리가 있으며, 거부하면 추첨에서만 빠지고 다른 불이익은 없습니다.',
    `· 문의: ${SETTINGS.contact}`,
  ].join('\n'));
  const consent = form.addMultipleChoiceItem()
    .setTitle('개인정보 수집·이용에 동의하십니까?')
    .setRequired(true);
  form.addPageBreakItem().setTitle('응모 정보');
  form.addTextItem().setTitle('이름').setRequired(true);
  form.addTextItem().setTitle('휴대전화 번호 (카카오톡 기프티콘 발송용)')
    .setHelpText('예: 010-1234-5678')
    .setValidation(FormApp.createTextValidation()
      .requireTextMatchesPattern('^01[016789]-?[0-9]{3,4}-?[0-9]{4}$')
      .setHelpText('휴대전화 번호를 010-1234-5678 형식으로 적어 주세요.')
      .build())
    .setRequired(true);
  consent.setChoices([
    consent.createChoice('동의합니다', FormApp.PageNavigationType.CONTINUE),
    consent.createChoice('동의하지 않습니다 (응모하지 않음)', FormApp.PageNavigationType.SUBMIT),
  ]);
  form.setConfirmationMessage(`응모가 완료되었습니다. 당첨되시면 ${SETTINGS.lottery.drawDate}에 카카오톡 기프티콘을 보내 드립니다.`);
  return form;
}

function createOneLinkForm() {
  checkSettings();
  const lottery = SETTINGS.lottery.enabled ? createLotteryForm() : null;

  const keys = Object.keys(TEXT_DATA);   // form1, form2, form3 = 묶음 1, 2, 3
  const form = FormApp.create('[Uniaccess 2차 설문] 공공기관 웹 글 난이도 평가');
  form.setIsQuiz(false);
  form.setCollectEmail(false);
  form.setProgressBar(false);            // 묶음 하나만 보므로 전체 기준 진행률은 틀리게 보인다
  form.setShuffleQuestions(false);       // 순서는 select_survey_texts.py가 이미 섞었고 selected.csv에 기록됨
  form.setDescription(
    '안녕하세요. 공공기관 웹사이트에 실제로 실린 글을 하나씩 보여 드리고, 각 글이 이해하기 얼마나 ' +
    '어려웠는지 여쭙는 설문입니다. 정답은 없습니다. 아래 안내를 읽고 동의 여부를 골라 주세요.'
  );
  form.setConfirmationMessage(lottery
    ? '설문을 마쳐 주셔서 감사합니다.\n\n경품 추첨에 응모하시려면 아래 링크에서 이름과 휴대전화 번호를 남겨 주세요. ' +
      '응모 정보는 설문 응답과 다른 폼에 따로 저장되며, 둘을 연결하지 않습니다.\n' + lottery.getPublishedUrl()
    : '설문을 마쳐 주셔서 감사합니다.');

  // 1페이지: 연구 안내와 동의
  form.addSectionHeaderItem().setTitle('연구 안내와 참여 동의').setHelpText(consentNotice());
  const consentItem = form.addMultipleChoiceItem().setTitle(CONSENT_QUESTION).setRequired(true);

  // 2페이지: 이용 빈도, 묶음 배정
  form.addPageBreakItem().setTitle('시작하기');
  form.addMultipleChoiceItem()
    .setTitle('평소 공공기관 웹사이트(정부24, 건강보험공단 등)를 이용하는 빈도는 어느 정도인가요? (선택)')
    .setChoiceValues(['거의 이용 안 함', '가끔 이용(연 1~2회)', '종종 이용(분기 1회 이상)', '자주 이용(월 1회 이상)'])
    .setRequired(false);
  const groupItem = form.addMultipleChoiceItem().setTitle(GROUP_QUESTION).setRequired(true);

  const firstPages = [];
  keys.forEach((key, groupIndex) => {
    const group = groupIndex + 1;
    const entries = TEXT_DATA[key];
    entries.forEach((entry, entryIndex) => {
      const page = form.addPageBreakItem().setTitle(`글 ${entry.position} / ${entries.length}`);
      if (entryIndex === 0) {
        firstPages.push(page);
        // 이 페이지 바로 앞 페이지(= 앞 묶음의 마지막 글)를 마치면 제출한다
        if (groupIndex > 0) page.setGoToPage(FormApp.PageNavigationType.SUBMIT);
      }
      form.addSectionHeaderItem().setTitle(entry.text);
      const question = entry.role === 'attention'
        ? `글 ${entry.position}. 응답 확인 문항입니다. 2를 선택해 주세요.`
        : `글 ${entry.position}. 이 글을 이해하기 얼마나 어려웠나요?`;
      form.addScaleItem()
        .setTitle(`묶음 ${group} · ${question}`)
        .setBounds(1, 5)
        .setLabels('매우 쉬웠다', '매우 어려웠다')
        .setRequired(true);
    });
  });
  consentItem.setChoices([
    consentItem.createChoice(CONSENT_YES, FormApp.PageNavigationType.CONTINUE),
    consentItem.createChoice(CONSENT_NO, FormApp.PageNavigationType.SUBMIT),
  ]);
  groupItem.setChoices(GROUP_CHOICES.map((label, i) => groupItem.createChoice(label, firstPages[i])));

  Logger.log(`설문 편집 URL: ${form.getEditUrl()}`);
  Logger.log(`설문 응답 URL(이것만 올리면 됨): ${form.getPublishedUrl()}`);
  if (lottery) {
    Logger.log(`추첨 응모 편집 URL: ${lottery.getEditUrl()}`);
    Logger.log(`추첨 응모 URL(설문 제출 화면에 자동으로 나옴): ${lottery.getPublishedUrl()}`);
  }
}
"""


def write_onelink_gs(path: Path, rows: list[dict]) -> None:
    data = {}
    for row in sorted(rows, key=lambda r: (r["form"], r["position"])):
        data.setdefault(f"form{row['form']}", []).append(
            {"position": row["position"], "role": row["role"], "text": row["text"]})
    if len(data) != len(ONELINK_GROUP_CHOICES):
        raise ValueError(f"묶음 수({len(data)})와 태어난 달 선택지 수({len(ONELINK_GROUP_CHOICES)})가 다릅니다.")
    dump = lambda value: json.dumps(value, ensure_ascii=False)   # noqa: E731
    script = (ONELINK_GS_TEMPLATE
              .replace("__TEXT_DATA__", json.dumps(data, ensure_ascii=False, indent=2))
              .replace("__GROUP_QUESTION__", dump(ONELINK_GROUP_QUESTION))
              .replace("__GROUP_CHOICES__", dump(ONELINK_GROUP_CHOICES))
              .replace("__CONSENT_QUESTION__", dump(ONELINK_CONSENT_QUESTION))
              .replace("__CONSENT_YES__", dump(ONELINK_CONSENT_YES))
              .replace("__CONSENT_NO__", dump(ONELINK_CONSENT_NO)))
    path.write_text(script, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="2차 설문용 글 선정과 설문 폼 스크립트 생성")
    parser.add_argument("urls", nargs="?", help="URL 목록 파일(한 줄에 하나)")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="결과 폴더 (기본 output/survey2)")
    parser.add_argument("--skip-run", action="store_true", help="사이트를 다시 돌리지 않고 기존 결과로만 고르기")
    parser.add_argument("--seed", type=int, default=20261004)
    parser.add_argument("--min-sentences", type=int, default=1)
    parser.add_argument("--max-sentences", type=int, default=3)
    parser.add_argument("--min-chars", type=int, default=MIN_CHARS,
                        help=f"후보 글 최소 글자 수 (기본 {MIN_CHARS}, 설문 계획값). 바꾸면 selection_log.json에 남는다")
    args = parser.parse_args(argv)

    out = Path(args.out)
    sites_dir = out / "sites"
    sites_dir.mkdir(parents=True, exist_ok=True)

    if not args.skip_run:
        if not args.urls:
            parser.error("URL 목록 파일을 주거나 --skip-run을 쓰세요.")
        urls = read_urls(Path(args.urls))
        for number, (url, site_dir, done) in enumerate(plan_site_dirs(urls, sites_dir), 1):
            print(f"\n[{number}/{len(urls)}] {url}")
            if done:
                print(f"  [이미 있음] {site_dir.name} 결과를 그대로 씁니다.")
                continue
            if not run_site(url, site_dir):
                print("  [건너뜀] 이 사이트는 결과를 만들지 못했습니다(차단·빈 페이지·시간초과).")

    candidates, stats = collect_candidates(sites_dir, args.min_sentences, args.max_sentences, args.min_chars)
    write_csv(out / "candidates.csv", candidates, CANDIDATE_FIELDS)
    common, unique, warnings = select(candidates, args.seed)
    rows = assign_forms(common, unique, args.seed)
    write_csv(out / "selected.csv", rows, SELECTED_FIELDS)
    write_gs(out / "create_survey_forms_v2.gs", rows)
    write_onelink_gs(out / "create_survey_form_onelink.gs", rows)
    (out / "selection_log.json").write_text(json.dumps({
        "seed": args.seed, "min_sentences": args.min_sentences, "max_sentences": args.max_sentences,
        "chars": [args.min_chars, MAX_CHARS], "stats": stats,
        "candidates_per_bin": {name: sum(c["gl_bin"] == name for c in candidates) for name, _, _ in GL_BINS},
        "selected_per_bin": {name: sum(c["gl_bin"] == name for c in unique) for name, _, _ in GL_BINS},
        "common": [c["candidate_id"] for c in common], "warnings": warnings,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n── 선정 결과 ──")
    print(f"  사이트 {stats['sites']}곳, 공식 적용 문단 {stats['paragraphs_with_formula']}개 → 후보 {len(candidates)}개")
    print(f"  (글자 수 밖 {stats['length_out']}, 문장 수 밖 {stats['sentences_out']}, "
          f"중복 {stats['exact_duplicates']}, 겹친 바깥 글 {stats['nested_duplicates']}, "
          f"문장 아닌 조각 {stats['not_prose']}, 누리집 공통 문구 {stats.get('boilerplate', 0)} 제외)")
    for name, _, _ in GL_BINS:
        print(f"  {name:7s} 후보 {sum(c['gl_bin'] == name for c in candidates):3d}개 → "
              f"선정 {sum(c['gl_bin'] == name for c in unique)}개")
    print(f"  공통 글 {len(common)}개, 폼 {N_FORMS}개, 결과: {out}")
    for warning in warnings:
        print(f"  [경고] {warning}")
    return 0 if not warnings else 3


if __name__ == "__main__":
    sys.exit(main())
