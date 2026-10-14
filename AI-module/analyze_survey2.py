"""
analyze_survey2.py — 2차 설문(문장 난이도 점수 vs 체감 난이도) 분석 스크립트
============================================================================

[왜 응답을 받기 전에 만들었나]
  1차 설문 때처럼 응답을 본 뒤에 "어떤 지표로, 어떤 기준으로" 볼지 정하면, 결과에 맞춰
  고르게 된다. 그래서 분석 방법과 판정 기준을 응답 수집 전에 이 파일에 고정해 둔다
  (README 4-10절, 12-16절). 응답이 들어온 뒤에는 이 파일도, 난이도 엔진도 고치지 않는다.
  결과를 보고 엔진을 고치면 그 결과는 검증이 아니라 다시 탐색 자료가 된다.

[입력]
  --selected   select_survey_texts.py가 만든 selected.csv (폼·순서·역할·엔진 지표·글)
  --responses  구글폼 응답 CSV (폼 3개). 파일 이름에 구글폼 제목의 "설문 N_3"이 들어 있어야
               어느 폼의 응답인지 알 수 있다. 파일 이름을 바꿨으면 "2=파일.csv"처럼 폼 번호를 붙인다.

[하는 일]
  1. 응답 확인 문항("2를 선택해 주세요")에서 2를 고르지 않은 응답자를 뺀다.
  2. 폼 3개의 응답을 글(candidate_id) 단위로 합친다. 폼 공통 글 2개는 세 폼의 응답이 모두 들어간다
     → 글 32개. 글마다 체감 난이도 평균(1~5)을 낸다.
  3. 주 분석: difficulty_score_v2와 체감 난이도 평균의 Spearman 순위 상관(ρ)과 95% 신뢰구간.
       - 신뢰구간: Fisher z 변환(Spearman 분산 1.06/(n−3), 사전 지정). 부트스트랩 1만 번으로 다시 확인.
       - 순열 검정 1만 번(체감 평균을 섞어 ρ가 우연히 이만큼 나올 확률).
  4. 판정 (사전 고정):
       성공      ρ ≥ 0.5, 신뢰구간 하한 > 0, 글자 수의 ρ보다 큼 (셋 다)
       부분 성공  성공이 아니고 ρ ≥ 0.3
       실패      ρ < 0.3
  5. 함께 보는 것 (판정에는 쓰지 않음): Jo 점수·GL 원값·명사 나열 길이·어려운 단어 개수 등의 ρ,
     72.7점(GL 9) 기준이 체감 상위 글을 맞히는 정밀도·재현율, 반분 신뢰도(응답자 평균의 일관성
     = 엔진 상관이 넘을 수 없는 대략적 상한), 공통 글로 본 폼 간 응답 수준 차이, 응답자 평균을
     뺀 체감 값으로 다시 잰 ρ.

[출력] (기본 output/survey2/analysis/, git 제외)
  report.md     읽는 글: 결과·판정·주의점
  per_text.csv  글별 체감 평균과 엔진 지표
  summary.json  모든 숫자

[실행]
  python analyze_survey2.py --responses "[Uniaccess 2차 설문 1_3] ... (응답).csv" ^
                                        "[Uniaccess 2차 설문 2_3] ... (응답).csv" ^
                                        "[Uniaccess 2차 설문 3_3] ... (응답).csv"
  python analyze_survey2.py --responses 1=a.csv 2=b.csv 3=c.csv      # 파일 이름을 바꾼 경우

  종료 코드: 0 정상, 1 파일 없음·읽기 실패, 2 입력이 서로 맞지 않음(폼 번호·문항 번호가 selected.csv와 다름)

[재현]
  표준 라이브러리만 쓴다. 같은 입력과 같은 --seed(기본 20261014)면 같은 결과가 나온다.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import re
import statistics
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
DEFAULT_SELECTED = PROJECT_ROOT / "output" / "survey2" / "selected.csv"
DEFAULT_OUT = PROJECT_ROOT / "output" / "survey2" / "analysis"

# ── 사전 고정한 값 (응답을 보기 전에 정함. 결과를 보고 바꾸지 않는다) ──────────────────
SEED = 20261014
RESAMPLES = 10_000          # 부트스트랩·순열 검정 횟수
SPLIT_REPEATS = 200         # 반분 신뢰도를 다시 나누는 횟수
MIN_RATINGS = 5             # 글 하나에 응답이 이보다 적으면 그 글은 분석에서 뺀다
TARGET_RATINGS = 20         # 설계상 글마다 응답 수 (응답자 약 60명 = 폼마다 약 20명, 고유 글은 한 폼에만 있음)
INTERIM_BELOW = 15          # 글마다 응답 수의 중앙값이 이보다 적으면 보고서에 "중간 결과"라고 적는다
ATTENTION_ANSWER = 2        # 응답 확인 문항에서 골라야 하는 값
SUCCESS_RHO = 0.5
PARTIAL_RHO = 0.3
Z95 = 1.959963984540054
# Spearman 상관을 Fisher z로 바꾼 값의 분산은 1.06/(n−3) (Fieller, Hartley, Pearson 1957).
# 피어슨의 1/(n−3)보다 약간 크다. 표준오차는 √(1.06/(n−3)) ≈ 1.03/√(n−3).
FISHER_VARIANCE_FACTOR = 1.06
# difficulty_engine.THRESHOLD_DIFFICULTY_SCORE와 같아야 한다(GL 9 = (9−1)/11×100). 테스트가 확인한다.
THRESHOLD_DIFFICULTY_SCORE = 72.7

PRIMARY = "difficulty_score_v2"
BASELINE = "chars"
METRICS = [   # (selected.csv 열, 보고서에 적는 이름)
    ("difficulty_score_v2", "종합 난이도 v2 (주 분석)"),
    ("difficulty_score", "Jo 난이도 점수 (0~100으로 자른 값)"),
    ("gl_raw", "GL 원값 (자르기 전)"),
    ("noun_eojeol_run", "명사 나열 길이 (어절)"),
    ("hard_noun_count", "어려운 단어 개수"),
    ("avg_sentence_length", "평균 문장 길이 (어절)"),
    ("easy_word_ratio", "쉬운 단어 비율"),
    ("chars", "글자 수 (비교 기준)"),
]

EXIT_BAD_FILES = 1
EXIT_MISMATCH = 2

_POSITION = re.compile(r"^\s*글\s*(\d+)\s*\.")
_FORM_IN_NAME = re.compile(r"설문\s*(\d+)\s*[_/／]\s*(\d+)")


class InputMismatch(Exception):
    """응답 파일이 selected.csv와 맞지 않는다(폼이 바뀌었거나 문항이 다르다)."""


# ── 통계 함수 (표준 라이브러리만) ─────────────────────────────────────────────

def average_ranks(values: list[float]) -> list[float]:
    """작은 값부터 1, 2, 3… 순위. 같은 값은 평균 순위."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start
        while end + 1 < len(order) and values[order[end + 1]] == values[order[start]]:
            end += 1
        average = (start + end) / 2 + 1
        for position in range(start, end + 1):
            ranks[order[position]] = average
        start = end + 1
    return ranks


def pearson(x: list[float], y: list[float]) -> float | None:
    n = len(x)
    if n < 2 or n != len(y):
        return None
    mean_x, mean_y = sum(x) / n, sum(y) / n
    sxx = sum((a - mean_x) ** 2 for a in x)
    syy = sum((b - mean_y) ** 2 for b in y)
    if sxx == 0 or syy == 0:
        return None   # 한쪽이 모두 같은 값이면 순위 상관을 정의할 수 없다
    sxy = sum((a - mean_x) * (b - mean_y) for a, b in zip(x, y))
    return max(-1.0, min(1.0, sxy / math.sqrt(sxx * syy)))


def spearman(x: list[float], y: list[float]) -> float | None:
    return pearson(average_ranks(x), average_ranks(y))


def fisher_ci(rho: float | None, n: int) -> tuple[float, float] | None:
    """Spearman ρ의 95% 신뢰구간 (Fisher z, 분산 1.06/(n−3))."""
    if rho is None or n <= 3:
        return None
    z = math.atanh(max(-0.999999, min(0.999999, rho)))
    margin = Z95 * math.sqrt(FISHER_VARIANCE_FACTOR / (n - 3))
    return math.tanh(z - margin), math.tanh(z + margin)


def percentile(sorted_values: list[float], q: float) -> float:
    """선형 보간 백분위수 (q는 0~1)."""
    position = q * (len(sorted_values) - 1)
    low = math.floor(position)
    high = math.ceil(position)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (position - low)


def bootstrap_ci(x: list[float], y: list[float], rng: random.Random,
                 resamples: int = RESAMPLES) -> dict:
    """글을 중복을 허용해 다시 뽑아(n개) ρ를 구하기를 반복한 분포의 2.5~97.5 백분위."""
    n = len(x)
    values = []
    for _ in range(resamples):
        picks = [rng.randrange(n) for _ in range(n)]
        rho = spearman([x[i] for i in picks], [y[i] for i in picks])
        if rho is not None:
            values.append(rho)
    if len(values) < max(2, resamples // 2):
        return {"low": None, "high": None, "valid_resamples": len(values)}
    values.sort()
    return {"low": percentile(values, 0.025), "high": percentile(values, 0.975),
            "valid_resamples": len(values)}


def permutation_p(x: list[float], y: list[float], rng: random.Random,
                  resamples: int = RESAMPLES) -> float | None:
    """체감 값을 섞었을 때 |ρ|가 관측값 이상 나올 비율 (양쪽 검정, +1 보정)."""
    n = len(x)
    rx, ry = average_ranks(x), average_ranks(y)
    mean_x, mean_y = sum(rx) / n, sum(ry) / n
    cx = [a - mean_x for a in rx]
    cy = [b - mean_y for b in ry]
    sxx, syy = sum(a * a for a in cx), sum(b * b for b in cy)
    if sxx == 0 or syy == 0:
        return None
    scale = math.sqrt(sxx * syy)
    observed = abs(sum(a * b for a, b in zip(cx, cy))) / scale
    count = 0
    for _ in range(resamples):
        rng.shuffle(cy)
        if abs(sum(a * b for a, b in zip(cx, cy))) / scale >= observed - 1e-12:
            count += 1
    return (count + 1) / (resamples + 1)


def spearman_brown(r: float | None) -> float | None:
    """반으로 나눈 두 점수의 상관 r로부터 전체 길이의 신뢰도를 추정한다."""
    if r is None or r <= -1:
        return None
    return 2 * r / (1 + r)


def split_half_reliability(ratings_by_text: list[list[float]], rng: random.Random,
                           repeats: int = SPLIT_REPEATS) -> dict:
    """글마다 응답자를 무작위로 반씩 나눠 두 평균의 글 간 상관을 구하기를 반복한다."""
    values = []
    for _ in range(repeats):
        first, second = [], []
        for ratings in ratings_by_text:
            shuffled = ratings[:]
            rng.shuffle(shuffled)
            half = len(shuffled) // 2
            first.append(statistics.fmean(shuffled[:half]))
            second.append(statistics.fmean(shuffled[half:]))
        corrected = spearman_brown(spearman(first, second))
        if corrected is not None:
            values.append(corrected)
    if not values:
        return {"mean": None, "low": None, "high": None, "repeats": 0, "max_attainable_rho": None}
    values.sort()
    mean = statistics.fmean(values)
    return {"mean": mean, "low": percentile(values, 0.025), "high": percentile(values, 0.975),
            "repeats": len(values),
            # 체감 평균이 이 정도로만 일관되면 어떤 엔진도 ρ가 대략 √신뢰도를 넘기 어렵다
            "max_attainable_rho": math.sqrt(mean) if mean > 0 else 0.0}


def kruskal_wallis_permutation(groups: list[list[float]], rng: random.Random,
                               resamples: int = RESAMPLES) -> dict | None:
    """폼(집단) 사이의 응답 수준 차이: Kruskal–Wallis H(동점 보정)와 순열 p."""
    groups = [g for g in groups if g]
    if len(groups) < 2:
        return None
    pooled = [v for g in groups for v in g]
    n = len(pooled)
    ranks = average_ranks(pooled)
    ties = {}
    for v in pooled:
        ties[v] = ties.get(v, 0) + 1
    correction = 1 - sum(t ** 3 - t for t in ties.values()) / (n ** 3 - n)
    if correction <= 0:
        return None   # 모든 응답이 같은 값
    sizes = [len(g) for g in groups]

    def statistic(order: list[float]) -> float:
        total, start = 0.0, 0
        for size in sizes:
            total += sum(order[start:start + size]) ** 2 / size
            start += size
        return (12 / (n * (n + 1)) * total - 3 * (n + 1)) / correction

    observed = statistic(ranks)
    shuffled = ranks[:]
    count = 0
    for _ in range(resamples):
        rng.shuffle(shuffled)
        if statistic(shuffled) >= observed - 1e-9:
            count += 1
    return {"h": observed, "p": (count + 1) / (resamples + 1)}


def classify(primary: dict, baseline: dict | None) -> dict:
    """사전 고정한 판정 규칙을 적용한다."""
    rho = primary.get("rho")
    low = (primary.get("fisher_ci") or [None])[0]
    baseline_rho = baseline.get("rho") if baseline else None
    if rho is None:
        return {"status": "undetermined", "label": "판정 불가",
                "reasons": ["주 분석값을 계산할 수 없습니다(글이 너무 적거나 값이 모두 같음)."]}
    beats_baseline = baseline_rho is None or rho > baseline_rho
    ci_above_zero = low is not None and low > 0

    if rho >= SUCCESS_RHO and ci_above_zero and beats_baseline:
        reason = f"ρ={rho:.2f} ≥ {SUCCESS_RHO}, 신뢰구간 하한 {low:.2f} > 0"
        if baseline_rho is not None:
            reason += f", 글자 수의 ρ({baseline_rho:.2f})보다 큼"
        return {"status": "success", "label": "성공", "reasons": [reason]}
    if rho >= PARTIAL_RHO:
        if rho >= SUCCESS_RHO:   # ρ는 충분한데 성공 기준의 나머지 조건을 못 채운 경우
            reasons = []
            if not ci_above_zero:
                reasons.append("신뢰구간이 0을 포함합니다.")
            if not beats_baseline:
                reasons.append(f"글자 수의 ρ({baseline_rho:.2f})보다 높지 않습니다.")
        else:
            reasons = [f"ρ={rho:.2f}가 {PARTIAL_RHO}~{SUCCESS_RHO} 사이입니다."]
        return {"status": "partial", "label": "부분 성공", "reasons": reasons}
    return {"status": "failure", "label": "실패", "reasons": [f"ρ={rho:.2f} < {PARTIAL_RHO}"]}


# ── 입력 읽기 ────────────────────────────────────────────────────────────────

def read_csv_rows(path: Path) -> tuple[list[str], list[list[str]]]:
    for encoding in ("utf-8-sig", "cp949"):
        try:
            with path.open("r", encoding=encoding, newline="") as f:
                rows = list(csv.reader(f))
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"{path}: 인코딩을 읽을 수 없습니다(utf-8, cp949 모두 실패)")
    if not rows:
        raise ValueError(f"{path}: 비어 있는 파일입니다")
    return rows[0], rows[1:]


def to_float(value) -> float | None:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def load_selected(path: Path) -> tuple[dict, dict]:
    """selected.csv → ({폼: {순서: 행}}, {candidate_id: 글 정보})."""
    header, rows = read_csv_rows(path)
    forms: dict[int, dict[int, dict]] = {}
    texts: dict[str, dict] = {}
    for values in rows:
        row = dict(zip(header, values))
        form, position = int(row["form"]), int(row["position"])
        if form in forms and position in forms[form]:
            raise ValueError(f"{path}: 폼 {form}의 {position}번 문항이 두 번 나옵니다")
        forms.setdefault(form, {})[position] = row
        if row["role"] == "attention":
            continue
        info = texts.setdefault(row["candidate_id"], {
            "candidate_id": row["candidate_id"], "role": row["role"], "forms": [],
            "text": row.get("text", ""), "site": row.get("site", ""),
            "gl_bin": row.get("gl_bin", ""), "length_group": row.get("length_group", ""),
            **{key: to_float(row.get(key)) for key, _ in METRICS},
        })
        info["forms"].append(form)
    if not forms or not texts:
        raise ValueError(f"{path}: 글이 하나도 없습니다")
    return forms, texts


def assign_response_files(specs: list[str], form_count: int) -> dict[int, Path]:
    """--responses 인자 → {폼 번호: 파일}. 폼 번호는 'N=파일'이나 파일 이름의 '설문 N_K'에서 얻는다."""
    assigned: dict[int, Path] = {}
    for spec in specs:
        explicit = re.match(r"^(\d+)=(.+)$", spec)
        if explicit:
            form, path = int(explicit.group(1)), Path(explicit.group(2))
        else:
            path = Path(spec)
            found = _FORM_IN_NAME.search(path.name)
            if not found:
                raise InputMismatch(
                    f"{path.name}: 파일 이름에서 폼 번호('설문 N_{form_count}')를 찾을 수 없습니다. "
                    f"'폼번호=파일'로 직접 지정해 주세요(예: 2={path.name}).")
            form = int(found.group(1))
            if int(found.group(2)) != form_count:
                raise InputMismatch(
                    f"{path.name}: 파일 이름은 폼이 {found.group(2)}개인 설문인데 selected.csv에는 "
                    f"{form_count}개입니다. 다른 설문의 응답이 아닌지 확인하세요.")
        if form < 1 or form > form_count:
            raise InputMismatch(f"{path.name}: 폼 번호 {form}이 selected.csv의 폼(1~{form_count})에 없습니다.")
        if form in assigned:
            raise InputMismatch(f"폼 {form}에 파일이 둘입니다: {assigned[form].name}, {path.name}. "
                                "폼마다 응답 파일은 하나여야 합니다.")
        assigned[form] = path
    return assigned


def read_form_responses(path: Path, form: int, layout: dict[int, dict]) -> dict:
    """응답 CSV 한 개 → 응답자 목록. 문항 번호가 selected.csv의 이 폼과 다르면 InputMismatch."""
    header, rows = read_csv_rows(path)
    columns = {}
    attention_column = None
    frequency_column = None
    for index, title in enumerate(header):
        found = _POSITION.match(title)
        if found:
            position = int(found.group(1))
            if position in columns:
                raise InputMismatch(f"{path.name}: '글 {position}.' 문항이 두 번 나옵니다.")
            columns[position] = index
            if "응답 확인" in title:
                attention_column = position
        elif "이용하는 빈도" in title:
            frequency_column = index

    expected = sorted(layout)
    expected_attention = [p for p, row in layout.items() if row["role"] == "attention"]
    if sorted(columns) != expected:
        raise InputMismatch(
            f"{path.name}: 글 문항이 {sorted(columns)}번인데 selected.csv의 폼 {form}은 {expected}번입니다. "
            f"폼 {form}의 응답 파일이 맞는지 확인하세요.")
    if attention_column != (expected_attention[0] if expected_attention else None):
        raise InputMismatch(
            f"{path.name}: 응답 확인 문항이 {attention_column}번인데 selected.csv의 폼 {form}은 "
            f"{expected_attention[0] if expected_attention else None}번입니다.")

    respondents = []
    for number, values in enumerate(rows, 1):
        if not any(cell.strip() for cell in values):
            continue
        ratings = {}
        for position, index in columns.items():
            value = to_float(values[index]) if index < len(values) else None
            if value is not None:
                ratings[position] = value
        frequency = values[frequency_column].strip() if frequency_column is not None and frequency_column < len(values) else ""
        respondents.append({
            "form": form, "row": number, "ratings": ratings, "frequency": frequency,
            "passed": ratings.get(attention_column) == ATTENTION_ANSWER,
        })
    return {"respondents": respondents, "attention_position": attention_column}


# ── 분석 ─────────────────────────────────────────────────────────────────────

def collect_ratings(forms: dict, responses: dict[int, dict]) -> tuple[dict, dict]:
    """합격한 응답자의 평점을 글(candidate_id) 단위로 모은다. 응답자 평균을 뺀 값도 함께 만든다."""
    by_text: dict[str, list[dict]] = {}
    respondent_stats = {}
    for form, loaded in sorted(responses.items()):
        layout = forms[form]
        passed = [r for r in loaded["respondents"] if r["passed"]]
        respondent_stats[form] = {"responses": len(loaded["respondents"]), "passed": len(passed),
                                  "dropped": len(loaded["respondents"]) - len(passed)}
        for respondent in passed:
            text_ratings = {pos: val for pos, val in respondent["ratings"].items()
                            if layout[pos]["role"] != "attention"}
            if not text_ratings:
                continue
            own_mean = statistics.fmean(text_ratings.values())
            for position, value in text_ratings.items():
                by_text.setdefault(layout[position]["candidate_id"], []).append(
                    {"form": form, "rating": value, "centered": value - own_mean})
    return by_text, respondent_stats


def correlate(name: str, label: str, values: list[float], ratings: list[float],
              seed: int, resamples: int) -> dict:
    n = len(values)
    rho = spearman(values, ratings)
    entry = {"metric": name, "label": label, "n": n, "rho": rho,
             "fisher_ci": list(fisher_ci(rho, n)) if fisher_ci(rho, n) else None,
             "bootstrap_ci": None, "permutation_p": None}
    if rho is not None and n >= 4:
        boot = bootstrap_ci(values, ratings, random.Random(seed), resamples)
        entry["bootstrap_ci"] = [boot["low"], boot["high"]] if boot["low"] is not None else None
        entry["permutation_p"] = permutation_p(values, ratings, random.Random(seed + 1), resamples)
    return entry


def confusion(engine_high: list[bool], perceived_high: list[bool]) -> dict:
    tp = sum(e and p for e, p in zip(engine_high, perceived_high))
    fp = sum(e and not p for e, p in zip(engine_high, perceived_high))
    fn = sum(p and not e for e, p in zip(engine_high, perceived_high))
    tn = sum(not e and not p for e, p in zip(engine_high, perceived_high))
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None}


def analyze(selected_path: Path, response_specs: list[str], seed: int = SEED,
            resamples: int = RESAMPLES, min_ratings: int = MIN_RATINGS) -> dict:
    forms, texts = load_selected(selected_path)
    files = assign_response_files(response_specs, len(forms))
    responses = {form: read_form_responses(path, form, forms[form]) for form, path in sorted(files.items())}
    by_text, respondent_stats = collect_ratings(forms, responses)

    warnings = []
    missing_forms = sorted(set(forms) - set(files))
    for form in missing_forms:
        warnings.append(f"폼 {form}의 응답 파일이 없어 그 폼에만 있는 글은 분석에서 빠집니다.")

    included, excluded = [], []
    for candidate_id in sorted(texts):
        ratings = by_text.get(candidate_id, [])
        (included if len(ratings) >= min_ratings else excluded).append(candidate_id)
    for candidate_id in excluded:
        warnings.append(f"{candidate_id}: 응답이 {len(by_text.get(candidate_id, []))}개(<{min_ratings})라 뺐습니다.")

    per_text = []
    for candidate_id in included:
        values = [r["rating"] for r in by_text[candidate_id]]
        centered = [r["centered"] for r in by_text[candidate_id]]
        info = texts[candidate_id]
        per_text.append({
            **info, "forms": sorted(set(r["form"] for r in by_text[candidate_id])),
            "n_ratings": len(values), "mean_rating": statistics.fmean(values),
            "median_rating": statistics.median(values),
            "sd_rating": statistics.stdev(values) if len(values) > 1 else None,
            "centered_mean": statistics.fmean(centered),
        })

    means = [t["mean_rating"] for t in per_text]
    result = {
        "parameters": {"seed": seed, "resamples": resamples, "split_repeats": SPLIT_REPEATS,
                       "min_ratings": min_ratings, "attention_answer": ATTENTION_ANSWER,
                       "threshold_difficulty_score": THRESHOLD_DIFFICULTY_SCORE},
        "inputs": {"selected": selected_path.name, "responses": {str(f): p.name for f, p in sorted(files.items())}},
        "respondents": {
            "per_form": {str(f): s for f, s in respondent_stats.items()},
            "total": sum(s["responses"] for s in respondent_stats.values()),
            "passed": sum(s["passed"] for s in respondent_stats.values()),
            "dropped": sum(s["dropped"] for s in respondent_stats.values()),
            "frequency": {},
        },
        "texts": {"in_design": len(texts), "analyzed": len(per_text), "excluded": excluded,
                  "ratings_per_text": None},
        "warnings": warnings,
        "per_text": per_text,
    }
    frequency = {}
    for loaded in responses.values():
        for respondent in loaded["respondents"]:
            if respondent["passed"] and respondent["frequency"]:
                frequency[respondent["frequency"]] = frequency.get(respondent["frequency"], 0) + 1
    result["respondents"]["frequency"] = dict(sorted(frequency.items()))

    if per_text:
        counts = [t["n_ratings"] for t in per_text]
        result["texts"]["ratings_per_text"] = {"min": min(counts), "median": statistics.median(counts),
                                               "max": max(counts), "target": TARGET_RATINGS}
        result["interim"] = statistics.median(counts) < INTERIM_BELOW

    if len(per_text) < 4:
        result["metrics"], result["verdict"] = [], classify({"rho": None}, None)
        result["warnings"].append("분석할 수 있는 글이 4개 미만이라 상관을 계산하지 않았습니다.")
        return result

    # 주 분석과 함께 보는 지표
    metric_results = []
    for name, label in METRICS:
        pairs = [(t[name], t["mean_rating"]) for t in per_text if t.get(name) is not None]
        if len(pairs) < 4:
            continue
        metric_results.append(correlate(name, label, [p[0] for p in pairs], [p[1] for p in pairs],
                                        seed, resamples))
    result["metrics"] = metric_results
    by_name = {m["metric"]: m for m in metric_results}
    primary = by_name.get(PRIMARY, {"rho": None})
    result["verdict"] = classify(primary, by_name.get(BASELINE))

    # 응답자 평균을 뺀 체감 값으로 다시 잰 주 분석 ρ (폼마다 응답자가 달라서 생기는 후한 점수·박한 점수 보정)
    pairs = [(t[PRIMARY], t["centered_mean"]) for t in per_text if t.get(PRIMARY) is not None]
    centered_rho = spearman([p[0] for p in pairs], [p[1] for p in pairs]) if len(pairs) >= 4 else None
    result["robustness"] = {"centered_rho_primary": centered_rho}

    # 72.7점 기준이 체감 상위 글을 맞히는가 (현재 쓰는 규칙: Jo 난이도 점수 ≥ 72.7이면 수정 제안)
    rated = [t for t in per_text if t.get("difficulty_score") is not None]
    engine_high = [t["difficulty_score"] >= THRESHOLD_DIFFICULTY_SCORE for t in rated]
    median_mean = statistics.median(means)
    high_by_median = [t["mean_rating"] > median_mean for t in rated]
    high_by_three = [t["mean_rating"] > 3 for t in rated]
    result["threshold"] = {
        "difficulty_score": THRESHOLD_DIFFICULTY_SCORE,
        "engine_high": sum(engine_high), "texts": len(rated),
        "perceived_high_median": {"cutoff": median_mean, **confusion(engine_high, high_by_median)},
        "perceived_high_over_3": {"cutoff": 3.0, **confusion(engine_high, high_by_three)},
    }
    for t, flag, by_med, by_3 in zip(rated, engine_high, high_by_median, high_by_three):
        t["engine_high"], t["perceived_high_median"], t["perceived_high_over_3"] = flag, by_med, by_3

    # 체감 평균의 일관성(반분 신뢰도)
    reliability = split_half_reliability(
        [[r["rating"] for r in by_text[t["candidate_id"]]] for t in per_text if t["n_ratings"] >= 2],
        random.Random(seed + 2))
    result["reliability"] = reliability

    # 공통 글: 폼 사이에 응답 수준이 다른가
    common = []
    for t in per_text:
        if t["role"] != "common":
            continue
        groups = {}
        for r in by_text[t["candidate_id"]]:
            groups.setdefault(r["form"], []).append(r["rating"])
        form_means = {str(f): {"n": len(v), "mean": statistics.fmean(v)} for f, v in sorted(groups.items())}
        spread = max(m["mean"] for m in form_means.values()) - min(m["mean"] for m in form_means.values())
        common.append({"candidate_id": t["candidate_id"], "forms": form_means, "mean_spread": spread,
                       "kruskal_wallis": kruskal_wallis_permutation(
                           [groups[f] for f in sorted(groups)], random.Random(seed + 3), resamples)
                       if len(groups) > 1 else None})
    result["common_texts"] = common
    return result


# ── 출력 ─────────────────────────────────────────────────────────────────────

def fmt(value, digits: int = 2) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def fmt_ci(ci, digits: int = 2) -> str:
    return "—" if not ci or ci[0] is None else f"[{ci[0]:.{digits}f}, {ci[1]:.{digits}f}]"


def write_per_text(path: Path, per_text: list[dict]) -> None:
    fields = ["candidate_id", "role", "forms", "gl_bin", "length_group", "n_ratings", "mean_rating",
              "median_rating", "sd_rating", "centered_mean", "engine_high", "perceived_high_median",
              "perceived_high_over_3"] + [name for name, _ in METRICS] + ["site", "text"]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for t in per_text:
            row = {key: t.get(key, "") for key in fields}
            row["forms"] = ",".join(str(x) for x in t["forms"])
            for key in ("mean_rating", "median_rating", "sd_rating", "centered_mean"):
                row[key] = "" if t.get(key) is None else round(t[key], 4)
            for key in ("engine_high", "perceived_high_median", "perceived_high_over_3"):
                row[key] = "" if key not in t else ("Y" if t[key] else "N")
            writer.writerow({k: ("" if v is None else v) for k, v in row.items()})


def build_report(result: dict) -> str:
    lines = []
    add = lines.append
    verdict = result["verdict"]
    respondents = result["respondents"]
    texts = result["texts"]
    interim = result.get("interim", True)

    add("# 2차 설문 분석 결과: 문장 난이도 점수 vs 체감 난이도")
    add("")
    add(f"- 응답 {respondents['total']}건 중 응답 확인 문항을 통과한 {respondents['passed']}건을 분석했습니다"
        f"(탈락 {respondents['dropped']}건).")
    per_form = ", ".join(f"폼 {f}: {s['passed']}/{s['responses']}" for f, s in respondents["per_form"].items())
    add(f"- 폼별 통과/전체: {per_form}")
    if texts["ratings_per_text"]:
        r = texts["ratings_per_text"]
        add(f"- 글 {texts['analyzed']}개(설계 {texts['in_design']}개). 글마다 응답 수: 최소 {r['min']}, "
            f"중앙값 {r['median']:g}, 최대 {r['max']} (설계 목표 약 {r['target']}개).")
    if interim:
        add("")
        add(f"> **중간 결과입니다.** 글마다 응답 수의 중앙값이 {INTERIM_BELOW}개 미만이라 아직 수집이 끝나지 않은 것으로 봅니다. "
            "응답을 더 모은 뒤 같은 명령으로 다시 돌리면 됩니다. 판정은 마감 뒤 한 번만 하세요"
            "(결과를 보다가 좋게 나온 때 멈추면 판정이 부풀려집니다). 중간 결과를 보고 난이도 엔진을 고치지 마세요.")
    for warning in result["warnings"]:
        add(f"- ⚠ {warning}")
    add("")

    add("## 1. 판정 (사전 고정 기준)")
    add("")
    add(f"**{verdict['label']}**")
    for reason in verdict["reasons"]:
        add(f"- {reason}")
    add("")
    add("기준: 성공 = ρ ≥ 0.5이고 신뢰구간 하한 > 0이며 글자 수의 ρ보다 큼 / 부분 성공 = 성공이 아니고 ρ ≥ 0.3 / 실패 = ρ < 0.3. "
        "주 분석은 종합 난이도 v2 하나입니다. 나머지 지표는 함께 보는 참고 자료이고 판정에 쓰지 않습니다.")
    add("")

    if result["metrics"]:
        add("## 2. 지표별 Spearman 순위 상관 (글별 체감 난이도 평균과)")
        add("")
        add("| 지표 | n | ρ | 95% 신뢰구간 (Fisher) | 부트스트랩 구간 | 순열 p |")
        add("|---|---|---|---|---|---|")
        for m in result["metrics"]:
            add(f"| {m['label']} | {m['n']} | {fmt(m['rho'])} | {fmt_ci(m['fisher_ci'])} | "
                f"{fmt_ci(m['bootstrap_ci'])} | {fmt(m['permutation_p'], 4)} |")
        add("")
        add("지표를 여러 개 함께 보므로, 주 분석 말고는 우연히 높게 나온 값이 섞일 수 있습니다. "
            "주 분석 밖의 지표가 더 높게 나와도 그 지표로 엔진을 바꾸지 않고 다음 검증 후보로만 둡니다.")
        add("")
        centered = result.get("robustness", {}).get("centered_rho_primary")
        add(f"- 응답자 평균을 뺀 체감 값으로 다시 잰 v2의 ρ: {fmt(centered)} "
            "(폼마다 응답자가 달라 생기는 후한 점수·박한 점수를 줄인 값. 주 분석과 비슷하면 안심해도 됩니다.)")
        add("")

    if "reliability" in result:
        rel = result["reliability"]
        add("## 3. 체감 평균은 얼마나 일관적인가 (반분 신뢰도)")
        add("")
        add(f"응답자를 무작위로 반씩 나눈 두 평균의 상관에 Spearman–Brown 보정을 한 신뢰도: **{fmt(rel['mean'])}** "
            f"(95% 구간 {fmt_ci([rel['low'], rel['high']])}, {rel['repeats']}회 반복). "
            f"체감 평균이 이 정도로만 일관되면 엔진과의 ρ는 대략 √신뢰도(= **{fmt(rel['max_attainable_rho'])}**) 이하에 머뭅니다. "
            "ρ가 낮게 나왔을 때 엔진 탓인지 응답이 흔들린 탓인지 가르는 데 씁니다.")
        add("")

    if "threshold" in result:
        th = result["threshold"]
        add(f"## 4. {th['difficulty_score']}점(GL 9) 기준이 체감 상위 글을 맞히는가")
        add("")
        add(f"현재 규칙은 Jo 난이도 점수가 {th['difficulty_score']}점 이상이면 수정 제안 대상입니다. "
            f"글 {th['texts']}개 중 엔진이 높다고 한 글은 {th['engine_high']}개입니다.")
        add("")
        add("| 체감 상위의 정의 | 기준값 | 맞힘(TP) | 잘못 지적(FP) | 놓침(FN) | 정밀도 | 재현율 |")
        add("|---|---|---|---|---|---|---|")
        for key, name in (("perceived_high_median", "글 평균이 중앙값보다 높음 (주)"),
                          ("perceived_high_over_3", "글 평균이 3점보다 높음 (보조)")):
            c = th[key]
            add(f"| {name} | {c['cutoff']:.2f} | {c['tp']} | {c['fp']} | {c['fn']} | "
                f"{fmt(c['precision'])} | {fmt(c['recall'])} |")
        add("")

    if result.get("common_texts"):
        add("## 5. 공통 글로 본 폼 간 응답 수준 차이")
        add("")
        add("| 글 | 폼별 평균 (응답 수) | 평균 차이(최대−최소) | Kruskal–Wallis H | 순열 p |")
        add("|---|---|---|---|---|")
        for c in result["common_texts"]:
            forms = ", ".join(f"폼 {f}: {m['mean']:.2f} ({m['n']})" for f, m in c["forms"].items())
            kw = c["kruskal_wallis"]
            add(f"| {c['candidate_id']} | {forms} | {c['mean_spread']:.2f} | "
                f"{fmt(kw['h']) if kw else '—'} | {fmt(kw['p'], 4) if kw else '—'} |")
        add("")
        add("같은 글을 폼마다 다른 사람들이 읽었으므로, 평균 차이가 크면 응답자 집단의 후함·박함이 섞였다는 뜻입니다. "
            "차이가 크면 2절의 '응답자 평균을 뺀' 값을 함께 보세요.")
        add("")

    add("## 읽을 때 주의할 점")
    add("")
    add("- 글이 32개뿐이라 ρ의 신뢰구간이 넓습니다. ρ=0.5라도 95% 구간이 대략 0.17~0.73입니다. 구간을 함께 읽으세요.")
    add("- 체감 난이도는 1~5점 순서 척도의 평균입니다. 글 하나당 응답자가 약 20명이라 평균에도 오차가 있습니다(3절).")
    add("- 글은 GL 구간 5개에서 고르게 뽑았으므로 쉬운 글부터 어려운 글까지 범위가 넓습니다. "
        "실제 웹페이지의 글 분포와는 다르니, 이 ρ를 '페이지 점수의 정확도'로 읽지 마세요.")
    add("- 같은 데이터를 보고 엔진을 고치면 그 결과는 검증이 아니라 탐색 자료가 됩니다. "
        "고친 엔진을 검증하려면 새 설문이 필요합니다.")
    add("")
    add(f"(seed {result['parameters']['seed']}, 부트스트랩·순열 {result['parameters']['resamples']:,}회, "
        f"반분 {result['parameters']['split_repeats']}회. 같은 입력과 seed면 같은 결과가 나옵니다.)")
    return "\n".join(lines) + "\n"


def write_outputs(out_dir: Path, result: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    write_per_text(out_dir / "per_text.csv", result["per_text"])
    summary = {k: v for k, v in result.items() if k != "per_text"}
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "report.md").write_text(build_report(result), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="2차 설문 응답 분석 (문장 난이도 점수 vs 체감 난이도)")
    parser.add_argument("--selected", default=str(DEFAULT_SELECTED), help="selected.csv (기본 output/survey2/selected.csv)")
    parser.add_argument("--responses", nargs="+", required=True,
                        help="구글폼 응답 CSV. 파일 이름에 '설문 N_3'이 없으면 '2=파일.csv'처럼 적는다")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="결과 폴더 (기본 output/survey2/analysis)")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--resamples", type=int, default=RESAMPLES, help="부트스트랩·순열 횟수")
    parser.add_argument("--min-ratings", type=int, default=MIN_RATINGS, help="글 하나에 필요한 최소 응답 수")
    args = parser.parse_args(argv)

    try:
        result = analyze(Path(args.selected), args.responses, args.seed, args.resamples, args.min_ratings)
    except InputMismatch as error:
        print(f"[중단] 입력이 맞지 않습니다: {error}")
        print("       아무것도 저장하지 않았습니다.")
        return EXIT_MISMATCH
    except (OSError, ValueError, KeyError) as error:
        print(f"[오류] 파일을 읽지 못했습니다: {error}")
        return EXIT_BAD_FILES

    out_dir = Path(args.out)
    write_outputs(out_dir, result)
    verdict = result["verdict"]
    primary = next((m for m in result["metrics"] if m["metric"] == PRIMARY), None)
    print(f"응답 {result['respondents']['total']}건 중 {result['respondents']['passed']}건 분석, "
          f"글 {result['texts']['analyzed']}/{result['texts']['in_design']}개")
    if primary:
        print(f"주 분석 ({primary['label']}): ρ={fmt(primary['rho'])}, 95% 구간 {fmt_ci(primary['fisher_ci'])}")
    print(f"판정: {verdict['label']}" + (" (중간 결과)" if result.get("interim") else ""))
    for warning in result["warnings"]:
        print(f"  [경고] {warning}")
    print(f"결과: {out_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
