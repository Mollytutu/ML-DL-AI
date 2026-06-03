import argparse
import csv
import json


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Export a compact school list from school summary data")
    p.add_argument("--summary-csv", required=True)
    p.add_argument("--out-csv", required=True)
    p.add_argument("--out-jsonl", required=False)
    return p.parse_args()


def load_summary_rows(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main() -> None:
    args = parse_args()
    rows = load_summary_rows(args.summary_csv)

    school_list: list[dict] = []
    for row in rows:
        school_list.append(
            {
                "school_num_id": row.get("school_num_id"),
                "school_id": row.get("school_id"),
                "country": row.get("country"),
                "school_name": row.get("school_name") or row.get("school_name_guess"),
                "homepage_url": row.get("homepage_url"),
                "page_count": row.get("page_count"),
                "fact_count": row.get("fact_count"),
                "unique_fact_count": row.get("unique_fact_count"),
                "unique_url_count": row.get("unique_url_count"),
                "page_types": row.get("page_types"),
                "has_deadline_signal": row.get("has_deadline_signal"),
                "has_exam_signal": row.get("has_exam_signal"),
                "has_acceptance_signal": row.get("has_acceptance_signal"),
                "has_applications_signal": row.get("has_applications_signal"),
                "has_admitted_signal": row.get("has_admitted_signal"),
                "has_enrolled_signal": row.get("has_enrolled_signal"),
                "has_yield_signal": row.get("has_yield_signal"),
            }
        )

    with open(args.out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "school_num_id",
                "school_id",
                "country",
                "school_name",
                "homepage_url",
                "page_count",
                "fact_count",
                "unique_fact_count",
                "unique_url_count",
                "page_types",
                "has_deadline_signal",
                "has_exam_signal",
                "has_acceptance_signal",
                "has_applications_signal",
                "has_admitted_signal",
                "has_enrolled_signal",
                "has_yield_signal",
            ],
        )
        writer.writeheader()
        writer.writerows(school_list)

    if args.out_jsonl:
        with open(args.out_jsonl, "w", encoding="utf-8") as f:
            for row in school_list:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"schools={len(school_list)}")
    print(f"out_csv={args.out_csv}")
    if args.out_jsonl:
        print(f"out_jsonl={args.out_jsonl}")


if __name__ == "__main__":
    main()
