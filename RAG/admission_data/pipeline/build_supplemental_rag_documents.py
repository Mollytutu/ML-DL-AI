from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
CLEAN_DIR = ROOT / "data" / "clean"
RAG_DIR = CLEAN_DIR / "rag"
QS_XLSX = CLEAN_DIR / "2026 QS World University Rankings 1.3 (For qs.com) (1).xlsx"
ADVICE_JSONL = CLEAN_DIR / "advice_data.jsonl"
BASE_RAG_DOCS = RAG_DIR / "rag_documents_deduped.jsonl"
SUPPLEMENTAL_DOCS = RAG_DIR / "rag_supplemental_documents.jsonl"
COMBINED_DOCS = RAG_DIR / "rag_documents_with_supplemental.jsonl"
MANIFEST = RAG_DIR / "rag_supplemental_manifest.json"


def clean_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or "unknown"


def flatten_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            item_text = flatten_value(item)
            if item_text:
                parts.append(f"{key}: {item_text}")
        return "; ".join(parts)
    if isinstance(value, list):
        return ", ".join(clean_value(item) for item in value if clean_value(item))
    return clean_value(value)


def make_doc(doc_id: str, doc_type: str, text: str, metadata: dict) -> dict:
    return {
        "doc_id": doc_id,
        "parent_id": doc_id,
        "doc_type": doc_type,
        "text": text,
        "metadata": {
            **metadata,
            "doc_type": doc_type,
            "chunk_index": 1,
            "chunk_count": 1,
            "data_status": "active",
        },
    }


def qs_documents(path: Path) -> list[dict]:
    df = pd.read_excel(path, header=None)
    docs = []
    for _, row in df.iloc[3:].iterrows():
        rank = clean_value(row[1])
        name = clean_value(row[3])
        country = clean_value(row[4])
        if not rank or not name:
            continue
        previous_rank = clean_value(row[2])
        region = clean_value(row[5])
        size = clean_value(row[6])
        focus = clean_value(row[7])
        research = clean_value(row[8])
        status = clean_value(row[9])
        overall_score = clean_value(row[30])
        ar_score = clean_value(row[10])
        er_score = clean_value(row[12])
        fsr_score = clean_value(row[14])
        cpf_score = clean_value(row[16])
        ifr_score = clean_value(row[18])
        isr_score = clean_value(row[20])
        irn_score = clean_value(row[24])
        eo_score = clean_value(row[26])
        sustainability_score = clean_value(row[28])
        lines = [
            "Document type: university_ranking",
            "Ranking: 2026 QS World University Rankings",
            f"University: {name}",
            f"2026 rank: {rank}",
            f"2025 previous rank: {previous_rank}" if previous_rank else "",
            f"Country/Territory: {country}" if country else "",
            f"Region: {region}" if region else "",
            f"Classification: size {size}, focus {focus}, research {research}, status {status}",
            f"Overall score: {overall_score}" if overall_score else "",
            f"Academic reputation score: {ar_score}" if ar_score else "",
            f"Employer reputation score: {er_score}" if er_score else "",
            f"Faculty student score: {fsr_score}" if fsr_score else "",
            f"Citations per faculty score: {cpf_score}" if cpf_score else "",
            f"International faculty score: {ifr_score}" if ifr_score else "",
            f"International students score: {isr_score}" if isr_score else "",
            f"International research network score: {irn_score}" if irn_score else "",
            f"Employment outcomes score: {eo_score}" if eo_score else "",
            f"Sustainability score: {sustainability_score}" if sustainability_score else "",
        ]
        text = "\n".join(line for line in lines if line)
        doc_id = f"ranking:qs-2026:{slugify(name)}"
        docs.append(
            make_doc(
                doc_id,
                "university_ranking",
                text,
                {
                    "university_name": name,
                    "country": country,
                    "region": region,
                    "ranking_name": "2026 QS World University Rankings",
                    "rank": rank,
                    "previous_rank": previous_rank,
                    "overall_score": overall_score,
                    "source_file": str(path.relative_to(ROOT)),
                },
            )
        )
    return docs


def country_advice_text(row: dict) -> str:
    profile = row.get("country_profile") or {}
    lines = [
        "Document type: country_advice",
        f"Country: {row.get('country')}",
        f"Student visa: {profile.get('student_visa')}",
        f"Degree structure: {flatten_value(profile.get('degree_structure'))}",
        f"Post-study work: {profile.get('post_study_work')}",
        f"Years to possible PR: {profile.get('years_to_possible_pr')}",
        f"Average tuition per year USD: {profile.get('average_tuition_per_year_usd')}",
        f"Average living cost per year USD: {profile.get('average_living_cost_per_year_usd')}",
        f"English requirement: {profile.get('english_requirement')}",
        f"Top fields: {flatten_value(profile.get('top_fields'))}",
        f"Popular schools for Chinese students: {flatten_value(profile.get('top_schools_for_chinese_students'))}",
        f"Average new graduate salary local currency: {profile.get('average_new_grad_salary_local_currency')}",
        f"Average new graduate salary CNY: {profile.get('average_new_grad_salary_cny')}",
        f"Why students choose this country: {profile.get('why_chinese_students_choose')}",
    ]
    return "\n".join(clean_value(line) for line in lines if clean_value(line) and not clean_value(line).endswith(": None"))


def program_advice_text(row: dict) -> str:
    program = row.get("program") or {}
    lines = [
        "Document type: program_advice",
        f"University: {row.get('university_name') or program.get('university_name')}",
        f"Country: {row.get('country') or program.get('country')}",
        f"Program: {program.get('program_name')}",
        f"Degree level: {program.get('degree_level')}",
        f"Program field: {program.get('program_field')}",
        f"Duration: {program.get('duration')}",
        f"Study mode: {program.get('study_mode')}",
        f"Intake months: {program.get('intake_months')}",
        f"Application deadline: {program.get('application_deadline')}",
        f"Minimum GPA requirement: {program.get('minimum_gpa_requirement')}",
        f"English requirement: {program.get('english_requirement')}",
        f"Tuition per year: {program.get('tuition_per_year')}",
        f"Application fee: {program.get('application_fee')}",
        f"Program description: {program.get('program_description')}",
    ]
    return "\n".join(clean_value(line) for line in lines if clean_value(line) and not clean_value(line).endswith(": None"))


def advice_documents(path: Path) -> list[dict]:
    docs = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            record_type = row.get("record_type")
            record_id = row.get("record_id")
            if record_type == "country_profile":
                doc_type = "country_advice"
                text = country_advice_text(row)
                metadata = {
                    "record_id": record_id,
                    "country": row.get("country"),
                    "source_file": str(path.relative_to(ROOT)),
                }
            elif record_type == "program_advice":
                program = row.get("program") or {}
                doc_type = "program_advice"
                text = program_advice_text(row)
                metadata = {
                    "record_id": record_id,
                    "program_id": program.get("program_id"),
                    "program_name": program.get("program_name"),
                    "program_level": program.get("degree_level"),
                    "university_name": row.get("university_name") or program.get("university_name"),
                    "country": row.get("country") or program.get("country"),
                    "source_file": str(path.relative_to(ROOT)),
                }
            else:
                continue
            if text:
                docs.append(make_doc(f"advice:{slugify(record_id or text[:80])}", doc_type, text, metadata))
    return docs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build supplemental RAG docs from rankings and advice files.")
    parser.add_argument("--qs-xlsx", default=str(QS_XLSX))
    parser.add_argument("--advice-jsonl", default=str(ADVICE_JSONL))
    parser.add_argument("--base-rag-docs", default=str(BASE_RAG_DOCS))
    parser.add_argument("--supplemental-output", default=str(SUPPLEMENTAL_DOCS))
    parser.add_argument("--combined-output", default=str(COMBINED_DOCS))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    supplemental_docs = []
    supplemental_docs.extend(qs_documents(Path(args.qs_xlsx)))
    supplemental_docs.extend(advice_documents(Path(args.advice_jsonl)))

    supplemental_path = Path(args.supplemental_output)
    combined_path = Path(args.combined_output)
    supplemental_path.parent.mkdir(parents=True, exist_ok=True)
    with supplemental_path.open("w", encoding="utf-8") as handle:
        for doc in supplemental_docs:
            handle.write(json.dumps(doc, ensure_ascii=False) + "\n")

    with combined_path.open("w", encoding="utf-8") as out:
        with Path(args.base_rag_docs).open(encoding="utf-8") as base:
            for line in base:
                if line.strip():
                    out.write(line)
        for doc in supplemental_docs:
            out.write(json.dumps(doc, ensure_ascii=False) + "\n")

    counts = {}
    for doc in supplemental_docs:
        counts[doc["doc_type"]] = counts.get(doc["doc_type"], 0) + 1
    manifest = {
        "supplemental_output": str(supplemental_path.relative_to(ROOT)),
        "combined_output": str(combined_path.relative_to(ROOT)),
        "supplemental_count": len(supplemental_docs),
        "doc_type_counts": dict(sorted(counts.items())),
        "inputs": [str(Path(args.qs_xlsx).relative_to(ROOT)), str(Path(args.advice_jsonl).relative_to(ROOT))],
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
