"""
============================================================
 총점 가중치 민감도 분석 (weights_sensitivity.py)
============================================================

[왜 필요한가]
  총점은 규칙 기반 50% + 텍스트 난이도 30% + CV 20%로 합산한다(run_all.py).
  이 5:3:2는 통계로 구한 값이 아니라 설계 판단이다(법적 기준 적합성 > 이해 용이성 > 명암비).
  판단으로 정한 값이므로, "다른 비율이었어도 사이트 순위와 등급이 같았을까?"를 확인해 두어야
  결과가 이 비율 때문에 나온 것이 아니라고 말할 수 있다.

[무엇을 하나]
  이미 측정해 둔 result_final.json의 모듈별 점수(score_breakdown.module_scores)만 읽어서
  가중치를 바꿔 가며 총점을 다시 합산한다. 브라우저·외부 API를 쓰지 않으므로 몇 초면 끝난다.
  이 파일은 결과 숫자를 만들어 내지 않는다. 실행해서 나온 값만 보고서에 쓴다.

    [1] 사이트별 모듈 점수, 모듈별 분포, 모듈 사이 상관
    [2] 현재 가중치(5:3:2)의 실제 영향 — 명목 가중치, 점수 흩어짐(SD), 총점과의 상관, 분산 기여율
    [3] 가중치 방식별 사이트 총점·등급
    [4] 현재 가중치 대비 변화 — 켄달 tau, 순위 최대 이동, 등급이 바뀐 사이트 수
    [5] 무작위 가중치 시뮬레이션 — 현재 가중치를 각각 ±50% 흔들었을 때 순위가 얼마나 유지되는가

[사용법]
  cd graduation_project
  python weights_sensitivity.py                          # output/_archive 아래의 result_final.json 전부
  python weights_sensitivity.py output/_archive          # 폴더를 지정(하위 폴더까지 찾는다)
  python weights_sensitivity.py a/result_final.json b/result_final.json
  python weights_sensitivity.py --exclude-warned         # 데이터 품질 경고가 있는 사이트를 빼고 비교
  python weights_sensitivity.py --scheme 6:2:2 --scheme 45:35:20   # 비교할 가중치를 직접 지정
  python weights_sensitivity.py --csv sensitivity.csv --json sensitivity.json
  python weights_sensitivity.py --random 0               # 무작위 시뮬레이션 생략

[입력 조건]
  - 규칙 기반·텍스트 난이도·CV 세 모듈 점수가 모두 있는 사이트만 쓴다. 하나라도 빠졌으면
    어떤 가중치에서도 같은 기준으로 비교할 수 없기 때문이다. 빠진 사이트와 이유는 보고서에 적힌다.
  - 같은 URL의 결과가 여러 개면 analyzed_at이 가장 최근인 것만 쓴다.
  - 모든 결과를 같은 버전의 코드로 측정해야 한다. 텍스트 점수 공식은 10/13에 바뀌었으므로
    (위치 의존·UI 길이 감점 제거) 옛 결과와 새 결과가 섞이면 경고를 출력한다.

[계산 방식]
  - 총점 = Σ(가중치 × 모듈 점수) / Σ(가중치). run_all.calculate_total_score()와 같은 순서·같은
    반올림(소수 첫째 자리)·같은 등급 기준(95/90/85/80/70/60)이다(tests/test_weights_sensitivity.py가 비교한다).
  - 순위·등급·켄달 tau는 반올림한 총점으로 구한다(화면에 보이는 값 그대로 비교).
  - 분산 기여율은 반올림하지 않은 총점으로 구한다: 모듈 i의 기여 = w_i × Cov(모듈 i, 총점) / Var(총점).
    세 값을 더하면 정확히 100%다. 모듈 점수가 사이트마다 거의 같으면 가중치가 커도 기여율이 작다.

[읽는 법과 한계]
  - 사이트가 열 곳 안팎이라 이 분석은 기술(요약) 통계다. 상관과 순위 상관은 불확실성이 매우 커서
    다른 사이트에도 같은 값이 나온다고 일반화할 수 없다.
  - "어느 비율이 옳은가"는 이 분석으로 정할 수 없다. 다른 비율에서도 순위·등급이 같은지만 보여 준다.
  - 종료 코드: 0 분석함, 1 입력 문제(파일 없음·사이트 3곳 미만)
"""

import argparse
import csv
import json
import math
import random
import statistics
import sys
import unicodedata
from datetime import datetime
from itertools import combinations
from pathlib import Path
from urllib.parse import urlsplit

import record_result

# ── 상수 ─────────────────────────────────────────────────────────────────────

MODULES = ('rule_based', 'difficulty', 'cv')
MODULE_LABELS = {'rule_based': '규칙 기반', 'difficulty': '텍스트 난이도', 'cv': 'CV(명암비)'}

# run_all.py의 WEIGHT_RULE_BASED / WEIGHT_DIFFICULTY / WEIGHT_CV 와 비율이 같아야 한다(테스트가 비교).
BASELINE_LABEL = '5:3:2'
DEFAULT_SCHEMES = (
    ('5:3:2', '현재 가중치'),
    ('1:1:1', '동일 가중치'),
    ('6:2:2', '규칙 기반 비중 상향'),
    ('4:4:2', '텍스트 비중 상향'),
    ('4:3:3', 'CV 비중 상향'),
    ('5:3:0', 'CV 제외(CV를 못 잰 사이트의 실제 합산과 같음)'),
    ('5:0:2', '텍스트 제외'),
    ('0:3:2', '규칙 기반 제외'),
)

# run_all.calculate_total_score()의 등급 기준
GRADE_CUTOFFS = ((95, 'A+'), (90, 'A'), (85, 'B+'), (80, 'B'), (70, 'C'), (60, 'D'))

MIN_SITES = 3                    # 순위 비교가 의미 있으려면 최소 3곳
RECONCILE_TOLERANCE = 0.1        # 모듈 점수와 총점이 각각 소수 첫째 자리로 반올림되어 생기는 최대 오차
# 10/13에 바뀐 텍스트 점수 공식: 이 키는 개정 이후 결과의 meta에만 있다
NEW_TEXT_FORMULA_KEY = 'page_score_formula'

CAUTIONS = (
    '사이트가 {n}곳뿐이라 이 분석은 기술(요약) 통계입니다. 상관과 순위 상관은 불확실성이 매우 커서 '
    '다른 사이트에도 같은 값이 나온다고 일반화할 수 없습니다.',
    '5:3:2는 통계로 구한 값이 아니라 설계 판단입니다(법적 기준 적합성 > 이해 용이성 > 명암비). '
    '이 분석은 "다른 비율이었어도 순위와 등급이 같았는가"만 보여 주며 어느 비율이 옳은지는 정하지 않습니다.',
    '명목 가중치와 실제 영향력은 다릅니다. 사이트마다 점수가 거의 같은 모듈은 가중치가 커도 순위를 가르지 못합니다'
    '(Paruolo·Saisana·Saltelli, 2013, J. R. Stat. Soc. A 176(3), 609-634).',
    '총점·순위·등급은 run_all.py와 같이 소수 첫째 자리로 반올림한 총점으로 매겼고, 입력은 result_final.json에 '
    '기록된 모듈 점수(소수 첫째 자리)입니다.',
    '"잴 대상이 없어서 만점에 가까운" 점수(텍스트 블록 0개 등)는 접근성이 좋다는 뜻이 아닙니다. '
    '데이터 품질 경고가 있는 사이트는 --exclude-warned로 빼고 다시 비교해 보세요.',
)


# ── 기본 통계 (표준 라이브러리만 사용) ───────────────────────────────────────

def mean(values):
    return sum(values) / len(values)


def sample_sd(values):
    """표본 표준편차(n-1). 값이 2개 미만이면 None."""
    n = len(values)
    if n < 2:
        return None
    m = mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (n - 1))


def covariance(xs, ys):
    """표본 공분산(n-1). 2개 미만이면 None."""
    n = len(xs)
    if n < 2 or n != len(ys):
        return None
    mx, my = mean(xs), mean(ys)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (n - 1)


def pearson(xs, ys):
    """피어슨 상관계수. 값이 2개 미만이거나 한쪽이 모두 같으면(분산 0) None."""
    n = len(xs)
    if n < 2 or n != len(ys):
        return None
    mx, my = mean(xs), mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 1e-12 or syy <= 1e-12:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return max(-1.0, min(1.0, sxy / math.sqrt(sxx * syy)))


def kendall_tau_b(xs, ys):
    """켄달 tau-b(동점 보정). 비교할 수 없으면(값이 2개 미만, 한쪽이 전부 동점) None."""
    n = len(xs)
    if n < 2 or n != len(ys):
        return None
    concordant = discordant = tied_x = tied_y = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            dx, dy = xs[i] - xs[j], ys[i] - ys[j]
            if dx == 0:
                tied_x += 1
            if dy == 0:
                tied_y += 1
            if dx != 0 and dy != 0:
                if (dx > 0) == (dy > 0):
                    concordant += 1
                else:
                    discordant += 1
    pairs = n * (n - 1) // 2
    denominator = math.sqrt((pairs - tied_x) * (pairs - tied_y))
    return None if denominator == 0 else (concordant - discordant) / denominator


def average_ranks(values):
    """점수가 높을수록 1위. 같은 점수는 평균 순위(예: 공동 2위 둘 → 2.5, 2.5)."""
    order = sorted(range(len(values)), key=lambda i: -values[i])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start
        while end + 1 < len(order) and values[order[end + 1]] == values[order[start]]:
            end += 1
        for k in range(start, end + 1):
            ranks[order[k]] = (start + end) / 2 + 1
        start = end + 1
    return ranks


def percentile(sorted_values, p):
    """가장 가까운 순위 방식의 백분위수(정렬된 값, 0 < p <= 100)."""
    index = max(0, math.ceil(p / 100 * len(sorted_values)) - 1)
    return sorted_values[index]


def describe(values):
    return {
        'n': len(values),
        'mean': mean(values) if values else None,
        'sd': sample_sd(values),
        'min': min(values) if values else None,
        'median': statistics.median(values) if values else None,
        'max': max(values) if values else None,
    }


# ── 가중치·총점 ──────────────────────────────────────────────────────────────

def parse_scheme(text):
    """'5:3:2' → (5.0, 3.0, 2.0). 규칙 기반:텍스트 난이도:CV 순서. 잘못된 입력은 ValueError."""
    parts = str(text).strip().split(':')
    if len(parts) != len(MODULES):
        raise ValueError(f'가중치는 "규칙:난이도:CV" 세 값을 콜론으로 이어 적어야 합니다: {text!r}')
    try:
        weights = tuple(float(part) for part in parts)
    except ValueError:
        raise ValueError(f'가중치는 숫자여야 합니다: {text!r}') from None
    if any(not math.isfinite(w) or w < 0 for w in weights):
        raise ValueError(f'가중치는 0 이상의 숫자여야 합니다: {text!r}')
    if sum(weights) <= 0:
        raise ValueError(f'가중치가 모두 0입니다: {text!r}')
    return weights


def normalize(weights):
    total = sum(weights)
    return tuple(w / total for w in weights)


def weighted_total(scores, weights):
    """모듈 점수(dict)를 가중 합산한다. 합산 순서와 정규화 방식이 run_all.calculate_total_score()와 같다."""
    total_weight = sum(weights)
    weighted_sum = 0
    for module, weight in zip(MODULES, weights):
        weighted_sum += scores[module] * (weight / total_weight)
    return weighted_sum


def grade_for(total):
    for cutoff, grade in GRADE_CUTOFFS:
        if total >= cutoff:
            return grade
    return 'F'


# ── 입력 파일 읽기 ───────────────────────────────────────────────────────────

def discover_result_files(paths):
    """파일은 그대로, 폴더는 하위 폴더까지 뒤져서 result_final.json을 모은다(중복 제거, 정렬)."""
    found = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            found.extend(sorted(path.rglob('result_final.json')))
        elif path.is_file():
            found.append(path)
    unique = []
    seen = set()
    for path in found:
        key = str(path.resolve())
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def load_tracker_names(tracker_path):
    """site_test_tracker.csv에서 {정규화한 URL: 사이트 이름}을 읽는다. 못 읽으면 빈 dict."""
    if not tracker_path:
        return {}
    try:
        _, _, rows = record_result.read_csv_auto_encoding(Path(tracker_path))
    except (OSError, UnicodeDecodeError, csv.Error):
        return {}
    names = {}
    for row in rows:
        url, name = (row.get('url') or '').strip(), (row.get('사이트') or '').strip()
        if url and name:
            names[record_result.normalize_url(url)] = name
    return names


def url_label(url):
    """트래커에 이름이 없을 때 표에 쓸 짧은 이름: 호스트(www. 제외) + 경로."""
    if not url:
        return '(URL 없음)'
    parts = urlsplit(url)
    host = parts.netloc.lower()
    if host.startswith('www.'):
        host = host[4:]
    return (host + parts.path.rstrip('/')) or url


def _timestamp(record):
    """analyzed_at(없거나 깨졌으면 파일 수정 시각)을 초 단위 숫자로."""
    text = record.get('analyzed_at')
    if isinstance(text, str):
        try:
            return datetime.fromisoformat(text).timestamp()
        except ValueError:
            pass
    try:
        return Path(record['path']).stat().st_mtime
    except OSError:
        return 0.0


def text_formula_version(final_data):
    """텍스트 점수가 10/13 이후 공식이면 'new', 그 전 공식이면 'old', 텍스트 결과가 없으면 None."""
    meta = record_result.get_path(final_data, 'modules', 'text_difficulty', 'meta')
    if not isinstance(meta, dict):
        return None
    return 'new' if NEW_TEXT_FORMULA_KEY in meta else 'old'


def load_site_result(path, names=None):
    """result_final.json 하나를 분석용 레코드로 바꾼다. 읽을 수 없으면 error가 채워진다."""
    path = Path(path)
    record = {'path': str(path), 'url': None, 'name': path.parent.name or path.name, 'analyzed_at': None,
              'scores': {m: None for m in MODULES}, 'recorded_total': None, 'recorded_grade': None,
              'weights_applied': None, 'warnings': [], 'text_formula': None, 'error': None}
    data = record_result.load_json(path)
    if not isinstance(data, dict):
        record['error'] = '읽을 수 없는 파일(JSON이 아니거나 비어 있음)'
        return record

    url = data.get('url') if isinstance(data.get('url'), str) else None
    record['url'] = url
    record['analyzed_at'] = data.get('analyzed_at')
    if url:
        record['name'] = (names or {}).get(record_result.normalize_url(url)) or url_label(url)

    module_scores = record_result.get_path(data, 'score_breakdown', 'module_scores')
    if isinstance(module_scores, dict):
        for module in MODULES:
            value = module_scores.get(module)
            if record_result.is_number(value) and math.isfinite(value):
                record['scores'][module] = float(value)
    record['recorded_total'] = data.get('total_score') if record_result.is_number(data.get('total_score')) else None
    record['recorded_grade'] = data.get('grade') if isinstance(data.get('grade'), str) else None
    applied = record_result.get_path(data, 'score_breakdown', 'weights_applied')
    record['weights_applied'] = applied if isinstance(applied, dict) else None
    record['text_formula'] = text_formula_version(data)

    # 보관 폴더에는 result_api.json·result.json도 같이 복사되어 있어서 트래커와 같은 기준으로 경고를 구한다.
    folder = path.parent
    rule_api = record_result.load_json(folder / 'result_api.json')
    try:
        record['warnings'] = record_result.data_quality_warnings(folder, data, rule_api)
    except (TypeError, ValueError, KeyError, AttributeError):
        record['warnings'] = ['데이터 품질 경고를 계산하지 못했습니다(결과 파일 형식이 예상과 다름)']
    return record


def missing_modules(record):
    return [m for m in MODULES if record['scores'][m] is None]


def select_sites(records, exclude_warned=False):
    """분석에 쓸 레코드와, 빠진 이유를 돌려준다 → (kept, excluded[{'record','reason'}])."""
    excluded = []
    duplicates = []

    candidates = []
    for record in records:
        if record['error']:
            excluded.append({'record': record, 'reason': record['error']})
        else:
            candidates.append(record)

    # 같은 URL이면 가장 최근 결과 하나만 (URL을 모르면 파일 경로를 구분자로 쓴다)
    latest = {}
    for record in sorted(candidates, key=lambda r: (_timestamp(r), r['path'])):
        key = record_result.normalize_url(record['url']) if record['url'] else ('path', record['path'])
        if key in latest:
            duplicates.append(latest[key])
        latest[key] = record
    for record in duplicates:
        excluded.append({'record': record, 'reason': '같은 URL의 더 최근 결과가 있어 쓰지 않음'})

    kept = []
    for record in sorted(latest.values(), key=lambda r: r['path']):
        missing = missing_modules(record)
        if missing:
            labels = ', '.join(MODULE_LABELS[m] for m in missing)
            excluded.append({'record': record, 'reason': f'{labels} 점수가 없음(측정 불가·실패)'})
        elif exclude_warned and record['warnings']:
            excluded.append({'record': record, 'reason': '데이터 품질 경고: ' + ' | '.join(record['warnings'])})
        else:
            kept.append(record)
    return kept, excluded


# ── 분석 ─────────────────────────────────────────────────────────────────────

def covariance_matrix(columns):
    return [[covariance(columns[a], columns[b]) for b in MODULES] for a in MODULES]


def decompose(columns, weights, cov, totals_unrounded):
    """가중치(정규화됨)별로 총점의 흩어짐을 모듈이 얼마나 설명하는지.

    - 분산 기여율: w_i × Cov(모듈 i, 총점) / Var(총점) — 세 값의 합이 1.
    - w×SD 비중  : w_i × SD_i / Σ(w_j × SD_j) — 상관을 무시한 단순 비교(참고용).
    - 총점과의 상관: 모듈 i와 총점의 피어슨 상관계수.
    """
    size = len(MODULES)
    variance = sum(weights[i] * weights[j] * cov[i][j] for i in range(size) for j in range(size))
    sds = [math.sqrt(cov[i][i]) if cov[i][i] is not None and cov[i][i] > 0 else 0.0 for i in range(size)]
    spread = sum(weights[i] * sds[i] for i in range(size))

    shares = {}
    sd_shares = {}
    correlations = {}
    for i, module in enumerate(MODULES):
        contribution = weights[i] * sum(weights[j] * cov[i][j] for j in range(size))
        shares[module] = contribution / variance if variance > 1e-12 else None
        sd_shares[module] = weights[i] * sds[i] / spread if spread > 1e-12 else None
        correlations[module] = pearson(columns[module], totals_unrounded)
    return {'total_variance': variance, 'variance_share': shares, 'w_sd_share': sd_shares,
            'pearson_with_total': correlations}


def _rank_metrics(totals, ranks, grades, base_totals, base_ranks, base_grades):
    """기준 방식 대비 변화: 켄달 tau, 순위 최대 이동, 등급이 바뀐 사이트 수, 총점 최대 변화."""
    rank_changes = [abs(r - b) for r, b in zip(ranks, base_ranks)]
    deltas = [t - b for t, b in zip(totals, base_totals)]
    return {
        'tau_vs_baseline': kendall_tau_b(base_totals, totals),
        'max_rank_change': max(rank_changes),
        'grade_changes': sum(1 for g, b in zip(grades, base_grades) if g != b),
        'max_abs_total_change': max(abs(d) for d in deltas),
    }


def simulate_random_weights(rows, base_weights, base_totals, base_ranks, base_grades, draws, spread, seed):
    """현재 가중치를 각각 (1 ± spread) 배 안에서 무작위로 흔들어 순위가 얼마나 유지되는지 본다."""
    rng = random.Random(seed)
    sites = len(rows)
    identical = 0
    taus, max_moves, grade_change_counts = [], [], []
    lowest = [math.inf] * sites
    highest = [-math.inf] * sites
    for _ in range(draws):
        raw = [b * rng.uniform(1 - spread, 1 + spread) for b in base_weights]
        total_weight = sum(raw)
        if total_weight <= 0:      # --spread 100에서 세 값이 모두 0이 될 확률은 사실상 0이지만 0으로 나누지 않게 막는다
            raw, total_weight = list(base_weights), sum(base_weights)
        weights = [w / total_weight for w in raw]
        totals = [round(sum(w * x for w, x in zip(weights, row)), 1) for row in rows]
        ranks = average_ranks(totals)
        grades = [grade_for(t) for t in totals]
        if ranks == base_ranks:
            identical += 1
        tau = kendall_tau_b(base_totals, totals)
        if tau is not None:
            taus.append(tau)
        max_moves.append(max(abs(r - b) for r, b in zip(ranks, base_ranks)))
        grade_change_counts.append(sum(1 for g, b in zip(grades, base_grades) if g != b))
        for i, rank in enumerate(ranks):
            lowest[i] = min(lowest[i], rank)
            highest[i] = max(highest[i], rank)

    taus.sort()
    max_moves.sort()
    return {
        'draws': draws,
        'spread': spread,
        'seed': seed,
        'identical_ranking_rate': identical / draws,
        'tau': {'min': taus[0], 'p5': percentile(taus, 5), 'median': statistics.median(taus)} if taus else None,
        'max_rank_change': {'median': statistics.median(max_moves), 'p95': percentile(max_moves, 95),
                            'max': max_moves[-1]},
        'grade_change_rate': sum(1 for c in grade_change_counts if c) / draws,
        'mean_grade_changes': sum(grade_change_counts) / draws,
        'rank_range': [[lowest[i], highest[i]] for i in range(sites)],
    }


def build_schemes(extra_schemes=None):
    """비교할 가중치 목록. 기준(5:3:2)이 항상 맨 앞이고, 정규화한 값이 같은 것은 한 번만 쓴다."""
    if extra_schemes:
        wanted = [(BASELINE_LABEL, '현재 가중치')] + [(label, '') for label in extra_schemes]
    else:
        wanted = list(DEFAULT_SCHEMES)
    schemes = []
    seen = []
    for label, note in wanted:
        weights = parse_scheme(label)
        normalized = normalize(weights)
        if any(all(abs(a - b) < 1e-12 for a, b in zip(normalized, other)) for other in seen):
            continue
        seen.append(normalized)
        schemes.append({'label': label, 'note': note, 'weights': weights})
    return schemes


def analyze(sites, schemes, random_draws=0, spread=0.5, seed=0):
    """sites: select_sites()가 돌려준 레코드(세 모듈 점수가 모두 있음). schemes[0]이 기준 가중치."""
    if len(sites) < 2:
        raise ValueError('사이트가 2곳 이상 있어야 분석할 수 있습니다')
    columns = {m: [site['scores'][m] for site in sites] for m in MODULES}
    rows = [tuple(site['scores'][m] for m in MODULES) for site in sites]
    cov = covariance_matrix(columns)

    results = []
    for scheme in schemes:
        weights = normalize(scheme['weights'])
        unrounded = [weighted_total(site['scores'], scheme['weights']) for site in sites]
        totals = [round(value, 1) for value in unrounded]
        decomposition = decompose(columns, weights, cov, unrounded)
        results.append({
            'label': scheme['label'],
            'note': scheme['note'],
            'weights': {m: w for m, w in zip(MODULES, weights)},
            'totals': totals,
            'grades': [grade_for(t) for t in totals],
            'ranks': average_ranks(totals),
            **decomposition,
        })

    base = results[0]
    for result in results:
        result.update(_rank_metrics(result['totals'], result['ranks'], result['grades'],
                                    base['totals'], base['ranks'], base['grades']))

    site_records = []
    for site, total in zip(sites, base['totals']):
        diff = None
        if site['recorded_total'] is not None:
            diff = round(total - site['recorded_total'], 3)
        note = None
        if diff is not None and abs(diff) > RECONCILE_TOLERANCE + 1e-9:
            note = (f'기록된 총점 {site["recorded_total"]}과 5:3:2 재계산 {total}의 차이가 {diff:+.1f}점 — '
                    '다른 가중치·다른 버전으로 계산된 결과일 수 있음')
        site_records.append({
            'name': site['name'], 'url': site['url'], 'path': site['path'], 'analyzed_at': site['analyzed_at'],
            'scores': dict(site['scores']), 'recorded_total': site['recorded_total'],
            'recorded_grade': site['recorded_grade'], 'warnings': list(site['warnings']),
            'text_formula': site['text_formula'], 'reconcile_note': note,
        })

    simulation = None
    if random_draws > 0:
        simulation = simulate_random_weights(rows, tuple(schemes[0]['weights']), base['totals'], base['ranks'],
                                             base['grades'], random_draws, spread, seed)

    formulas = [s['text_formula'] for s in sites if s['text_formula']]
    return {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'baseline': base['label'],
        'sites': site_records,
        'module_stats': {m: describe(columns[m]) for m in MODULES},
        'module_correlations': {f'{a}~{b}': pearson(columns[a], columns[b]) for a, b in combinations(MODULES, 2)},
        'schemes': results,
        'random': simulation,
        'text_formula_counts': {'new': formulas.count('new'), 'old': formulas.count('old')},
        'cautions': [text.format(n=len(sites)) for text in CAUTIONS],
    }


# ── 보고서 ───────────────────────────────────────────────────────────────────

def display_width(text):
    """한글 같은 전각 문자는 2칸으로 센다(표 정렬용)."""
    return sum(2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1 for ch in str(text))


def pad(text, width, align='left'):
    gap = max(0, width - display_width(text))
    return str(text) + ' ' * gap if align == 'left' else ' ' * gap + str(text)


def shorten(text, width):
    text = str(text)
    if display_width(text) <= width:
        return text
    out = ''
    for ch in text:
        if display_width(out + ch) > width - 3:
            break
        out += ch
    return out + '...'


def render_table(header, rows, aligns=None, indent='  '):
    aligns = aligns or ['left'] + ['right'] * (len(header) - 1)
    widths = [max(display_width(line[c]) for line in [header] + rows) for c in range(len(header))]
    lines = [indent + '  '.join(pad(header[c], widths[c], aligns[c]) for c in range(len(header))).rstrip(),
             indent + '  '.join('-' * w for w in widths)]
    for row in rows:
        lines.append(indent + '  '.join(pad(row[c], widths[c], aligns[c]) for c in range(len(header))).rstrip())
    return '\n'.join(lines)


def _num(value, digits=1):
    return '-' if value is None else f'{value:.{digits}f}'


def _pct(value, digits=1):
    return '-' if value is None else f'{value * 100:.{digits}f}%'


def _rank(value):
    return str(int(value)) if value == int(value) else f'{value:.1f}'


def _range(low, high):
    return _rank(low) if low == high else f'{_rank(low)}~{_rank(high)}'


def render_report(analysis, input_summary=None):
    """분석 결과를 사람이 읽는 글로 만든다. input_summary: main()이 모은 파일 수·제외 목록."""
    sites = analysis['sites']
    schemes = analysis['schemes']
    base = schemes[0]
    out = []

    out.append('총점 가중치 민감도 분석')
    out.append(f'  기준(현재) 가중치 {analysis["baseline"]} = 규칙 기반 : 텍스트 난이도 : CV (run_all.py)')
    if input_summary:
        out.append(f'  입력 결과 파일 {input_summary["files"]}개 → 분석 대상 {len(sites)}곳, '
                   f'제외 {len(input_summary["excluded"])}개')
        for item in input_summary['excluded']:
            out.append(f'    - 제외: {item["record"]["name"]} — {item["reason"]}')
    else:
        out.append(f'  분석 대상 {len(sites)}곳')

    counts = analysis['text_formula_counts']
    if counts['new'] and counts['old']:
        out.append(f'  [주의] 텍스트 점수 공식이 섞여 있습니다(10/13 이후 공식 {counts["new"]}곳, 이전 공식 {counts["old"]}곳). '
                   '모든 사이트를 같은 코드로 다시 측정한 뒤에 비교하세요.')
    elif counts['old'] and not counts['new']:
        out.append('  [주의] 모든 결과가 10/13 이전 텍스트 점수 공식(위치 의존·UI 길이 감점 포함)으로 계산되었습니다. '
                   '현재 코드의 결과가 아닙니다.')
    for site in sites:
        if site['reconcile_note']:
            out.append(f'  [주의] {site["name"]}: {site["reconcile_note"]}')
    warned = [site for site in sites if site['warnings']]
    if warned:
        out.append(f'  [참고] 데이터 품질 경고가 있는 사이트 {len(warned)}곳 포함(표에서 * 표시). '
                   '--exclude-warned로 빼고 다시 비교할 수 있습니다.')
    out.append('')

    # [1] 사이트별 모듈 점수와 분포
    order = sorted(range(len(sites)), key=lambda i: (base['ranks'][i], sites[i]['name']))
    out.append(f'[1] 사이트별 모듈 점수와 분포 (n={len(sites)})')
    rows = []
    for i in order:
        site = sites[i]
        recorded = '-' if site['recorded_total'] is None else f'{site["recorded_total"]:.1f}({site["recorded_grade"] or "?"})'
        rows.append([_rank(base['ranks'][i]), shorten(site['name'], 30) + (' *' if site['warnings'] else '')] +
                    [_num(site['scores'][m]) for m in MODULES] + [recorded])
    out.append(render_table(['순위', '사이트'] + [MODULE_LABELS[m] for m in MODULES] + ['기록된 총점'], rows,
                            aligns=['right', 'left', 'right', 'right', 'right', 'right']))
    out.append('  순위는 5:3:2로 다시 합산한 총점 기준입니다. 기록된 총점은 result_final.json에 적힌 값입니다.')
    out.append('')
    rows = []
    for module in MODULES:
        s = analysis['module_stats'][module]
        rows.append([MODULE_LABELS[module], _num(s['mean']), _num(s['sd']), _num(s['min']),
                     _num(s['median']), _num(s['max'])])
    out.append(render_table(['모듈', '평균', '표준편차', '최소', '중앙값', '최대'], rows))
    pair_text = []
    for key, value in analysis['module_correlations'].items():
        a, b = key.split('~')
        pair_text.append(f'{MODULE_LABELS[a]}-{MODULE_LABELS[b]} r={_num(value, 2)}')
    out.append('  모듈 사이 상관(피어슨): ' + ', '.join(pair_text))
    out.append('')

    # [2] 현재 가중치의 실제 영향
    out.append(f'[2] 현재 가중치({base["label"]})의 실제 영향')
    rows = []
    for module in MODULES:
        s = analysis['module_stats'][module]
        rows.append([MODULE_LABELS[module], _pct(base['weights'][module]), _num(s['sd']),
                     _pct(base['w_sd_share'][module]), _num(base['pearson_with_total'][module], 2),
                     _pct(base['variance_share'][module])])
    out.append(render_table(['모듈', '명목 가중치', '표준편차', 'w×SD 비중', '총점과의 상관', '분산 기여율'], rows))
    out.append('  분산 기여율 = 가중치 × Cov(모듈, 총점) / Var(총점). 세 값의 합이 100%이며 "사이트마다 총점이 달라지는 정도" 중')
    out.append('  그 모듈이 설명하는 몫입니다. 명목 가중치보다 훨씬 작으면 점수가 비슷하거나 다른 모듈과 반대로 움직여서 순위를 못 가른다는 뜻입니다.')
    out.append('')

    # [3] 사이트별 총점
    out.append('[3] 가중치 방식별 총점(등급)')
    header = ['순위', '사이트'] + [s['label'] for s in schemes]
    rows = []
    for i in order:
        label = shorten(sites[i]['name'], 30) + (' *' if sites[i]['warnings'] else '')
        rows.append([_rank(base['ranks'][i]), label] +
                    [f'{s["totals"][i]:.1f}({s["grades"][i]})' for s in schemes])
    out.append(render_table(header, rows, aligns=['right', 'left'] + ['right'] * len(schemes)))
    for site in warned:
        out.append(f'  * {site["name"]}: ' + ' | '.join(site['warnings']))
    out.append('')

    # [4] 현재 가중치 대비 변화
    out.append(f'[4] {base["label"]} 대비 변화')
    rows = []
    for index, s in enumerate(schemes):
        shares = '/'.join('-' if s['variance_share'][m] is None else str(round(s['variance_share'][m] * 100))
                          for m in MODULES) + '%'
        if index == 0:
            rows.append([s['label'], s['note'], '(기준)', '-', '-', '-', shares])
        else:
            rows.append([s['label'], s['note'], _num(s['tau_vs_baseline'], 2), _rank(s['max_rank_change']),
                         str(s['grade_changes']), _num(s['max_abs_total_change']), shares])
    out.append(render_table(['가중치', '설명', '켄달 τ', '순위 최대 이동', '등급 바뀐 곳', '총점 최대 변화', '분산 기여율(규칙/텍스트/CV)'],
                            rows, aligns=['left', 'left', 'right', 'right', 'right', 'right', 'right']))
    out.append('  켄달 τ: 1이면 순위가 완전히 같고, 값이 작을수록 순위가 많이 뒤바뀝니다(동점은 tau-b로 보정).')
    out.append('')

    # [5] 무작위 가중치
    simulation = analysis['random']
    if simulation:
        out.append(f'[5] 무작위 가중치 {simulation["draws"]}개 — 현재 가중치를 각각 ±{simulation["spread"] * 100:.0f}% 안에서 '
                   f'흔들어 다시 합산(seed={simulation["seed"]})')
        out.append(f'  순위가 현재와 완전히 같았던 비율: {_pct(simulation["identical_ranking_rate"])}')
        tau = simulation['tau']
        if tau:
            out.append(f'  켄달 τ: 최소 {_num(tau["min"], 2)}, 하위 5% {_num(tau["p5"], 2)}, 중앙값 {_num(tau["median"], 2)}')
        move = simulation['max_rank_change']
        out.append(f'  순위 최대 이동(한 사이트가 움직인 가장 큰 폭): 중앙값 {_rank(move["median"])}, '
                   f'상위 95% {_rank(move["p95"])}, 최대 {_rank(move["max"])}')
        out.append(f'  등급이 하나라도 바뀐 비율: {_pct(simulation["grade_change_rate"])} '
                   f'(평균 {simulation["mean_grade_changes"]:.2f}곳)')
        rows = [[shorten(sites[i]['name'], 30), _rank(base['ranks'][i]), _range(*simulation['rank_range'][i])]
                for i in order]
        out.append(render_table(['사이트', '현재 순위', '무작위 순위 범위'], rows))
        out.append('')

    out.append('[해석 주의]')
    for text in analysis['cautions']:
        out.append(f'  - {text}')
    return '\n'.join(out)


# ── 파일 출력 ────────────────────────────────────────────────────────────────

CSV_FIELDS = ['site', 'url', 'scheme', 'weights_percent', 'rule_based', 'difficulty', 'cv', 'total', 'grade',
              'rank', 'baseline_total', 'baseline_grade', 'baseline_rank', 'delta_total', 'rank_change',
              'grade_changed']


def write_csv(path, analysis):
    """사이트 × 가중치 방식 한 줄씩(긴 형식). 엑셀에서 열 수 있게 utf-8-sig로 쓴다."""
    base = analysis['schemes'][0]
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for scheme in analysis['schemes']:
            percent = '/'.join(f'{scheme["weights"][m] * 100:.1f}' for m in MODULES)
            for i, site in enumerate(analysis['sites']):
                writer.writerow({
                    'site': site['name'], 'url': site['url'], 'scheme': scheme['label'], 'weights_percent': percent,
                    'rule_based': site['scores']['rule_based'], 'difficulty': site['scores']['difficulty'],
                    'cv': site['scores']['cv'], 'total': scheme['totals'][i], 'grade': scheme['grades'][i],
                    'rank': scheme['ranks'][i], 'baseline_total': base['totals'][i],
                    'baseline_grade': base['grades'][i], 'baseline_rank': base['ranks'][i],
                    'delta_total': round(scheme['totals'][i] - base['totals'][i], 1),
                    'rank_change': abs(scheme['ranks'][i] - base['ranks'][i]),
                    'grade_changed': 'Y' if scheme['grades'][i] != base['grades'][i] else 'N',
                })


def write_json(path, analysis):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)
        f.write('\n')


def safe_print(text):
    """콘솔 인코딩이 표현하지 못하는 문자가 있어도 멈추지 않고 대체 문자로 출력한다."""
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or 'utf-8'
        print(text.encode(encoding, errors='replace').decode(encoding))


# ── 실행 ─────────────────────────────────────────────────────────────────────

def scheme_argument(text):
    try:
        parse_scheme(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from None
    return text.strip()


def build_parser():
    ap = argparse.ArgumentParser(
        description='총점 가중치(규칙 기반:텍스트 난이도:CV = 5:3:2)를 바꿔 가며 사이트 순위·등급이 얼마나 달라지는지 본다.')
    ap.add_argument('paths', nargs='*',
                    help='result_final.json 또는 그것을 찾을 폴더(하위 폴더까지). 생략하면 output/_archive')
    ap.add_argument('--scheme', action='append', type=scheme_argument, metavar='규칙:난이도:CV',
                    help='현재 가중치와 비교할 가중치(여러 번 쓸 수 있음). 쓰면 기본 비교 목록 대신 이것만 비교')
    ap.add_argument('--exclude-warned', action='store_true', help='데이터 품질 경고가 있는 사이트를 분석에서 뺀다')
    ap.add_argument('--tracker', default=None,
                    help='사이트 이름을 읽을 CSV (기본: site_test_tracker.csv, 없으면 URL로 표시)')
    ap.add_argument('--random', type=int, default=2000, metavar='N', dest='random_draws',
                    help='무작위 가중치 시뮬레이션 횟수 (기본 2000, 0이면 생략)')
    ap.add_argument('--spread', type=float, default=50.0, metavar='PERCENT',
                    help='무작위 시뮬레이션에서 각 가중치를 흔드는 폭, ±%% (기본 50)')
    ap.add_argument('--seed', type=int, default=0, help='무작위 시뮬레이션의 시드 (기본 0, 같은 값이면 같은 결과)')
    ap.add_argument('--csv', metavar='파일', help='사이트 × 가중치 방식 결과를 CSV로 저장')
    ap.add_argument('--json', metavar='파일', help='전체 분석 결과를 JSON으로 저장')
    return ap


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.random_draws < 0:
        parser.error('--random은 0 이상이어야 합니다')
    if not 0 < args.spread <= 100:
        parser.error('--spread는 0보다 크고 100 이하여야 합니다')

    here = Path(__file__).resolve().parent
    paths = args.paths or [str(here / 'output' / '_archive')]
    for raw in paths:
        if not Path(raw).exists():
            safe_print(f'[경고] 경로를 찾을 수 없습니다: {raw}')
    files = discover_result_files(paths)
    if not files:
        safe_print('result_final.json을 찾지 못했습니다: ' + ', '.join(paths))
        safe_print('각 사이트를 run_all.py → record_result.py로 처리하면 output/_archive/<사이트>/에 보관됩니다.')
        return 1

    tracker = args.tracker if args.tracker else (here / 'site_test_tracker.csv')
    names = load_tracker_names(tracker if Path(tracker).exists() else None)
    records = [load_site_result(path, names) for path in files]
    kept, excluded = select_sites(records, exclude_warned=args.exclude_warned)
    summary = {'files': len(files), 'excluded': excluded}
    if len(kept) < MIN_SITES:
        safe_print(f'분석에 쓸 수 있는 사이트가 {len(kept)}곳뿐입니다(최소 {MIN_SITES}곳 필요, 결과 파일 {len(files)}개).')
        for item in excluded:
            safe_print(f'  - 제외: {item["record"]["name"]} — {item["reason"]}')
        return 1

    schemes = build_schemes(args.scheme)
    analysis = analyze(kept, schemes, random_draws=args.random_draws, spread=args.spread / 100, seed=args.seed)
    safe_print(render_report(analysis, summary))
    if args.csv:
        write_csv(args.csv, analysis)
        safe_print(f'\nCSV 저장: {args.csv}')
    if args.json:
        write_json(args.json, analysis)
        safe_print(f'JSON 저장: {args.json}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
