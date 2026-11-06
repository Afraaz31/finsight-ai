"""Upload your own files and ask questions about them, from the terminal.

python -m scripts.upload_cli add samples/northwind_annual_report.pdf
python -m scripts.upload_cli list
python -m scripts.upload_cli ask <doc_id> "What was total revenue?"
python -m scripts.upload_cli ask <doc_id> <doc_id2> "Compare the two reports"
python -m scripts.upload_cli ask <doc_id> "Net profit margin by year" --sheet "Income Statement"
python -m scripts.upload_cli delete <doc_id>
"""
import argparse
import logging
from pathlib import Path

from backend.services.document_qa_service import answer_upload_question
from backend.services.llm_service import LLMError
from backend.services.table_service import PlanError, table_to_text
from backend.services.upload_service import UploadError, add_upload, delete_upload, list_uploads

import pandas as pd


def cmd_add(args) -> None:
    path = Path(args.path)
    if not path.exists():
        raise SystemExit(f"File not found: {path}")
    meta = add_upload(path.name, path.read_bytes())
    print(f"\nUploaded '{meta['filename']}'  ->  doc_id = {meta['doc_id']}   (kind: {meta['kind']})")
    if meta["kind"] == "text":
        print(f"  {meta['pages']} page(s), {meta['characters']:,} characters, {meta['chunks']} chunks")
    else:
        for t in meta["tables"]:
            shape = "  (wide year columns reshaped to Period/Value)" if t["reshaped_to_long"] else ""
            print(f"  sheet '{t['sheet']}': {t['rows']} rows, columns {t['columns']}{shape}")


def cmd_list(_args) -> None:
    uploads = list_uploads()
    if not uploads:
        print("No uploads yet.")
    for m in uploads:
        print(f"{m['doc_id']}  {m['kind']:<5}  {m['uploaded_at']}  {m['filename']}")


def cmd_delete(args) -> None:
    delete_upload(args.doc_id)
    print(f"Deleted {args.doc_id}")


def cmd_ask(args) -> None:
    result = answer_upload_question(args.question, args.doc_ids, sheet=args.sheet,
                                    use_cache=not args.no_cache)
    print(f"\nQ: {args.question}\n\n{result['answer']}")
    if result.get("calculation"):
        calc = result["calculation"]
        print(f"\nCalculation (done by Python, not the AI): {calc['summary']}")
        print(f"Plan: {calc['plan']}")
        if calc["table"]:
            print(table_to_text(pd.DataFrame(calc["table"])))
    if result["sources"]:
        print("\nSources:")
        for s in result["sources"]:
            where = f"page {s['page']}" if "page" in s else f"sheet {s['sheet']}"
            label = f"[{s['number']}] " if "number" in s else ""
            print(f"  {label}{s['filename']} - {where}")
    if result["cached"]:
        print(f"\n(answer from cache - no quota used; originally by {result['model']})")
    elif result.get("model"):
        print(f"\n(answered by {result['model']})")


def main() -> None:
    parser = argparse.ArgumentParser(description="FinSight uploads")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("add"); p.add_argument("path"); p.set_defaults(func=cmd_add)
    p = sub.add_parser("list"); p.set_defaults(func=cmd_list)
    p = sub.add_parser("delete"); p.add_argument("doc_id"); p.set_defaults(func=cmd_delete)
    p = sub.add_parser("ask")
    p.add_argument("doc_ids", nargs="+", help="one or more doc ids, then the question")
    p.add_argument("--sheet"); p.add_argument("--no-cache", action="store_true")
    p.set_defaults(func=cmd_ask)
    args = parser.parse_args()
    if args.command == "ask":            # last positional value is the question
        if len(args.doc_ids) < 2:
            raise SystemExit('Usage: ask <doc_id> [<doc_id> ...] "question"')
        *args.doc_ids, args.question = args.doc_ids
    logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
    try:
        args.func(args)
    except (UploadError, PlanError, LLMError, ValueError) as exc:
        raise SystemExit(f"\nProblem: {exc}")


if __name__ == "__main__":
    main()
