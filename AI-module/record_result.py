"""
============================================================
 동작검증 결과 자동 기록 스크립트 (record_result.py)
============================================================

[목적]
  run_all.py <URL> 실행이 끝난 직후 이 스크립트를 실행하면,
  output/ 의 결과 파일을 읽어서 site_test_tracker.csv의 해당 URL 행을
  자동으로 채운다. 매번 파일을 열어보고 손으로 옮겨 적을 필요가 없다.

[동작 순서]
  0) result_final.json(없으면 result_artifact.json)에 적힌 요청 URL이 넘긴 URL과
     다르면 아무것도 하지 않고 멈춘다. 다른 사이트의 결과를 이 사이트 행에 적거나
     백업하는 실수를 막기 위해서다(--force로 무시할 수 있다).
  1) site_test_tracker.csv에서 url이 일치하는 행을 찾는다.
     (트래커에 이미 10개 사이트의 이름/URL이 채워져 있다고 가정)
  2) output/ 폴더의 결과 파일들을 output/_archive/<사이트슬러그>/로
     복사해둔다 — run_all.py는 다음 실행 시작 시 output/의 결과
     파일을 전부 지우므로(clear_previous_outputs), 다음 사이트를
     돌리기 전에 반드시 이 백업이 먼저 이루어져야 한다.
  3) 결과를 읽어서 행을 채운다 (10/9 개정: 현재 result_final.json 형식 기준).
       - step1~5의 O/X는 모듈의 실제 상태로 판정한다.
           step1 규칙 기반  : modules.rule_based에 점수가 있으면 O
           step2 텍스트 추출: result_text.json이 있으면 O
           step3 난이도     : modules.text_difficulty가 유효하면 O (page_score 있음)
           step4 수정 제안  : modules.text_suggestions가 유효하면 O
           step5 CV         : modules.cv_visual.status가 success면 O (not_measured·failed는 X)
         result_final.json이 없으면(파이프라인이 중간에 죽었거나 차단·빈 문서) 중간 산출물
         파일이 있는지로 판정한다.
       - total_score, grade를 그대로 기록
       - 경고 칸(data_quality_warning=Y, warning_detail)에는 점수가 나왔어도 믿기 어려운 경우를 적는다:
           규칙 결과 없음 / 텍스트 블록 0개 / 난이도 공식을 적용한 문단 0개 /
           CV 측정 불가 / 정적 fallback(봇 대기 화면 → 최초 응답 HTML만 분석) /
           대상 페이지 아님(차단·빈 문서·HTTP 오류, document_health.status)
       - notes에는 [자동] 태그로 레이어 팝업·제외 영역 개수, 분석 중단 사유,
         "모듈 상태와 점수가 앞뒤가 안 맞는" 경우를 남긴다(조용히 넘어가지 않도록).
  4) 기존 notes 셀의 사람이 쓴 메모는 지우지 않고 뒤에 이어붙인다.
     이전 실행이 남긴 [자동...] 항목만 새로 바꾼다.

[사용법]
  cd graduation_project
  python run_all.py https://www.gov.kr
  python record_result.py https://www.gov.kr

  # 이 결과에 대한 메모를 같이 남기고 싶으면
  python record_result.py https://www.gov.kr --note "정상 케이스, 이상 없음"

  # 기본 경로가 다르면
  python record_result.py https://www.gov.kr --output-dir output --tracker site_test_tracker.csv

[주의]
  - 트래커에 없는 URL을 넘기면 에러를 내고 종료한다(오타로 엉뚱한 행이
    새로 생기는 것을 막기 위해). 새 사이트를 추가하려면 --allow-new를 쓴다.
  - output/의 결과가 다른 URL의 것이면 종료 코드 2로 멈춘다. 일부러 기록하려면 --force.
  - 인코딩은 기존 파일이 cp949(윈도우 기본)면 cp949로, UTF-8이면 UTF-8로
    자동 감지해서 그대로 유지한다.
  - 종료 코드: 0 기록함, 1 오류(트래커 없음·URL 없음·파일 잠김), 2 결과의 URL이 다름
"""

import argparse
import csv
import json
import os
import re
import shutil
import sys
from datetime import date
from pathlib import Path
from urllib.parse import unquote, urlparse, urlsplit

FIELDNAMES_DEFAULT = [
    '사이트', 'url', 'site_type', 'test_date',
    'step1_rule_based', 'step2_text_extract', 'step3_difficulty',
    'step4_suggestion', 'step5_cv',
    'total_score', 'grade', 'data_quality_warning', 'warning_detail', 'notes',
]

# output/ 안에서 각 step의 산출물 파일 (result_final.json이 없을 때 성공 여부의 근거)
STEP_FILES = {
    'step1_rule_based': 'result_api.json',
    'step2_text_extract': 'result_text.json',
    'step3_difficulty': 'result_text_difficulty.json',
    'step4_suggestion': 'result_text_suggestions.json',
    'step5_cv': 'result_cv.json',
}

# step ↔ result_final.json의 module_scores 키 매핑 (셋만 점수가 있다)
STEP_TO_MODULE_SCORE = {
    'step1_rule_based': 'rule_based',
    'step3_difficulty': 'difficulty',
    'step5_cv': 'cv',
}

# run_all.py의 TARGET_PAGE_UNAVAILABLE_REASONS와 같은 문구 (대상 페이지 대신 받은 문서의 종류)
UNAVAILABLE_REASONS = {
    'EMPTY': '페이지 본문을 확인하지 못했습니다',
    'HTTP_ERROR': '대상 페이지가 HTTP 오류를 반환했습니다',
    'BLOCKED': '보안 확인·자동 접근 차단 화면이 표시되었습니다',
}

EXIT_URL_MISMATCH = 2


# ── 파일 읽기·쓰기 ───────────────────────────────────────────────────────────

def read_csv_auto_encoding(path):
    """utf-8-sig / cp949 순으로 시도해서 (encoding, fieldnames, rows) 반환."""
    for enc in ('utf-8-sig', 'cp949'):
        try:
            with open(path, 'r', encoding=enc, newline='') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                fieldnames = reader.fieldnames or FIELDNAMES_DEFAULT
            return enc, fieldnames, rows
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError('알 수 없는 인코딩', b'', 0, 1, 'cp949/utf-8-sig 모두 실패')


def write_csv(path, encoding, fieldnames, rows):
    """임시 파일에 먼저 쓰고 성공하면 교체한다. encoding으로 인코딩이 안 되는
    문자가 들어오면(cp949에 없는 기호 등) 자동으로 utf-8-sig로 승격해서 다시 쓴다.
    원본 파일은 성공했을 때만 덮어써서, 실패해도 기존 내용이 깨지지 않는다.
    """
    tmp_path = path.with_suffix(path.suffix + '.tmp')

    def _try_write(enc):
        with open(tmp_path, 'w', encoding=enc, newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in rows:
                writer.writerow({k: r.get(k, '') for k in fieldnames})

    try:
        _try_write(encoding)
        used_encoding = encoding
    except UnicodeEncodeError:
        print(f"[안내] {encoding} 인코딩으로 저장할 수 없는 문자가 있어 utf-8-sig로 저장합니다.")
        _try_write('utf-8-sig')
        used_encoding = 'utf-8-sig'

    os.replace(tmp_path, path)
    return used_encoding


def load_json(path):
    """JSON 파일을 읽는다. 없거나 깨졌으면 None."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def slugify(url):
    s = re.sub(r'^https?://', '', url)
    s = re.sub(r'[^0-9a-zA-Z]+', '_', s).strip('_')
    return s[:60] or 'site'


def normalize_url(url):
    """URL 비교용: 스킴·호스트 대소문자와 경로 끝 '/', #조각을 무시한다."""
    parts = urlsplit((url or '').strip())
    return (parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip('/'), parts.query)


def archive_output(output_dir: Path, url: str):
    """output/ 안의 결과 파일들을 output/_archive/<슬러그>/로 복사."""
    archive_root = output_dir / '_archive'
    dest = archive_root / slugify(url)
    dest.mkdir(parents=True, exist_ok=True)

    copied = []
    for item in output_dir.iterdir():
        if item.name == '_archive' or item.name == '.ocr_cache':
            continue
        if item.is_file():
            shutil.copy2(item, dest / item.name)
            copied.append(item.name)
    return dest, copied


# ── 결과 읽기 ────────────────────────────────────────────────────────────────

def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def get_path(data, *keys):
    """중첩 dict에서 키를 따라 내려간다. 중간이 dict가 아니면 None."""
    for key in keys:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


def rule_has_score(rule):
    score = rule.get('score') if isinstance(rule, dict) else None
    if isinstance(score, dict):
        score = score.get('score')
    return is_number(score)


def difficulty_is_valid(module):
    return (isinstance(module, dict) and isinstance(module.get('results'), list)
            and is_number(get_path(module, 'meta', 'page_score')))


def suggestions_are_valid(module):
    return difficulty_is_valid(module) and isinstance(get_path(module, 'meta', 'suggestion_stats'), dict)


def unavailable_status(rule_api):
    """대상 페이지 대신 받은 문서의 종류(EMPTY·HTTP_ERROR·BLOCKED). 정상 페이지면 None."""
    status = get_path(rule_api, 'metadata', 'document_health', 'status')
    return status if status in UNAVAILABLE_REASONS else None


# 같은 사이트 안의 차단 관문 (2026-10-16, run_all.py의 SECURITY_GATE_URL_PATTERN과 같다).
# 예: plus.gov.kr → plus.gov.kr/mbuster/Mbuster_T. 호스트가 같아 위 비교로는 못 잡는다.
SECURITY_GATE_URL_PATTERN = re.compile(r'/mbuster(?:[/?#]|$)', re.IGNORECASE)


def _host(url):
    host = (urlparse(url).hostname or '').lower().rstrip('.') if isinstance(url, str) else ''
    return host[4:] if host.startswith('www.') else host


def redirected_elsewhere(requested_url, rule_api):
    """규칙 검사가 요청한 사이트가 아닌 곳에서 돌았으면 그 주소, 아니면 None (2026-10-14).

    run_all.py의 validate_target_navigation과 같은 기준이다(호스트가 다르거나 봇 관리 화면,
    또는 같은 사이트 안의 차단 관문 /mbuster/ — 2026-10-16 추가).
    이때 run.js는 점수까지 낸 정상 모양의 result_api.json을 남기지만, run_all.py는 종료 코드 2로
    멈추고 result_final.json을 만들지 않는다. 예: gov.kr → plus.gov.kr, 홍익대 → 봇 확인 화면.
    """
    analyzed = get_path(rule_api, 'metadata', 'url')
    if not isinstance(analyzed, str) or not analyzed or not requested_url:
        return None
    analyzed_host = _host(analyzed)
    if (analyzed.startswith('chrome-error://') or 'botmanager' in analyzed_host
            or SECURITY_GATE_URL_PATTERN.search(unquote(analyzed))
            or not analyzed_host or analyzed_host != _host(requested_url)):
        return analyzed
    return None


def result_url(output_dir: Path, final_data):
    """output/ 의 결과가 어느 URL의 것인지(요청한 URL). 알 수 없으면 None.

    result_final.json의 url은 run_all.py에 넘긴 주소 그대로다. 최종 결과가 없을 때는
    result_artifact.json의 requestedUrl을 쓴다. 차단·빈 문서가 남기는 result_api.json의
    metadata.url은 리다이렉트된 최종 주소(예: gov.kr → plus.gov.kr/mbuster)라 비교에 쓰지 않는다.
    """
    url = final_data.get('url') if isinstance(final_data, dict) else None
    return url or get_path(load_json(output_dir / 'result_artifact.json'), 'requestedUrl')


def check_steps(output_dir: Path, final_data, rule_api=None, requested_url=None):
    """각 step의 (판정, 경고 메시지)를 돌려준다. final_data는 result_final.json 내용 또는 None.

    result_final.json의 modules가 있으면 모듈 상태로, 없으면(옛 형식이거나 파이프라인이 일찍
    죽음) 산출물 파일이 있는지로 판정한다. 파일이 없는데 점수가 있거나 그 반대인 불일치는
    mismatch_notes로 돌려준다(result_final.json이 없을 때는 비교 대상이 없어 건너뜀).
    """
    modules = final_data.get('modules') if isinstance(final_data, dict) else None
    module_scores = get_path(final_data, 'score_breakdown', 'module_scores') or {}

    results = {}
    mismatch_notes = []
    for step, fname in STEP_FILES.items():
        file_exists = (output_dir / fname).exists()
        if isinstance(modules, dict):
            if step == 'step1_rule_based':
                ok = rule_has_score(modules.get('rule_based'))
            elif step == 'step2_text_extract':
                ok = file_exists
            elif step == 'step3_difficulty':
                ok = difficulty_is_valid(modules.get('text_difficulty'))
            elif step == 'step4_suggestion':
                ok = suggestions_are_valid(modules.get('text_suggestions'))
            else:
                ok = get_path(modules, 'cv_visual', 'status') == 'success'
        elif step == 'step1_rule_based':
            # 차단·빈 문서가 남기는 result_api.json은 점수가 없는 표식일 뿐이라 성공이 아니다.
            ok = (file_exists and rule_has_score(rule_api)
                  and not redirected_elsewhere(requested_url, rule_api))
        else:
            ok = file_exists
        results[step] = 'O' if ok else 'X'

        module_key = STEP_TO_MODULE_SCORE.get(step)
        if module_key is not None and isinstance(modules, dict):
            score_present = is_number(module_scores.get(module_key))
            if ok and not score_present:
                mismatch_notes.append(
                    f"[자동경고] {step}는 성공인데 module_scores.{module_key}가 없습니다(직접 확인 필요)")
            elif not ok and score_present:
                mismatch_notes.append(
                    f"[자동경고] {step}는 실패인데 module_scores.{module_key}에 값이 있습니다(직접 확인 필요)")
    return results, mismatch_notes


def data_quality_warnings(output_dir: Path, final_data, rule_api, requested_url=None):
    """점수가 나왔어도 믿기 어려운 경우를 문장 목록으로 돌려준다 (경고 칸에 ' | '로 이어 적음)."""
    warnings = []

    status = unavailable_status(rule_api)
    if status:
        warnings.append(f'대상 페이지 아님: {UNAVAILABLE_REASONS[status]} ({status}). 점수를 저장하지 않았습니다')
    elif final_data is None:
        moved_to = redirected_elsewhere(requested_url, rule_api)
        if moved_to:
            warnings.append(f'대상 페이지 아님: 요청한 사이트가 아닌 주소로 이동했습니다({moved_to}). '
                            '점수를 저장하지 않았습니다')

    modules = final_data.get('modules') if isinstance(final_data, dict) else None
    if isinstance(modules, dict):
        if not rule_has_score(modules.get('rule_based')) and not status:
            warnings.append('규칙 결과 없음: 규칙 기반 평가가 점수를 내지 못했습니다')

        difficulty = modules.get('text_difficulty')
        if difficulty_is_valid(difficulty):
            blocks = difficulty['results']
            if not blocks:
                warnings.append('텍스트 블록 0개: 분석할 글을 찾지 못했습니다(페이지가 비었거나 본문이 이미지일 수 있음)')
            else:
                scored = get_path(difficulty, 'meta', 'score_breakdown', 'scored_paragraphs')
                if not is_number(scored):   # 10/9 이전 결과에는 이 칸이 없다
                    scored = sum(1 for b in blocks if b.get('category') == 'paragraph'
                                 and b.get('difficulty_score') is not None)
                if scored == 0:
                    warnings.append('난이도 공식을 적용한 문단 0개: 난이도 감점이 0이라 만점에 가까운 점수는 '
                                    '"쉽다"가 아니라 "잴 문장이 없다"는 뜻입니다')

        if get_path(modules, 'cv_visual', 'status') == 'not_measured':
            reason = get_path(modules, 'cv_visual', 'reason') or 'NO_TEXT_DETECTED'
            warnings.append(f'CV 측정 불가: 잴 수 있는 글자가 없어 점수에서 빠졌습니다 ({reason})')

    legacy = final_data.get('data_quality_warnings') if isinstance(final_data, dict) else None
    if isinstance(legacy, list):   # 9월 형식의 결과(백업 폴더의 옛 결과)에 남아 있던 경고
        warnings.extend(str(item) for item in legacy)

    replay_source = get_path(load_json(output_dir / 'result.json'), 'meta', 'replaySource')
    if replay_source == 'INITIAL_RESPONSE_STATIC':
        warnings.append('정적 fallback: 봇 대기 화면을 감지해 최초 응답 HTML만 분석했습니다'
                        '(스크립트로 그려지는 내용은 빠짐)')
    return warnings


def auto_info_notes(rule_api, final_data):
    """notes에 남길 사실 정보: 레이어 팝업·제외 영역 개수."""
    rule = get_path(final_data, 'modules', 'rule_based') or rule_api
    notes = []
    popups = get_path(rule, 'metadata', 'popup_layers')
    if isinstance(popups, list) and popups:
        notes.append(f'[자동] 레이어 팝업 {len(popups)}개(점수 제외)')
    regions = get_path(rule, 'metadata', 'excluded_regions')
    if isinstance(regions, list) and regions:
        counts = {}
        for region in regions:
            reason = region.get('reason') if isinstance(region, dict) else None
            counts[reason or '기타'] = counts.get(reason or '기타', 0) + 1
        detail = ', '.join(f'{reason} {count}개' for reason, count in sorted(counts.items()))
        notes.append(f'[자동] 제외 영역 {len(regions)}개({detail}, 점수 제외)')
    return notes


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main(argv=None):
    ap = argparse.ArgumentParser(description='run_all.py 결과를 site_test_tracker.csv에 자동 기록')
    ap.add_argument('url', help='방금 테스트한 사이트 URL (트래커의 url 열과 정확히 일치해야 함)')
    ap.add_argument('--output-dir', default='output', help='run_all.py의 출력 폴더 (기본: output)')
    ap.add_argument('--tracker', default='site_test_tracker.csv', help='트래커 CSV 경로')
    ap.add_argument('--date', default=None, help='test_date에 넣을 날짜 (기본: 오늘)')
    ap.add_argument('--note', default=None, help='notes 열에 덧붙일 메모')
    ap.add_argument('--allow-new', action='store_true',
                    help='트래커에 없는 URL이면 에러 대신 새 행을 추가')
    ap.add_argument('--force', action='store_true',
                    help='output/의 결과 URL이 넘긴 URL과 달라도 기록')
    args = ap.parse_args(argv)

    tracker_path = Path(args.tracker)
    output_dir = Path(args.output_dir)

    if not tracker_path.exists():
        print(f"[오류] 트래커 파일을 찾을 수 없습니다: {tracker_path}")
        return 1

    encoding, fieldnames, rows = read_csv_auto_encoding(tracker_path)

    target = None
    for r in rows:
        if (r.get('url') or '').strip() == args.url.strip():
            target = r
            break

    if target is None:
        if not args.allow_new:
            print(f"[오류] 트래커에서 이 URL을 찾을 수 없습니다: {args.url}")
            print("       오타 확인, 또는 새 사이트를 추가하려면 --allow-new 옵션을 쓰세요.")
            existing = [r.get('url', '') for r in rows if r.get('url')]
            if existing:
                print("       트래커에 있는 URL 목록:")
                for u in existing:
                    print(f"         - {u}")
            return 1
        target = {k: '' for k in fieldnames}
        target['url'] = args.url
        rows.append(target)   # 저장은 아래 4단계에서만 한다(그 전에 멈추면 아무것도 안 바뀜)

    # ── 0) output/의 결과가 이 URL의 것인지 확인 (아무것도 바꾸기 전에) ──
    final_data = load_json(output_dir / 'result_final.json')
    if final_data is None and (output_dir / 'result_final.json').exists():
        print(f"[경고] {output_dir / 'result_final.json'}이 있지만 JSON 파싱에 실패했습니다.")
    rule_api = load_json(output_dir / 'result_api.json')
    found_url = result_url(output_dir, final_data)
    if found_url and normalize_url(found_url) != normalize_url(args.url) and not args.force:
        print(f"[중단] output/의 결과는 다른 URL의 것입니다. 아무것도 기록하지 않았습니다.")
        print(f"       넘긴 URL:   {args.url}")
        print(f"       결과의 URL: {found_url}")
        print("       이 URL로 run_all.py를 다시 돌렸는지 확인하세요. 그래도 기록하려면 --force를 쓰세요.")
        return EXIT_URL_MISMATCH
    # ── 1) 결과 아카이브 (다음 run_all.py 실행이 output/을 지우기 전에) ──
    archived_to = None
    archived_files = []
    if output_dir.exists():
        archived_to, archived_files = archive_output(output_dir, args.url)

    # ── 2) step 판정과 경고 ──
    step_results, mismatch_notes = check_steps(output_dir, final_data, rule_api, args.url)
    warnings = data_quality_warnings(output_dir, final_data, rule_api, args.url)

    # ── 3) 트래커 행 채우기 ──
    target['test_date'] = args.date or date.today().isoformat()
    for step, verdict in step_results.items():
        target[step] = verdict

    auto_notes = []
    if final_data is None:
        target['total_score'] = ''
        target['grade'] = ''
        status = unavailable_status(rule_api)
        moved_to = redirected_elsewhere(args.url, rule_api)
        if status:
            auto_notes.append(f'[자동] 분석 중단: {UNAVAILABLE_REASONS[status]} (document_health.status={status})')
        elif moved_to:
            auto_notes.append(f'[자동] 분석 중단: 다른 주소로 이동 ({moved_to})')
        else:
            auto_notes.append('[자동] result_final.json 없음(파이프라인이 끝까지 못 돌았을 가능성)')
    else:
        target['total_score'] = final_data.get('total_score', '')
        target['grade'] = final_data.get('grade', '')
    target['data_quality_warning'] = 'Y' if warnings else 'N'
    target['warning_detail'] = ' | '.join(warnings)

    auto_notes.extend(auto_info_notes(rule_api, final_data))
    auto_notes.extend(mismatch_notes)

    # 기존 notes에서 이전 실행이 남긴 [자동...] 태그 항목은 제거하고
    # 사람이 직접 적은 메모만 남긴 뒤, 이번 실행의 자동 메모를 새로 붙인다.
    existing_note = target.get('notes', '').strip()
    manual_parts = [p.strip() for p in existing_note.split(' / ') if p.strip() and not p.strip().startswith('[자동')]

    note_parts = list(manual_parts)
    if args.note:
        note_parts.append(args.note.strip())
    note_parts.extend(auto_notes)
    target['notes'] = ' / '.join(p for p in note_parts if p)

    # ── 4) 저장 ──
    backup_path = tracker_path.with_suffix(tracker_path.suffix + '.bak')
    shutil.copy2(tracker_path, backup_path)
    used_encoding = write_csv(tracker_path, encoding, fieldnames, rows)

    # ── 5) 요약 출력 ──
    print('=' * 55)
    print(f"기록 완료: {args.url}")
    print('=' * 55)
    for step, verdict in step_results.items():
        print(f"  {step:<20} {verdict}")
    print(f"  total_score          {target['total_score']}")
    print(f"  grade                {target['grade']}")
    print(f"  data_quality_warning {target['data_quality_warning']}")
    if target['warning_detail']:
        print(f"  warning_detail       {target['warning_detail']}")
    if mismatch_notes:
        print()
        print("  ⚠ 자동 감지된 불일치 (직접 확인 필요):")
        for m in mismatch_notes:
            print(f"    - {m}")
    if archived_to:
        print()
        print(f"  결과 백업: {archived_to}  ({len(archived_files)}개 파일)")
    print()
    print(f"  트래커 저장됨: {tracker_path}  (인코딩: {used_encoding}, 백업: {backup_path.name})")
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except PermissionError as e:
        # Windows에서 가장 흔한 원인: site_test_tracker.csv가 엑셀 등 다른
        # 프로그램에서 열려 있어 파일이 잠긴 경우. 이 시점에서는 아직
        # 원본 파일 교체 전이라(os.replace는 원자적) 기존 데이터는 안전하다.
        target = getattr(e, 'filename2', None) or getattr(e, 'filename', None) or '트래커 파일'
        print()
        print(f"[오류] 파일 접근이 거부됐습니다: {target}")
        print("       엑셀 등 다른 프로그램에서 이 파일을 열어놓지 않았는지 확인하고,")
        print("       열려 있다면 닫은 뒤 방금 실행한 명령을 다시 실행하세요.")
        print("       (계산된 결과는 안전하게 보존되어 있으니 재실행하면 됩니다)")
        sys.exit(1)
