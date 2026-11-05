"""Create, load, verify and query the Superstore PostgreSQL warehouse."""
from pathlib import Path
from decimal import Decimal
import argparse
import csv
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
from datetime import date, datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parents[2]
SQL = Path(__file__).parent/"sql"
SOURCE = ROOT/"data"/"processed"/"superstore_processed.csv"
RESULTS = ROOT/"results"/"warehouse"
SOURCE_COLUMNS = [
    "category","city","country","customer_id","customer_name","discount","market",
    "order_date","order_id","order_priority","product_id","product_name","profit",
    "quantity","region","row_id","sales","segment","ship_date","ship_mode",
    "shipping_cost","state","sub_category","market_group","weeknum","profit_margin"]
NUMBER_COLUMNS = {"discount","profit","quantity","row_id","sales","shipping_cost","weeknum","profit_margin"}
PRIMARY_KEYS = {
    "dim_date":["full_date"],"dim_customer":["customer_id"],
    "dim_product":["product_id","product_name"],
    "dim_geography":["country","state","city","region","market"],
    "dim_order":["order_id","order_date","customer_id"],"fact_sales":["row_id"]}

def read_source():
    with SOURCE.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != SOURCE_COLUMNS:
            raise ValueError("CSV column order differs from the agreed processed dataset.")
        rows = list(reader)
    if not rows or len({r["row_id"] for r in rows}) != len(rows):
        raise ValueError("The source is empty or contains duplicate row_id values.")
    return rows

def psql_command(dsn):
    executable = os.environ.get("PSQL_PATH") or str(ROOT/".runtime"/"pgsql"/"bin"/"psql.exe")
    if not Path(executable).is_file():
        executable = shutil.which("psql")
    if not executable:
        raise FileNotFoundError("Run setup_local_postgres.py first, or set PSQL_PATH.")
    return [executable,"-X","-q","-v","ON_ERROR_STOP=1","-d",dsn]

def execute(command, statement):
    env = os.environ.copy()
    env.update(PGCLIENTENCODING="UTF8", PGCONNECT_TIMEOUT="10", PGDATESTYLE="ISO, YMD")
    env.setdefault("PGPASSFILE", str(ROOT/".runtime"/"pgpass.conf"))
    result = subprocess.run(command, input=statement, capture_output=True, text=True,
                            encoding="utf-8", env=env,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return result.stdout

def query_csv(command, query):
    return execute(command, f"COPY ({query.strip().rstrip(';')}) TO STDOUT WITH (FORMAT CSV, HEADER true);\n")

def read_query(command, query):
    return list(csv.DictReader(io.StringIO(query_csv(command,query))))

def create(command):
    execute(command,(SQL/"01_create_tables.sql").read_text(encoding="utf-8"))
    execute(command,(SQL/"03_analysis_view.sql").read_text(encoding="utf-8"))
    print("Created/checked 5 dimensions, fact_sales and the analysis view.")

def load(command):
    read_source()
    script = (SQL/"02_load_data.sql").read_text(encoding="utf-8")
    csv_path = SOURCE.as_posix().replace("'","''")
    execute(command,script.replace("__CSV_PATH__",csv_path))
    print("Loaded dimensions first, then fact_sales. Existing row_id values are updated.")

def verify(command):
    source = read_source()
    actual = read_query(command,"SELECT "+",".join(SOURCE_COLUMNS)+" FROM dw.v_sales_analysis ORDER BY row_id")
    expected_by_id = {r["row_id"]:r for r in source}
    if len(actual)!=len(source) or {r["row_id"] for r in actual}!=set(expected_by_id):
        raise AssertionError("Fact rows or analysis joins lost/duplicated source rows.")
    for row in actual:
        expected = expected_by_id[row["row_id"]]
        for col in SOURCE_COLUMNS:
            if col not in NUMBER_COLUMNS:
                if row[col]!=expected[col]:
                    raise AssertionError(f"row_id={row['row_id']}: {col} differs")
            elif col=="profit_margin":
                if expected[col]=="":
                    if row[col]!="":raise AssertionError("Undefined margin must stay NULL.")
                elif row[col]=="" or abs(Decimal(row[col])-Decimal(expected[col]))>Decimal("0.00000001"):
                    raise AssertionError(f"row_id={row['row_id']}: margin differs")
            elif Decimal(row[col])!=Decimal(expected[col]):
                raise AssertionError(f"row_id={row['row_id']}: {col} differs")
    totals=[]
    for col in ["sales","profit","quantity","shipping_cost"]:
        before=sum((Decimal(r[col]) for r in source),Decimal(0))
        after=sum((Decimal(r[col]) for r in actual),Decimal(0))
        assert before==after
        totals.append({"measure":col,"csv_total":str(before),"warehouse_total":str(after),"difference":str(after-before)})
    counts={}
    for table,keys in PRIMARY_KEYS.items():
        count=int(read_query(command,f"SELECT count(*) AS n FROM dw.{table}")[0]["n"])
        counts[table]=count
        if table not in {"dim_date","fact_sales"}:
            expected_count=len({tuple(r[k] for k in keys) for r in source})
            assert count==expected_count,(table,count,expected_count)
    first=min(min(date.fromisoformat(r[c]) for r in source) for c in ["order_date","ship_date"])
    last=max(max(date.fromisoformat(r[c]) for r in source) for c in ["order_date","ship_date"])
    assert counts["dim_date"]==(last-first).days+1
    constraints=read_query(command,"""
        SELECT conname,contype,pg_get_constraintdef(oid) AS definition,convalidated
        FROM pg_constraint WHERE connamespace='dw'::regnamespace
        ORDER BY conrelid::regclass::text,conname
    """)
    assert sum(c["contype"]=="f" for c in constraints)==6
    assert all(c["convalidated"]=="t" for c in constraints)
    assert sum(c["contype"]=="p" for c in constraints)==6
    overview=read_query(command,"""
        SELECT count(*) AS sales_lines,
               count(DISTINCT (order_id,order_date,customer_id)) AS order_groups,
               count(*) FILTER (WHERE profit<0) AS loss_lines,
               count(*) FILTER (WHERE sales=0) AS zero_sales_lines,
               count(*) FILTER (WHERE profit_margin IS NULL) AS null_margin_lines,
               sum(sales) AS sales,sum(profit) AS profit,sum(quantity) AS quantity,
               sum(shipping_cost) AS shipping_cost
        FROM dw.fact_sales
    """)[0]
    report={
        "verified_at":datetime.now(timezone(timedelta(hours=7))).isoformat(timespec="seconds"),
        "postgresql":read_query(command,"SELECT version() AS version")[0]["version"],
        "source_file":str(SOURCE.relative_to(ROOT)).replace("\\","/"),
        "source_sha256":hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "source_rows":len(source),"warehouse_rows":len(actual),
        "all_26_columns_reconciled":True,"foreign_keys_validated":6,
        "table_counts":counts,"overview":overview,"measure_reconciliation":totals,
        "constraints":constraints,"status":"passed"}
    RESULTS.mkdir(parents=True,exist_ok=True)
    (RESULTS/"verification.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    with (RESULTS/"reconciliation.csv").open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(totals[0]));writer.writeheader();writer.writerows(totals)
    print("Verified every source row and all 26 columns; 6 foreign keys are valid.")
    print("Table counts:",counts)
    return report

def olap(command):
    source=read_source()
    expected_sales=sum((Decimal(r["sales"]) for r in source),Decimal(0))
    script=(SQL/"04_olap_queries.sql").read_text(encoding="utf-8")
    parts=re.split(r"(?m)^-- name: ([a-z0-9_]+)\s*$",script)
    folder=RESULTS/"olap";folder.mkdir(parents=True,exist_ok=True)
    output={}
    for index in range(1,len(parts),2):
        name,query=parts[index],parts[index+1].strip()
        content=query_csv(command,query)
        rows=list(csv.DictReader(io.StringIO(content)))
        (folder/f"{name}.csv").write_text(content,encoding="utf-8-sig",newline="")
        output[name]=rows
        print(f"{name}: {len(rows)} rows")
    assert len(output["02_monthly_growth"])==48
    assert output["02_monthly_growth"][0]["mom_growth"]==""
    assert all(r["yoy_growth"]=="" for r in output["02_monthly_growth"][:12])
    for name in ["02_monthly_growth","05_geography","06_customer_segments","08_order_shipping","12_discount_analysis"]:
        assert sum((Decimal(r["sales"]) for r in output[name]),Decimal(0))==expected_sales,name
    for name in ["03_time_rollup","09_market_category_cube"]:
        grand=[r for r in output[name] if r["grouping_level"]==("7" if name=="03_time_rollup" else "3")]
        assert len(grand)==1 and Decimal(grand[0]["sales"])==expected_sales
    summary={name:len(rows) for name,rows in output.items()}
    (RESULTS/"olap_summary.json").write_text(json.dumps({"status":"passed","queries":summary},indent=2),encoding="utf-8")
    print("OLAP totals, subtotal flags and growth boundaries verified.")

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=["create","load","verify","olap","all"],nargs="?",default="all")
    parser.add_argument("--dsn",default=os.environ.get("SUPERSTORE_DATABASE_URL",
                        "postgresql://superstore@127.0.0.1:55432/superstore_dw?sslmode=disable"))
    args=parser.parse_args()
    command=psql_command(args.dsn)
    if args.action in {"create","all"}:create(command)
    if args.action in {"load","all"}:load(command)
    if args.action in {"verify","all"}:verify(command)
    if args.action in {"olap","all"}:olap(command)

if __name__=="__main__":
    main()
