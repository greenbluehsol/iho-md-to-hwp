"""
hwpx_writer.py
기존 HWPX 파일을 템플릿으로 사용하여 Obsidian .md 내용으로 채운 새 HWPX/HWP 생성
"""
import zipfile
import shutil
import re
import copy
import os
import os
from pathlib import Path
from xml.etree import ElementTree as ET

from parser import AgendaItem, SECTION_ORDER

HP  = 'http://www.hancom.co.kr/hwpml/2011/paragraph'
HP10 = 'http://www.hancom.co.kr/hwpml/2016/paragraph'

ET.register_namespace('hs', 'http://www.hancom.co.kr/hwpml/2011/section')
ET.register_namespace('hp', HP)
ET.register_namespace('hp10', HP10)
ET.register_namespace('ha', 'http://www.hancom.co.kr/hwpml/2011/app')
ET.register_namespace('hc', 'http://www.hancom.co.kr/hwpml/2011/core')
ET.register_namespace('hh', 'http://www.hancom.co.kr/hwpml/2011/head')
ET.register_namespace('hhs', 'http://www.hancom.co.kr/hwpml/2011/history')
ET.register_namespace('hm', 'http://www.hancom.co.kr/hwpml/2011/master-page')
ET.register_namespace('hpf', 'http://www.hancom.co.kr/schema/2011/hpf')
ET.register_namespace('dc', 'http://purl.org/dc/elements/1.1/')
ET.register_namespace('opf', 'http://www.idpf.org/2007/opf/')
ET.register_namespace('ooxmlchart', 'http://www.hancom.co.kr/hwpml/2016/ooxmlchart')
ET.register_namespace('epub', 'http://www.idpf.org/2007/ops')
ET.register_namespace('config', 'urn:oasis:names:tc:opendocument:xmlns:config:1.0')

TEMPLATE_PATH = Path(__file__).parent / "template_source.hwpx"


def _tag(name):
    return f'{{{HP}}}{name}'


def _get_text(elem):
    return ''.join(t.text or '' for t in elem.iter(_tag('t')))


def _set_text(elem, text):
    """첫 번째 <hp:t> 노드의 텍스트를 교체하고 linesegarray 초기화"""
    for t in elem.iter(_tag('t')):
        t.text = text
        break
    # linesegarray 초기화 (캐시된 레이아웃 위치 제거 → HWP가 재계산)
    lsa = elem.find(_tag('linesegarray'))
    if lsa is not None:
        for ls in lsa.findall(_tag('lineseg')):
            lsa.remove(ls)


def _clear_t_text(elem):
    for t in elem.iter(_tag('t')):
        t.text = ''


def _find_agenda_starts(children):
    """
    top-level <hp:p> 리스트에서 각 의제 항목의 시작 인덱스 반환.
    배지 셀(col 0)에 의제번호 패턴(예: 04.3A, 05.1A)이 있는 표 단락으로 식별.
    """
    import re
    agenda_pat = re.compile(r'^\d{2}\.\d+[A-Z]$')
    starts = []
    tbl_tag = _tag('tbl')
    for i, p in enumerate(children):
        for run in p.findall(_tag('run')):
            tbl = run.find(tbl_tag)
            if tbl is None:
                continue
            # 첫 번째 셀 텍스트 확인
            badge_paras = _get_cell_paras(tbl, 0)
            if badge_paras:
                badge_txt = _get_text(badge_paras[0]).strip()
                if agenda_pat.match(badge_txt):
                    starts.append(i)
                    break
    return starts


def _extract_agenda_block(children, start_idx, next_start_idx):
    """시작~다음 시작 전까지의 단락 리스트 반환"""
    return children[start_idx:next_start_idx]


def _get_header_table(para):
    """header table paragraph에서 <hp:tbl> 반환"""
    for run in para.findall(_tag('run')):
        tbl = run.find(_tag('tbl'))
        if tbl is not None:
            return tbl
    return None


def _get_cell_paras(tbl, col_idx):
    """표에서 특정 열(col_idx)의 subList 내 단락들 반환"""
    tr = tbl.find(_tag('tr'))
    if tr is None:
        return []
    tcs = tr.findall(_tag('tc'))
    if col_idx >= len(tcs):
        return []
    sub = tcs[col_idx].find(_tag('subList'))
    if sub is None:
        return []
    return sub.findall(_tag('p'))


def _clone_para(template_p):
    """단락 XML deep copy"""
    return copy.deepcopy(template_p)


def _make_content_para(template_p, text):
    """기존 단락을 복제하고 텍스트 교체"""
    new_p = copy.deepcopy(template_p)
    # linesegarray는 HWP가 재계산하므로 초기화
    lsa = new_p.find(_tag('linesegarray'))
    if lsa is not None:
        for ls in lsa.findall(_tag('lineseg')):
            lsa.remove(ls)
    for t in new_p.iter(_tag('t')):
        t.text = text
        return new_p
    # <hp:t>가 없으면 run에 추가
    run = new_p.find(_tag('run'))
    if run is not None:
        t_elem = ET.SubElement(run, _tag('t'))
        t_elem.text = text
    return new_p


def _find_section_range(block_paras, section_marker):
    """
    block_paras(단락 리스트)에서 section_marker 텍스트를 포함하는 단락 인덱스,
    그리고 이후 다음 □ 섹션 또는 끝까지의 내용 범위 반환.
    Returns: (heading_idx, content_start_idx, content_end_idx) or None
    """
    heading_idx = None
    for i, p in enumerate(block_paras):
        txt = _get_text(p)
        if '□' in txt and section_marker.replace(' ', '') in txt.replace(' ', ''):
            heading_idx = i
            break
    if heading_idx is None:
        return None

    content_start = heading_idx + 1
    content_end = len(block_paras)

    # 다음 □ 섹션 또는 빈 단락 연속까지
    for i in range(content_start, len(block_paras)):
        txt = _get_text(block_paras[i])
        if '□' in txt:
            content_end = i
            break

    return (heading_idx, content_start, content_end)


def _replace_section_content(block_paras, section_marker, new_blocks,
                              template_subheading_para, template_bullet_para):
    """
    block_paras 내 섹션 내용을 new_blocks로 교체.
    new_blocks: [{"type": "bullet"|"subheading", "text": str}, ...]
    template_subheading_para: ○ 소제목용 복제 템플릿 (paraPrIDRef=25)
    template_bullet_para: - 글머리용 복제 템플릿 (paraPrIDRef=26)
    Returns: 새로운 block_paras 리스트
    """
    info = _find_section_range(block_paras, section_marker)
    if info is None:
        return block_paras

    heading_idx, content_start, content_end = info

    # 섹션에 소제목(plain text)이 있는지 확인
    has_subheading = any(b['type'] == 'subheading' for b in new_blocks)

    # 새 내용 단락 생성
    new_content_paras = []
    for block in new_blocks:
        if has_subheading:
            # 소제목 있는 섹션: subheading=○, bullet=-
            tpl = template_bullet_para if block['type'] == 'bullet' else template_subheading_para
        else:
            # 소제목 없는 섹션: bullet도 ○ 스타일로
            tpl = template_subheading_para
        new_content_paras.append(_make_content_para(tpl, block['text']))

    # 기존 내용을 새 내용으로 교체
    result = (
        block_paras[:content_start] +
        new_content_paras +
        block_paras[content_end:]
    )
    return result


def _build_agenda_block(template_block, item: AgendaItem):
    """
    template_block(단락 리스트)을 기반으로 새 의제 항목 단락 리스트 생성.
    """
    block = copy.deepcopy(template_block)

    # ── 헤더 표 업데이트 ──────────────────────────────────────────
    header_para = block[0]
    tbl = _get_header_table(header_para)

    # 제목 길이 기반 표 높이 계산 (HWP 단위: 1/283.5mm ≈ 1hwpunit)
    # 제목 열 너비 ≈ 150mm → 한글 30자/줄, 영문 60자/줄
    if tbl is not None:
        LINE_H = 1500  # 줄당 높이 (hwpunit)
        ko_lines = max(1, (len(item.title_ko) + 29) // 30)
        en_lines = max(1, (len(item.title_en) + 59) // 60) if item.title_en else 0
        pr_lines = 1 if item.presenter else 0
        needed = (ko_lines + en_lines + pr_lines) * LINE_H + 1200
        new_h = str(max(6071, needed))

        sz = tbl.find(_tag('sz'))
        if sz is not None:
            sz.set('height', new_h)
        for tc in tbl.iter(_tag('tc')):
            cell_sz = tc.find(_tag('cellSz'))
            if cell_sz is not None:
                cell_sz.set('height', new_h)
    if tbl:
        # col 0: 배지 (의제번호 - "HSSC18-" 접두어 제거, "05.1A" 형태만)
        badge_paras = _get_cell_paras(tbl, 0)
        if badge_paras:
            badge_num = re.sub(r'^HSSC\d+-', '', item.agenda_number)
            _set_text(badge_paras[0], badge_num)

        # col 2: 제목 영역
        title_paras = _get_cell_paras(tbl, 2)
        if len(title_paras) >= 1:
            _set_text(title_paras[0], item.title_ko)
        if len(title_paras) >= 2:
            _set_text(title_paras[1], item.title_en)
        if len(title_paras) >= 3:
            presenter_text = f'({item.presenter})' if item.presenter else ''
            _set_text(title_paras[2], presenter_text)

    # ── 세션 정보 단락 업데이트 (index 1) ────────────────────────
    if len(block) > 1:
        session_para = block[1]
        tbl2 = _get_header_table(session_para)
        if tbl2:
            # 세션 표 내용 업데이트
            for col_i in range(3):
                sub_paras = _get_cell_paras(tbl2, col_i)
                for sp in sub_paras:
                    txt = _get_text(sp)
                    if 'PLENARY SESSION' in txt or 'HSSC-18' in txt:
                        _set_text(sp, item.session_line)
                    elif txt.strip().isdigit() or (len(txt.strip()) <= 3 and '.' in txt):
                        pass  # session number, keep
                    elif txt.strip() and 'SESSION' not in txt and 'HSSC' not in txt:
                        _set_text(sp, item.session_sub)

    # ── 콘텐츠 단락 템플릿 찾기 ─────────────────────────────────
    # paraPrIDRef="25" → ○ 소제목, paraPrIDRef="26" → - 글머리
    template_subheading = None
    template_bullet = None
    for p in block:
        pr = p.get('paraPrIDRef', '')
        txt = _get_text(p).strip()
        if not txt or '□' in txt:
            continue
        if pr == '25' and template_subheading is None:
            template_subheading = p
        elif pr == '26' and template_bullet is None:
            template_bullet = p
        if template_subheading and template_bullet:
            break

    # fallback: 둘 다 같은 것 사용
    if template_subheading is None and template_bullet is None:
        for p in block:
            txt = _get_text(p).strip()
            if txt and '□' not in txt and len(txt) > 5:
                template_subheading = p
                break
    if template_subheading is None:
        return block
    if template_bullet is None:
        template_bullet = template_subheading

    # ── SECTION_ORDER 순서대로 내용 교체 ────────────────────────
    section_label_map = {
        '의제 개요': '의제 개요',
        '논의 경과 및 현황': '논의 경과',
        '의제 내용': '의제 내용',
        '요청사항': '요청',
        '부록': '부록',
        '원문 자료(참고문헌)': '원문 자료',
    }

    for sec_name in SECTION_ORDER:
        matched_key = None
        for key in item.sections:
            if sec_name.replace(' ', '') in key.replace(' ', '') or key.replace(' ', '') in sec_name.replace(' ', ''):
                matched_key = key
                break
        if matched_key is None:
            continue

        blocks_data = item.sections[matched_key]
        marker = section_label_map.get(sec_name, sec_name)
        block = _replace_section_content(block, marker, blocks_data,
                                          template_subheading, template_bullet)

    return block


def generate_single(item: AgendaItem, output_path: Path, template_path: Path = None):
    """단일 의제 → HWP 파일 생성 (HWPX 경유)"""
    if template_path is None:
        template_path = TEMPLATE_PATH

    hwpx_path = output_path.with_suffix('.hwpx')
    _generate_hwpx([item], hwpx_path, template_path)
    _convert_hwpx_to_hwp(hwpx_path, output_path)


def generate_combined(items: list[AgendaItem], output_path: Path, template_path: Path = None):
    """여러 의제 → 단일 HWP 파일 생성"""
    if template_path is None:
        template_path = TEMPLATE_PATH

    hwpx_path = output_path.with_suffix('.hwpx')
    _generate_hwpx(items, hwpx_path, template_path)
    _convert_hwpx_to_hwp(hwpx_path, output_path)


def _generate_hwpx(items: list[AgendaItem], output_hwpx: Path, template_path: Path):
    """HWPX 파일 생성"""
    # 템플릿 복사
    shutil.copy2(template_path, output_hwpx)

    with zipfile.ZipFile(template_path, 'r') as z:
        xml_bytes = z.read('Contents/section0.xml')

    root = ET.fromstring(xml_bytes)
    children = list(root)

    # 의제 항목 경계 찾기
    starts = _find_agenda_starts(children)
    if not starts:
        print('[오류] 템플릿에서 의제 항목을 찾을 수 없습니다.')
        return

    # 문서 설정(secPr)이 담긴 첫 단락만 유지, 나머지 소개 페이지 제거
    # secPr은 항상 children[0]에 위치
    header_children = children[:1]

    # 첫 번째 의제를 템플릿으로 사용
    template_end = starts[1] if len(starts) > 1 else len(children)
    template_block = children[starts[0]:template_end]

    # 새 섹션 구성
    new_children = list(header_children)

    for idx, item in enumerate(items):
        new_block = _build_agenda_block(template_block, item)
        # 첫 번째 의제 이후 pageBreak="1" 설정은 이미 template에 있음
        new_children.extend(new_block)

    # root의 기존 자식 교체
    for child in list(root):
        root.remove(child)
    for child in new_children:
        root.append(child)

    # 직렬화
    new_xml = ET.tostring(root, encoding='unicode', xml_declaration=False)
    new_xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>' + new_xml

    # HWPX에 쓰기
    _repack_hwpx(template_path, output_hwpx, {'Contents/section0.xml': new_xml.encode('utf-8')})
    print(f'HWPX 생성: {output_hwpx}')


def _repack_hwpx(src_hwpx: Path, dst_hwpx: Path, replacements: dict):
    """src_hwpx를 기반으로 일부 파일을 교체하여 dst_hwpx 생성"""
    import tempfile
    tmp_path = Path(str(dst_hwpx) + '.tmp')

    with zipfile.ZipFile(src_hwpx, 'r') as zin:
        with zipfile.ZipFile(tmp_path, 'w', zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename in replacements:
                    zout.writestr(item, replacements[item.filename])
                else:
                    zout.writestr(item, zin.read(item.filename))

    if dst_hwpx.exists():
        dst_hwpx.unlink()
    tmp_path.rename(dst_hwpx)


def _convert_hwpx_to_hwp(hwpx_path: Path, hwp_path: Path):
    """HWP COM으로 HWPX → HWP 변환"""
    try:
        import win32com.client as win32
        hwp = win32.gencache.EnsureDispatch("HWPFrame.HwpObject")
        hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")

        hwp.HAction.GetDefault("FileOpen", hwp.HParameterSet.HFileOpen.HSet)
        hwp.HParameterSet.HFileOpen.OpenFileName = str(hwpx_path.resolve())
        hwp.HParameterSet.HFileOpen.OpenFormat = "HWPX"
        hwp.HAction.Execute("FileOpen", hwp.HParameterSet.HFileOpen.HSet)

        hwp.HAction.GetDefault("FileSaveAs", hwp.HParameterSet.HFileSaveAs.HSet)
        hwp.HParameterSet.HFileSaveAs.SaveFileName = str(hwp_path.resolve())
        hwp.HParameterSet.HFileSaveAs.SaveFormat = "HWP"
        hwp.HParameterSet.HFileSaveAs.SaveOverWrite = 1
        hwp.HAction.Execute("FileSaveAs", hwp.HParameterSet.HFileSaveAs.HSet)
        hwp.Quit()
        # 중간 파일 삭제
        if hwpx_path.exists():
            hwpx_path.unlink()
        print(f'저장 완료: {hwp_path}')
    except Exception as e:
        print(f'[경고] HWP 변환 실패: {e}')
        print(f'HWPX 파일 사용 가능: {hwpx_path}')
