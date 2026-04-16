# IHO 의제 분석 문서 자동 생성기

Obsidian에 작성한 국제회의 의제 분석 마크다운 파일을 HWP 문서로 자동 변환하는 도구입니다.

## 개요

**현재 워크플로우**
```
국제회의 문서 다운로드 → NotebookLM 의제 분석 → Obsidian 작성 → [이 도구] → HWP 자동 생성
```

수동 복붙 없이 Obsidian .md 파일에서 지정된 HWP 서식 문서를 자동으로 생성합니다.

## 설치 요구사항

- Python 3.x
- 한컴 한글(HWP) 설치
- `pywin32` 패키지

```bash
pip install pywin32
```

## 사용 방법

### 단일 파일 변환
```bash
python main.py single "파일경로.md"
python main.py single "파일경로.md" -o "출력경로.hwp"
```

### 폴더 전체 변환 (개별 HWP)
```bash
python main.py batch "폴더경로"
```

### 폴더 전체 변환 (통합 HWP)
```bash
python main.py batch "폴더경로" --combined
python main.py batch "폴더경로" --combined -o "출력파일명.hwp"
```

## Obsidian 파일 형식

두 가지 형식을 지원합니다.

### HSSC 형식 (세션 정보 포함)
```
HSSC-18 – PLENARY SESSION 2
5. Reports by HSSC Working Groups and Project Teams

---

HSSC18-05.1A S-100 실무그룹(S-100WG) 보고서 Report of the S-100 Working Group (Submitted by: Julia Powell)

**□ 의제 개요**
- 내용...

**□ 논의 경과 및 현황**
- 내용...

**□ 의제 내용**
○ 소제목
- 세부 내용...

**□ 요청사항**
- 내용...

**□ 부록(Annex)**
- 내용...

**□ 원문 자료(참고문헌)**
- 파일명.pdf

**□ 검토의견**

**□ 대응방안**
```

### 간소 형식 (제목만)
```
한글 제목

ENGLISH TITLE

(제출자 - 이름)

**□ 의제 개요**
- 내용...
```

### 마크다운 계층 구조

| 마크다운 | HWP 출력 |
|---------|---------|
| `**□ 섹션명**` | □ 섹션 제목 (1단계) |
| `○ 소제목` 또는 plain text | ○ 소제목 (2단계) |
| `- 내용` | - 글머리 (3단계) |

> `**□ 검토의견**`, `**□ 대응방안**` 섹션은 개인 메모용으로 HWP에 포함되지 않습니다.

## 파일 구조

```
├── main.py              # 실행 진입점 (CLI)
├── parser.py            # Obsidian .md 파싱
├── hwpx_writer.py       # HWP 생성 엔진 (HWPX → HWP 변환)
└── template_source.hwpx # HWP 서식 템플릿
```

## 서식 변경 방법

HWP 서식(색상, 폰트, 표 스타일 등)을 변경하려면:

1. HWP에서 기준 문서 열기
2. 원하는 서식으로 수정
3. **다른 이름으로 저장 → HWPX 형식** → `template_source.hwpx` 덮어쓰기
4. 완료 — 다음 실행부터 새 서식 적용

> 템플릿 수정 시 각 의제 항목의 표 구조와 □ 섹션 순서는 유지해야 합니다.
