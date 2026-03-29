"""
evaluation/evaluate.py
======================
Offline evaluation harness for the SalesBookingChatBot SQL generation pipeline.

Usage
-----
1. Set the required environment variables (same as the bot):

       export AZURE_OPENAI_ENDPOINT="https://<resource>.openai.azure.com/"
       export AZURE_OPENAI_API_KEY="<key>"
       export AZURE_OPENAI_DEPLOYMENT="<gpt-4o-deployment-name>"
       export AZURE_OPENAI_API_VERSION="2024-02-15-preview"

2. Run from the repository root:

       python -m evaluation.evaluate [--test-file evaluation/test_queries.json]

3. A summary table is printed to stdout and a JSON report is saved to
   ``evaluation/results.json``.

Metrics
-------
- **Exact match** – the generated SQL string, after normalisation, matches the
  expected SQL exactly.
- **Keyword coverage** – what fraction of the key SQL tokens in the expected
  query (table names, column names, aggregate functions) appear in the
  generated query.
- **Safety pass** – the generated SQL passes the :class:`SQLSafetyValidator`
  checks (read-only, valid start token).

The evaluation uses the same :func:`src.utilities.gpt_prompts.GPTPrompts.build_sql_prompt`
system prompt and the same :class:`src.utilities.sql_safety.SQLSafetyValidator`
that are used by the live bot.
"""

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Make sure the repo root is on sys.path so we can import from src/
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from langchain_openai import AzureChatOpenAI
from src.utilities.gpt_prompts import GPTPrompts
from src.utilities.sql_safety import SQLSafetyValidator, SQLSafetyError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise(sql: str) -> str:
    """Lowercase, collapse whitespace, strip trailing semicolons."""
    sql = sql.lower()
    sql = re.sub(r"\s+", " ", sql).strip()
    sql = sql.rstrip(";").strip()
    return sql


def _keyword_coverage(expected_sql: str, generated_sql: str) -> float:
    """
    Fraction of key tokens from *expected_sql* that appear in *generated_sql*.

    Key tokens are words longer than 2 characters that are not SQL keywords.
    """
    _SQL_KW = {
        "select", "from", "where", "join", "inner", "left", "right", "outer",
        "on", "and", "or", "not", "in", "like", "between", "is", "null",
        "as", "by", "group", "order", "having", "top", "distinct", "with",
        "union", "all", "case", "when", "then", "else", "end", "cast",
        "convert", "year", "month", "day", "count", "sum", "avg", "min",
        "max", "isnull", "coalesce", "pivot", "over", "partition", "into",
        "values", "set", "format", "round", "abs", "desc", "asc",
    }
    tokens = re.findall(r"\b(\w+)\b", expected_sql.lower())
    key_tokens = [t for t in tokens if t not in _SQL_KW and len(t) > 2]
    if not key_tokens:
        return 1.0
    matched = sum(1 for t in key_tokens if t in generated_sql.lower())
    return matched / len(key_tokens)


async def _generate_sql(gpt: AzureChatOpenAI, question: str, schema_info: Optional[str]) -> str:
    """Ask the LLM to produce a SQL query for *question*."""
    system_prompt = GPTPrompts.build_sql_prompt.format(schema_info=schema_info or "")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": question},
    ]
    response = await gpt.ainvoke(messages)
    raw = response.content.strip()
    # Strip code fences if present
    raw = raw.replace("```sql", "").replace("```", "").strip()
    return raw


# ---------------------------------------------------------------------------
# Core evaluation loop
# ---------------------------------------------------------------------------

async def evaluate(test_file: str, schema_info: Optional[str] = None) -> dict:
    """
    Run evaluation against *test_file* and return a results dictionary.

    Parameters
    ----------
    test_file:
        Path to a JSON file with the same schema as ``evaluation/test_queries.json``.
    schema_info:
        Optional schema string passed to the system prompt and safety validator.

    Returns
    -------
    dict
        ``{"cases": [...], "summary": {...}}``
    """
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
    api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")

    gpt = AzureChatOpenAI(
        azure_deployment=deployment,
        api_version=api_version,
        temperature=0,
    )

    validator = SQLSafetyValidator(schema_info=None)  # no dict schema in this harness

    with open(test_file, encoding="utf-8") as fh:
        test_cases = json.load(fh)

    results = []

    for case in test_cases:
        qid        = case["id"]
        question   = case["input_question"]
        expected   = case["expected_sql"]
        notes      = case.get("notes", "")

        print(f"  [{qid}] {question[:60]}...")

        try:
            generated = await _generate_sql(gpt, question, schema_info)
        except Exception as exc:
            results.append({
                "id": qid,
                "question": question,
                "expected_sql": expected,
                "generated_sql": "",
                "exact_match": False,
                "keyword_coverage": 0.0,
                "safety_pass": False,
                "error": str(exc),
                "notes": notes,
            })
            continue

        # Metrics
        norm_expected  = _normalise(expected)
        norm_generated = _normalise(generated)
        exact_match    = norm_expected == norm_generated
        kw_coverage    = _keyword_coverage(expected, generated)

        try:
            validator.validate(generated)
            safety_pass = True
            safety_msg  = ""
        except SQLSafetyError as err:
            safety_pass = False
            safety_msg  = str(err)

        results.append({
            "id": qid,
            "question": question,
            "expected_sql": expected,
            "generated_sql": generated,
            "exact_match": exact_match,
            "keyword_coverage": round(kw_coverage, 3),
            "safety_pass": safety_pass,
            "safety_message": safety_msg,
            "notes": notes,
        })

    # Summary
    n          = len(results)
    exact_n    = sum(1 for r in results if r["exact_match"])
    safety_n   = sum(1 for r in results if r["safety_pass"])
    avg_kw     = sum(r["keyword_coverage"] for r in results) / n if n else 0.0

    summary = {
        "total_cases":       n,
        "exact_matches":     exact_n,
        "exact_match_rate":  round(exact_n / n, 3) if n else 0.0,
        "safety_pass_rate":  round(safety_n / n, 3) if n else 0.0,
        "avg_keyword_coverage": round(avg_kw, 3),
    }

    return {"cases": results, "summary": summary}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Evaluate SalesBookingChatBot SQL generation.")
    parser.add_argument(
        "--test-file",
        default=str(_REPO_ROOT / "evaluation" / "test_queries.json"),
        help="Path to the test queries JSON file.",
    )
    parser.add_argument(
        "--schema-info",
        default=None,
        help="Optional path to a plain-text file containing schema information.",
    )
    parser.add_argument(
        "--output",
        default=str(_REPO_ROOT / "evaluation" / "results.json"),
        help="Path to write the JSON results report.",
    )
    args = parser.parse_args()

    schema_info = None
    if args.schema_info and Path(args.schema_info).exists():
        schema_info = Path(args.schema_info).read_text(encoding="utf-8")

    print(f"\nRunning evaluation against: {args.test_file}\n")
    report = asyncio.run(evaluate(args.test_file, schema_info))

    # Print summary
    s = report["summary"]
    print("\n" + "=" * 60)
    print("EVALUATION SUMMARY")
    print("=" * 60)
    print(f"  Total test cases     : {s['total_cases']}")
    print(f"  Exact match rate     : {s['exact_match_rate']:.1%}  ({s['exact_matches']}/{s['total_cases']})")
    print(f"  Safety pass rate     : {s['safety_pass_rate']:.1%}")
    print(f"  Avg keyword coverage : {s['avg_keyword_coverage']:.1%}")
    print("=" * 60)

    # Per-case table
    print(f"\n{'ID':<8} {'Exact':^7} {'Kw Cov':^8} {'Safety':^7}  Question")
    print("-" * 80)
    for r in report["cases"]:
        exact  = "✓" if r["exact_match"]  else "✗"
        safety = "✓" if r["safety_pass"]  else "✗"
        kw     = f"{r['keyword_coverage']:.0%}"
        q      = r["question"][:45]
        print(f"{r['id']:<8} {exact:^7} {kw:^8} {safety:^7}  {q}")

    # Save report
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(f"\nFull report saved to: {args.output}\n")


if __name__ == "__main__":
    main()
