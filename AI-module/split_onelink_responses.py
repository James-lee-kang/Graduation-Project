"""
split_onelink_responses.py — 한 링크 설문 응답 CSV를 묶음별 CSV 3개로 나눈다 (2026-10-16)

[왜 필요한가]
  링크 하나(카톡방·인스타 스토리)로 배포하려고 create_survey_form_onelink.gs로 폼 1개를 만들면,
  응답자는 태어난 달에 따라 묶음 1·2·3 중 한 곳의 글 12개 + 응답 확인 1개에만 답한다.
  analyze_survey2.py는 폼 3개의 응답 CSV를 받도록 응답 전에 고정해 두었으므로, 그 파일은 고치지 않고
  이 스크립트가 한 링크 응답을 "폼 3개를 따로 받은 것과 같은 모양"으로 바꿔 준다.
    - 응답자마다 태어난 달 답 → 묶음 번호
    - 그 묶음의 문항("묶음 K · 글 N. …")만 남기고 제목 앞의 "묶음 K · "를 떼어 "글 N. …"으로
    - 파일 이름에 "설문 K_3"을 넣어 analyze_survey2.py가 폼 번호를 알아보게
  다른 묶음 칸에 값이 있으면(뒤로 가서 달을 바꾼 경우) 그 값은 쓰지 않는다.
  10/17: 첫 페이지 동의 문항에 "동의합니다"가 아닌 응답(동의하지 않아 바로 제출된 빈 응답)은 뺀다.

[실행] (프로젝트 루트에서)
  python split_onelink_responses.py "<구글폼에서 받은 응답.csv>"
  → output/survey2/onelink_split/ 에 묶음별 CSV 3개, 마지막에 analyze_survey2.py 실행 명령을 보여 준다.

  종료 코드: 0 정상, 1 파일 없음·읽기 실패, 2 모양이 다름(태어난 달 문항이나 "묶음 K ·" 문항이 없음)
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

from select_survey_texts import ONELINK_CONSENT_YES, ONELINK_GROUP_CHOICES, ONELINK_GROUP_QUESTION

PROJECT_ROOT = Path(__file__).parent.resolve()
DEFAULT_OUT = PROJECT_ROOT / "output" / "survey2" / "onelink_split"
_GROUP_TITLE = re.compile(r"^\s*묶음\s*(\d+)\s*·\s*")
FREQUENCY_KEY = "이용하는 빈도"   # analyze_survey2.py도 이 말이 들어간 열을 이용 빈도로 읽는다


def read_rows(path: Path) -> tuple[list[str], list[list[str]]]:
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


def split(header: list[str], rows: list[list[str]]) -> tuple[dict[int, tuple[list[str], list[list[str]]]], dict]:
    """→ ({묶음: (헤더, 행들)}, 통계). 모양이 다르면 ValueError."""
    n_groups = len(ONELINK_GROUP_CHOICES)
    group_col = next((i for i, t in enumerate(header) if t.strip() == ONELINK_GROUP_QUESTION.strip()), None)
    if group_col is None:
        group_col = next((i for i, t in enumerate(header) if "태어난 달" in t), None)
    if group_col is None:
        raise ValueError("'태어난 달' 문항 열이 없습니다. 한 링크 폼(create_survey_form_onelink.gs)의 응답이 맞나요?")
    freq_col = next((i for i, t in enumerate(header) if FREQUENCY_KEY in t), None)
    consent_col = next((i for i, t in enumerate(header) if "동의하십니까" in t), None)   # 10/17 동의 문항

    columns: dict[int, list[tuple[int, str]]] = {g: [] for g in range(1, n_groups + 1)}
    for index, title in enumerate(header):
        found = _GROUP_TITLE.match(title)
        if found:
            group = int(found.group(1))
            if group not in columns:
                raise ValueError(f"'{title}': 묶음 번호 {group}이 1~{n_groups} 밖입니다.")
            columns[group].append((index, title[found.end():]))
    empty = [g for g, cols in columns.items() if not cols]
    if empty:
        raise ValueError(f"묶음 {empty}의 문항('묶음 K · 글 N.')이 없습니다.")

    out: dict[int, tuple[list[str], list[list[str]]]] = {}
    for group in columns:
        new_header = [header[0]]
        if freq_col is not None:
            new_header.append(header[freq_col])
        new_header += [title for _, title in columns[group]]
        out[group] = (new_header, [])

    stats = {"rows": 0, "not_consented": 0, "no_group": 0, "unknown_group": 0, "other_group_values_ignored": 0,
             "per_group": {g: 0 for g in columns}}
    for values in rows:
        if not any(cell.strip() for cell in values):
            continue
        stats["rows"] += 1
        cell = lambda i: values[i].strip() if i < len(values) else ""   # noqa: E731
        if consent_col is not None and cell(consent_col) != ONELINK_CONSENT_YES:
            stats["not_consented"] += 1   # 동의하지 않으면 바로 제출되어 빈 응답만 남는다
            continue
        answer = cell(group_col)
        if not answer:
            stats["no_group"] += 1
            continue
        if answer not in ONELINK_GROUP_CHOICES:
            stats["unknown_group"] += 1
            continue
        group = ONELINK_GROUP_CHOICES.index(answer) + 1
        if any(cell(i) for other, cols in columns.items() if other != group for i, _ in cols):
            stats["other_group_values_ignored"] += 1
        new_row = [cell(0)]
        if freq_col is not None:
            new_row.append(cell(freq_col))
        new_row += [cell(i) for i, _ in columns[group]]
        out[group][1].append(new_row)
        stats["per_group"][group] += 1
    return out, stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="한 링크 설문 응답 CSV → 묶음별 CSV")
    parser.add_argument("responses", help="구글폼에서 받은 한 링크 설문 응답 CSV")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="결과 폴더 (기본 output/survey2/onelink_split)")
    args = parser.parse_args(argv)

    path = Path(args.responses)
    try:
        header, rows = read_rows(path)
    except (OSError, ValueError) as error:
        print(f"[오류] {error}")
        return 1
    try:
        groups, stats = split(header, rows)
    except ValueError as error:
        print(f"[오류] {error}")
        return 2

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for group, (new_header, new_rows) in groups.items():
        target = out / f"[Uniaccess 2차 설문 {group}_{len(groups)}] 한 링크 응답.csv"
        with target.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(new_header)
            writer.writerows(new_rows)
        written.append(target)

    print(f"응답 {stats['rows']}개 → " + ", ".join(f"묶음 {g}: {n}명" for g, n in stats["per_group"].items()))
    if stats["not_consented"]:
        print(f"  [제외] 참여에 동의하지 않은 응답 {stats['not_consented']}개")
    if stats["no_group"] or stats["unknown_group"]:
        print(f"  [제외] 태어난 달 답 없음 {stats['no_group']}개, 알 수 없는 답 {stats['unknown_group']}개")
    if stats["other_group_values_ignored"]:
        print(f"  [참고] 다른 묶음 칸에 값이 있던 응답 {stats['other_group_values_ignored']}개 — 고른 묶음 값만 썼습니다.")
    print("\n다음 명령으로 분석하세요:")
    print("  python analyze_survey2.py --responses " + " ".join(f'"{p}"' for p in written))
    return 0


if __name__ == "__main__":
    sys.exit(main())
