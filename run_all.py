"""Run the whole pipeline in order.

    python run_all.py              everything; uses cached LLM labels, never calls the API
    python run_all.py --classify   also send uncached sample rows to the LLM API
                                   (needs GEMINI_API_KEY for the default model, or
                                   ANTHROPIC_API_KEY with a claude model; stops at USD 10)
    python run_all.py --skip-download   reuse files already in data/raw

Without --classify the run costs nothing: LLM labels are read from
outputs/llm_labels.jsonl if they exist, and the clearly labeled fallback model is
used if they do not.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
EXIT_NO_KEY, EXIT_OVER_BUDGET, EXIT_NO_LLM_LABELS, EXIT_DAILY_QUOTA = 3, 2, 3, 4


def step(title: str, script: str, *args: str, allow: tuple[int, ...] = ()) -> int:
    print(f"\n=== {title} ===", flush=True)
    code = subprocess.run([sys.executable, str(SRC / script), *args], cwd=ROOT).returncode
    if code != 0 and code not in allow:
        print(f"Step failed with exit code {code}: {script} {' '.join(args)}")
        sys.exit(code)
    return code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--classify", action="store_true", help="call the LLM API for uncached rows")
    parser.add_argument("--skip-download", action="store_true")
    args = parser.parse_args()

    if not args.skip_download:
        step("1. Download CFPB archive files", "download.py")
    step("2. Filter to credit cards and the seven issuers", "ingest.py")
    step("3. Cross-check against the live CFPB API", "api_check.py")
    step("4. Data profile", "data_profile.py")
    step("5. Structured analysis (DuckDB SQL)", "run_sql.py")
    step("6. Stratified sample", "sample.py")
    step("7. Cost estimate (no billable calls)", "classify.py", "estimate")

    if args.classify:
        code = step("8. LLM classification", "classify.py", "run", allow=(EXIT_NO_KEY, EXIT_OVER_BUDGET, EXIT_DAILY_QUOTA))
        if code == EXIT_NO_KEY:
            print("Stopped: the API key is missing. Set it and rerun with --classify.")
            return EXIT_NO_KEY
        if code == EXIT_DAILY_QUOTA:
            print("The provider's daily quota ran out. Continuing with the labels collected so far.")
        if code == EXIT_OVER_BUDGET:
            print("Stopped: the budget check failed. Nothing beyond the budget was sent.")
            return EXIT_OVER_BUDGET
    else:
        print("\n=== 8. LLM classification skipped (cached labels are used if present) ===")

    step("9. Theme model for all narratives (LLM-distilled, or labeled fallback)", "fallback.py")
    step("10. Validation set", "validation.py", "build", allow=(1, EXIT_NO_LLM_LABELS))
    step("11. Validation score", "validation.py", "score", allow=(1,))
    step("12. Theme tables and quotes", "themes.py")
    step("13. Event study", "event_study.py")
    step("14. Findings", "findings.py")
    step("15. Dashboard", "dashboard.py")
    step("16. Memo, README and interview documents", "report.py")
    print("\nDone. Open docs/index.html.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
