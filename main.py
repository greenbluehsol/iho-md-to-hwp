"""
main.py
사용법:
  python main.py single <md파일경로>            # 단일 파일 → HWP
  python main.py single <md파일경로> -o <출력>  # 출력경로 지정
  python main.py batch  <폴더경로>              # 폴더 전체 → 개별 HWP
  python main.py batch  <폴더경로> --combined   # 폴더 전체 → 하나의 HWP
  python main.py batch  <폴더경로> --combined -o <출력파일>
"""
import sys
import argparse
from pathlib import Path

from parser import parse_md_file, parse_folder
from hwpx_writer import generate_single, generate_combined


def cmd_single(args):
    md_path = Path(args.file)
    if not md_path.exists():
        print(f"[오류] 파일 없음: {md_path}")
        sys.exit(1)

    item = parse_md_file(md_path)
    if not item.agenda_number:
        print(f"[경고] 의제번호를 파싱하지 못했습니다: {md_path.name}")

    if args.output:
        out_path = Path(args.output)
    else:
        out_path = md_path.with_suffix(".hwp")

    print(f"생성 중: {out_path.name}")
    generate_single(item, out_path)


def cmd_batch(args):
    folder = Path(args.folder)
    if not folder.is_dir():
        print(f"[오류] 폴더 없음: {folder}")
        sys.exit(1)

    items = parse_folder(folder)
    if not items:
        print("[오류] .md 파일이 없습니다.")
        sys.exit(1)

    print(f"파싱 완료: {len(items)}개 파일")
    for item in items:
        print(f"  - {item.agenda_number}: {item.title_ko[:30] if item.title_ko else item.file_path.name}")

    if args.combined:
        if args.output:
            out_path = Path(args.output)
        else:
            out_path = folder / f"{folder.name}_combined.hwp"
        print(f"\n통합 HWP 생성 중: {out_path.name}")
        generate_combined(items, out_path)
    else:
        for item in items:
            out_path = item.file_path.with_suffix(".hwp")
            print(f"\n생성 중: {out_path.name}")
            generate_single(item, out_path)


def main():
    parser = argparse.ArgumentParser(
        description="Obsidian 의제 분석 .md → HWP 변환기",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    sub = parser.add_subparsers(dest="command")

    # single
    p_single = sub.add_parser("single", help="단일 .md 파일 변환")
    p_single.add_argument("file", help=".md 파일 경로")
    p_single.add_argument("-o", "--output", help="출력 .hwp 파일 경로 (기본: 같은 폴더)")

    # batch
    p_batch = sub.add_parser("batch", help="폴더 내 모든 .md 파일 변환")
    p_batch.add_argument("folder", help=".md 파일들이 있는 폴더")
    p_batch.add_argument("--combined", action="store_true", help="하나의 HWP 파일로 합치기")
    p_batch.add_argument("-o", "--output", help="통합 출력 파일 경로 (--combined 사용 시)")

    args = parser.parse_args()

    if args.command == "single":
        cmd_single(args)
    elif args.command == "batch":
        cmd_batch(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
