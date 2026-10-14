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
  같은 입력과 같은 --seed면 항상 같은 결과가 나온다.

[실행] (run_all.py와 같은 폴더에서)
  python select_survey_texts.py urls.txt            # URL 목록 파일(한 줄에 하나, # 주석 가능)
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


def normalize(text: str) -> str:
    return " ".join(str(text).split())


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

def collect_candidates(sites_dir: Path, min_sentences: int, max_sentences: int) -> tuple[list[dict], dict]:
    stats = {"sites": 0, "paragraphs_with_formula": 0, "length_out": 0, "sentences_out": 0,
             "nested_duplicates": 0, "exact_duplicates": 0}
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
            if not (MIN_CHARS <= len(text) <= MAX_CHARS):
                stats["length_out"] += 1
                continue
            n_sent = sentence_count(text)
            if not (min_sentences <= n_sent <= max_sentences):
                stats["sentences_out"] += 1
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
  form.addSectionHeaderItem().setTitle(`**${entry.text}**`);
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
  form.addPageBreakItem().setTitle('설문을 마쳐 주셔서 감사합니다.');
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="2차 설문용 글 선정과 설문 폼 스크립트 생성")
    parser.add_argument("urls", nargs="?", help="URL 목록 파일(한 줄에 하나)")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="결과 폴더 (기본 output/survey2)")
    parser.add_argument("--skip-run", action="store_true", help="사이트를 다시 돌리지 않고 기존 결과로만 고르기")
    parser.add_argument("--seed", type=int, default=20261004)
    parser.add_argument("--min-sentences", type=int, default=1)
    parser.add_argument("--max-sentences", type=int, default=3)
    args = parser.parse_args(argv)

    out = Path(args.out)
    sites_dir = out / "sites"
    sites_dir.mkdir(parents=True, exist_ok=True)

    if not args.skip_run:
        if not args.urls:
            parser.error("URL 목록 파일을 주거나 --skip-run을 쓰세요.")
        urls = read_urls(Path(args.urls))
        for index, url in enumerate(urls, 1):
            print(f"\n[{index}/{len(urls)}] {url}")
            if not run_site(url, sites_dir / site_slug(index, url)):
                print("  [건너뜀] 이 사이트는 결과를 만들지 못했습니다(차단·빈 페이지·시간초과).")

    candidates, stats = collect_candidates(sites_dir, args.min_sentences, args.max_sentences)
    write_csv(out / "candidates.csv", candidates, CANDIDATE_FIELDS)
    common, unique, warnings = select(candidates, args.seed)
    rows = assign_forms(common, unique, args.seed)
    write_csv(out / "selected.csv", rows, SELECTED_FIELDS)
    write_gs(out / "create_survey_forms_v2.gs", rows)
    (out / "selection_log.json").write_text(json.dumps({
        "seed": args.seed, "min_sentences": args.min_sentences, "max_sentences": args.max_sentences,
        "chars": [MIN_CHARS, MAX_CHARS], "stats": stats,
        "candidates_per_bin": {name: sum(c["gl_bin"] == name for c in candidates) for name, _, _ in GL_BINS},
        "selected_per_bin": {name: sum(c["gl_bin"] == name for c in unique) for name, _, _ in GL_BINS},
        "common": [c["candidate_id"] for c in common], "warnings": warnings,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n── 선정 결과 ──")
    print(f"  사이트 {stats['sites']}곳, 공식 적용 문단 {stats['paragraphs_with_formula']}개 → 후보 {len(candidates)}개")
    print(f"  (글자 수 밖 {stats['length_out']}, 문장 수 밖 {stats['sentences_out']}, "
          f"중복 {stats['exact_duplicates']}, 겹친 바깥 글 {stats['nested_duplicates']} 제외)")
    for name, _, _ in GL_BINS:
        print(f"  {name:7s} 후보 {sum(c['gl_bin'] == name for c in candidates):3d}개 → "
              f"선정 {sum(c['gl_bin'] == name for c in unique)}개")
    print(f"  공통 글 {len(common)}개, 폼 {N_FORMS}개, 결과: {out}")
    for warning in warnings:
        print(f"  [경고] {warning}")
    return 0 if not warnings else 3


if __name__ == "__main__":
    sys.exit(main())
