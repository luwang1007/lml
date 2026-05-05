from __future__ import annotations

import argparse
from pathlib import Path

from pypdf import PdfReader


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    reader = PdfReader(str(args.pdf))
    lines = []
    for i, page in enumerate(reader.pages, 1):
        lines.append(f"\n\n===== PAGE {i} =====\n")
        lines.append(page.extract_text() or "")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines), encoding="utf-8")
    print(f"pages={len(reader.pages)} out={args.out}")


if __name__ == "__main__":
    main()
