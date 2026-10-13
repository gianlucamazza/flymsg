"""Print the evidence audit (SF1, issue #147): per record its status and the fields recorded
as unknown, per lock its evidence records. Usage: uv run python scripts/evidence_audit.py"""

from flymsg import evidence

if __name__ == "__main__":
    print(evidence.audit())
