"""
parser.py
Obsidian .md 파일을 파싱하여 구조화된 데이터로 변환
"""
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


EXCLUDED_SECTIONS = {"검토의견", "대응방안"}

SECTION_ORDER = [
    "의제 개요",
    "논의 경과 및 현황",
    "의제 내용",
    "요청사항",
    "부록",
    "원문 자료(참고문헌)",
]


@dataclass
class AgendaItem:
    file_path: Path
    session_line: str          # e.g. "HSSC-18 – PLENARY SESSION 2"
    session_sub: str           # e.g. "5. Reports by HSSC Working Groups and Project Teams"
    agenda_number: str         # e.g. "HSSC18-05.1A"
    title_ko: str              # Korean title
    title_en: str              # English title
    presenter: str             # Submitted by: ...
    sections: dict             # section name -> list of content blocks


def _split_title_line(line: str) -> tuple[str, str, str, str]:
    """
    'HSSC18-05.1A S-100 실무그룹(S-100WG) 보고서 Report of the S-100 Working Group (Submitted by: Julia Powell)'
    -> (agenda_number, title_ko, title_en, presenter)
    """
    # Extract presenter - "(Submitted by: ...)" 또는 "(Chair: ...)" 형태
    presenter = ""
    submitted_match = re.search(r'\((Submitted by|Chair)[:\s]+([^)]+)\)', line, re.IGNORECASE)
    if submitted_match:
        presenter = submitted_match.group(2).strip()
        line = line[:submitted_match.start()].strip()

    # Extract agenda number (first token, alphanumeric with dashes and dots)
    parts = line.split(None, 1)
    if not parts:
        return ("", "", "", presenter)

    agenda_number = parts[0]
    rest = parts[1] if len(parts) > 1 else ""

    # Split Korean and English portions
    # English typically starts with a capital letter sequence that looks like an English sentence
    # Strategy: find the last contiguous block of hangul-mixed text, then the rest is English
    # More robust: find position where Korean chars end and English begins
    # We look for a transition from Korean characters to English sentence

    title_ko = ""
    title_en = ""

    if rest:
        # Find where English title starts: look for pattern of Korean text followed by space + English capital
        # Korean unicode range: \uAC00-\uD7A3, \u3130-\u318F, \u1100-\u11FF
        # Find last Korean character position
        last_ko_pos = -1
        for i, ch in enumerate(rest):
            if '\uAC00' <= ch <= '\uD7A3' or '\u3130' <= ch <= '\u318F':
                last_ko_pos = i

        if last_ko_pos == -1:
            # No Korean characters, all English
            title_en = rest.strip()
        else:
            # Check if there's English content after the Korean part
            after_ko = rest[last_ko_pos + 1:].strip()
            if after_ko and re.match(r'[A-Z]', after_ko):
                title_ko = rest[:last_ko_pos + 1].strip()
                title_en = after_ko
            else:
                title_ko = rest.strip()

    return (agenda_number, title_ko, title_en, presenter)


def _parse_section_content(lines: list[str]) -> list[dict]:
    """
    섹션 내용을 블록 리스트로 변환.
    반환: [{"type": "bullet"|"subheading", "text": str}, ...]
    - "- text"  → bullet
    - "○ text"  → subheading
    - plain text → subheading
    """
    blocks = []
    for line in lines:
        stripped = line.rstrip()
        if not stripped:
            continue
        if stripped.startswith("- "):
            blocks.append({"type": "bullet", "text": stripped[2:].strip()})
        elif stripped.startswith("○ "):
            blocks.append({"type": "subheading", "text": stripped[2:].strip()})
        else:
            blocks.append({"type": "subheading", "text": stripped.strip()})
    return blocks


def parse_md_file(file_path: Path) -> Optional[AgendaItem]:
    """단일 .md 파일 파싱 → AgendaItem

    두 가지 형식 지원:
    1. HSSC 형식: session line / sub line / --- / 제목행(의제번호 포함) / **□ 섹션**
    2. 간소 형식: 한글제목 / 영문제목 / (제출자...) / **□ 섹션**
    """
    text = file_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    n = len(lines)

    session_line = ""
    session_sub = ""
    agenda_number = ""
    title_ko = ""
    title_en = ""
    presenter = ""
    sections = {}

    section_pattern = re.compile(r'^\*\*□\s*(.+?)\*\*\s*$')

    # 첫 번째 **□ 섹션** 위치 찾기
    first_section_idx = next(
        (i for i, l in enumerate(lines) if section_pattern.match(l.strip())),
        n
    )

    # 헤더 영역 파싱 (첫 섹션 전까지)
    header_lines = [l.strip() for l in lines[:first_section_idx] if l.strip()]

    # --- 구분선 있는 HSSC 형식인지 확인
    has_separator = any(l == '---' for l in header_lines)

    if has_separator:
        # HSSC 형식: session / sub / --- / [**해원...**] / 제목행(들)
        sep_pos = next(i for i, l in enumerate(header_lines) if l == '---')
        pre_sep = header_lines[:sep_pos]
        post_sep = [l for l in header_lines[sep_pos+1:] if not l.startswith('**해원')]

        if len(pre_sep) >= 1:
            session_line = pre_sep[0]
        if len(pre_sep) >= 2:
            session_sub = pre_sep[1]

        if post_sep:
            first = post_sep[0]
            # 의제번호만 있는 줄인지 확인 (제목 없음)
            parsed_num, parsed_ko, parsed_en, parsed_pr = _split_title_line(first)
            if parsed_num and not parsed_ko and len(post_sep) > 1:
                # 다음 줄들에서 제목/발표자 읽기
                agenda_number = parsed_num
                for line in post_sep[1:]:
                    if line.startswith('(Submitted by') or line.startswith('(submitted by'):
                        m = re.search(r'\(Submitted by[:\s]+(.+?)\)?\s*$', line, re.IGNORECASE)
                        presenter = m.group(1).strip() if m else line.strip('() ')
                    elif not title_ko:
                        en_ratio = sum(1 for c in line if c.isascii() and c.isalpha()) / max(len(line), 1)
                        if en_ratio < 0.5:
                            title_ko = line
                        else:
                            title_en = line
                    elif not title_en:
                        en_ratio = sum(1 for c in line if c.isascii() and c.isalpha()) / max(len(line), 1)
                        if en_ratio >= 0.4:
                            title_en = line
            else:
                agenda_number, title_ko, title_en, presenter = parsed_num, parsed_ko, parsed_en, parsed_pr
    else:
        # 간소 형식: 한글제목 / 영문제목 / (제출자...)
        # 의제번호는 파일명에서 추출
        agenda_number = file_path.stem  # e.g. "PRO 2.1"

        non_empty = header_lines
        for line in non_empty:
            # 영문 제목 (대문자 시작, 영문 비율 높음)
            en_ratio = sum(1 for c in line if c.isascii() and c.isalpha()) / max(len(line), 1)
            # 발표자 줄 (제출자 또는 Submitted by)
            if '제출자' in line or 'Submitted by' in line.lower():
                # "(제출자 - XXX)" 또는 "(Submitted by: XXX)" 형태
                m = re.search(r'[제출자Submitted by:\s-]+(.+?)\)?$', line, re.IGNORECASE)
                if m:
                    presenter = m.group(1).strip().rstrip(')')
                else:
                    presenter = line.strip('() ')
            elif not title_ko and en_ratio < 0.5:
                title_ko = line
            elif not title_en and en_ratio >= 0.5:
                title_en = line

    # 섹션 파싱
    i = first_section_idx
    current_section = None
    current_lines = []

    def flush_section():
        if current_section and current_section not in EXCLUDED_SECTIONS:
            sections[current_section] = _parse_section_content(current_lines)

    while i < n:
        line = lines[i]
        match = section_pattern.match(line.strip())
        if match:
            flush_section()
            current_section = match.group(1).strip()
            current_lines = []
        elif current_section is not None:
            if current_section not in EXCLUDED_SECTIONS:
                current_lines.append(line)
        i += 1

    flush_section()

    return AgendaItem(
        file_path=file_path,
        session_line=session_line,
        session_sub=session_sub,
        agenda_number=agenda_number,
        title_ko=title_ko,
        title_en=title_en,
        presenter=presenter,
        sections=sections,
    )


def parse_folder(folder_path: Path) -> list[AgendaItem]:
    """폴더 내 모든 .md 파일 파싱, 파일명 기준 정렬"""
    md_files = sorted(folder_path.glob("*.md"))
    items = []
    for f in md_files:
        item = parse_md_file(f)
        if item:
            items.append(item)
    return items


if __name__ == "__main__":
    # Quick test
    test_file = Path(r"C:\sol\Obsidian_SOL\2. Work\항해용 간해물\HSSC 18\HSSC18-05.1A.md")
    if test_file.exists():
        item = parse_md_file(test_file)
        print(f"agenda_number : {item.agenda_number}")
        print(f"title_ko      : {item.title_ko}")
        print(f"title_en      : {item.title_en}")
        print(f"presenter     : {item.presenter}")
        print(f"session_line  : {item.session_line}")
        print(f"sections      : {list(item.sections.keys())}")
        for sec, blocks in item.sections.items():
            print(f"\n  [{sec}]")
            for b in blocks[:3]:
                print(f"    ({b['type']}) {b['text'][:60]}")
