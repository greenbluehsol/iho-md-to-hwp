# CLAUDE.md

## 프로젝트 개요

Obsidian .md 파일 → HWP 문서 자동 변환 도구. IHO 국제회의(HSSC) 의제 분석 문서용.

## 아키텍처

- `parser.py` → Obsidian .md 파싱 → `AgendaItem` 객체
- `hwpx_writer.py` → `template_source.hwpx` 기반으로 HWPX XML 편집 → COM으로 HWP 변환
- `main.py` → CLI 진입점 (single / batch 모드)

## 핵심 설계 결정

### HWPX XML 편집 방식
COM 자동화로 서식을 처음부터 생성하지 않고, 기존 HWP 파일을 HWPX(ZIP+XML)로 변환한 뒤 XML을 직접 편집하는 방식을 사용함. 서식은 100% 원본 유지.

### 템플릿 의존성
`template_source.hwpx`는 실제 회의 문서에서 추출한 서식 파일. `_find_agenda_starts()`가 배지 셀(col 0)에 `DD.DA` 패턴(예: `04.3A`)이 있는 표 단락을 탐지해 의제 경계를 식별함.

### 단락 스타일 매핑
- `paraPrIDRef="25"` → ○ 소제목 (2단계)
- `paraPrIDRef="26"` → - 글머리 (3단계)
- 섹션에 소제목(plain text)이 없으면 bullet도 ○ 스타일로 출력

### linesegarray 초기화
텍스트 교체 시 `<hp:linesegarray>`를 비워야 HWP가 레이아웃을 재계산함. 비우지 않으면 기존 위치 캐시로 인해 텍스트가 겹쳐 보임.

### 표 높이 자동 계산
긴 제목을 위해 한글(30자/줄)·영문(60자/줄) 기준으로 줄 수를 추정해 표 높이(hwpunit)를 동적으로 설정함.

## 파서 지원 형식

### HSSC 형식
`---` 구분선 있음. 의제번호가 제목 줄 맨 앞 또는 별도 줄에 위치.
발표자 패턴: `(Submitted by: ...)` 또는 `(Chair: ...)`

### 간소 형식
`---` 없음. 의제번호는 파일명에서 추출. 한글/영문 제목 자동 구분(영문 비율).

## 변경 시 주의사항

- `template_source.hwpx` 교체 시: `_find_agenda_starts()`가 인식하는 배지 셀 패턴(`DD.DA`) 유지 필수
- 새 섹션 추가 시: `parser.py`의 `SECTION_ORDER`와 `EXCLUDED_SECTIONS` 업데이트
- HWP COM API 속성명은 버전마다 다를 수 있음 (`HParameterSet` 하위 속성 확인 필요)
