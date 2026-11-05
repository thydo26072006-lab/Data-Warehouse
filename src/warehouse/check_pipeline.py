"""Integration checks against the project's PostgreSQL warehouse."""
import csv
import json
from pathlib import Path
import warehouse as w

def expect_rejected(command,sql,expected_message):
    try:
        w.execute(command,"BEGIN;\n"+sql+"\nROLLBACK;\n")
    except RuntimeError as error:
        if expected_message not in str(error):
            raise
    else:
        raise AssertionError("The database accepted invalid data.")

def main():
    import os
    command=w.psql_command(os.environ.get("SUPERSTORE_DATABASE_URL",
        "postgresql://superstore@127.0.0.1:55432/superstore_dw?sslmode=disable"))
    checks=[]
    before=w.verify(command)
    w.load(command)
    after=w.verify(command)
    assert before["table_counts"]==after["table_counts"]
    assert before["overview"]==after["overview"]
    checks.append("Rerun load preserves counts, totals and all 26 source columns")

    expect_rejected(command,"""
        UPDATE dw.fact_sales SET row_id=(SELECT min(row_id) FROM dw.fact_sales)
        WHERE row_id=(SELECT max(row_id) FROM dw.fact_sales);
    ""","fact_sales_pkey")
    checks.append("Duplicate row_id rejected")
    expect_rejected(command,"""
        UPDATE dw.fact_sales SET product_name='__invalid_product_combination__'
        WHERE row_id=(SELECT min(row_id) FROM dw.fact_sales);
    ""","fk_product")
    checks.append("Invalid composite product FK rejected")
    expect_rejected(command,"""
        UPDATE dw.fact_sales SET quantity=0
        WHERE row_id=(SELECT min(row_id) FROM dw.fact_sales);
    ""","fact_sales_quantity_check")
    checks.append("Non-positive quantity rejected")
    expect_rejected(command,"""
        UPDATE dw.fact_sales SET profit_margin=0 WHERE sales=0;
    ""","check constraint")
    checks.append("Zero-sales margin must remain NULL")

    # Make a temporary validation input outside data/processed. Change a dimension
    # description first, then force a fact CHECK failure; the whole load must roll back.
    original_source=w.SOURCE
    scratch=w.ROOT/".runtime"/"validation_discount.csv"
    if scratch.exists():
        raise FileExistsError("Validation scratch path already exists; no file was overwritten.")
    rows=w.read_source()
    customer=rows[0]["customer_id"]
    for row in rows:
        if row["customer_id"]==customer:
            row["customer_name"]="Rollback validation customer"
    rows[-1]["discount"]="2"
    try:
        with scratch.open("w",encoding="utf-8-sig",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=w.SOURCE_COLUMNS)
            writer.writeheader();writer.writerows(rows)
        w.SOURCE=scratch
        try:
            w.load(command)
        except RuntimeError as error:
            if "fact_sales_discount_check" not in str(error):
                raise
        else:
            raise AssertionError("Invalid load unexpectedly committed.")
    finally:
        w.SOURCE=original_source
        scratch.unlink(missing_ok=True)
    final=w.verify(command)
    assert final["table_counts"]==before["table_counts"]
    assert final["overview"]==before["overview"]
    checks.append("Failed fact load rolls back dimension changes as well")
    w.olap(command)
    checks.append("All 12 OLAP queries and aggregate checks pass")
    report={"status":"passed","checks":checks}
    (w.RESULTS/"integration_checks.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    for check in checks:
        print("PASS:",check)

if __name__=="__main__":
    main()
