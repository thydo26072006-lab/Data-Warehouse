BEGIN;
CREATE TEMP TABLE stage_sales (
    category varchar(50), city varchar(100), country varchar(100),
    customer_id varchar(20), customer_name varchar(100), discount numeric(6,4),
    market varchar(20), order_date date, order_id varchar(30), order_priority varchar(20),
    product_id varchar(30), product_name varchar(255), profit numeric(18,5),
    quantity smallint, region varchar(50), row_id integer, sales numeric(18,5),
    segment varchar(30), ship_date date, ship_mode varchar(30), shipping_cost numeric(18,5),
    state varchar(100), sub_category varchar(50), market_group varchar(30),
    weeknum smallint, profit_margin numeric(18,8)
) ON COMMIT DROP;
-- The Python launcher substitutes the quoted path; psql \copy reads the client file.
\copy stage_sales FROM '__CSV_PATH__' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')

INSERT INTO dw.dim_date
SELECT d::date, EXTRACT(YEAR FROM d)::smallint, EXTRACT(QUARTER FROM d)::smallint,
       EXTRACT(MONTH FROM d)::smallint, EXTRACT(ISOYEAR FROM d)::smallint,
       EXTRACT(WEEK FROM d)::smallint
FROM generate_series(
    (SELECT LEAST(min(order_date),min(ship_date)) FROM stage_sales)::timestamp,
    (SELECT GREATEST(max(order_date),max(ship_date)) FROM stage_sales)::timestamp,
    interval '1 day') AS dates(d)
ON CONFLICT (full_date) DO NOTHING;

INSERT INTO dw.dim_customer
SELECT DISTINCT customer_id,customer_name,segment FROM stage_sales
ON CONFLICT (customer_id) DO UPDATE
SET customer_name=EXCLUDED.customer_name, segment=EXCLUDED.segment;

INSERT INTO dw.dim_product
SELECT DISTINCT product_id,product_name,category,sub_category FROM stage_sales
ON CONFLICT (product_id,product_name) DO UPDATE
SET category=EXCLUDED.category, sub_category=EXCLUDED.sub_category;

INSERT INTO dw.dim_geography
SELECT DISTINCT country,state,city,region,market,market_group FROM stage_sales
ON CONFLICT (country,state,city,region,market) DO UPDATE SET market_group=EXCLUDED.market_group;

INSERT INTO dw.dim_order
SELECT DISTINCT order_id,order_date,customer_id,ship_mode,order_priority FROM stage_sales
ON CONFLICT (order_id,order_date,customer_id) DO UPDATE
SET ship_mode=EXCLUDED.ship_mode, order_priority=EXCLUDED.order_priority;

INSERT INTO dw.fact_sales (
    row_id,order_date,ship_date,product_id,product_name,country,state,city,region,market,
    customer_id,order_id,weeknum,sales,profit,quantity,discount,shipping_cost,profit_margin)
SELECT row_id,order_date,ship_date,product_id,product_name,country,state,city,region,market,
       customer_id,order_id,weeknum,sales,profit,quantity,discount,shipping_cost,profit_margin
FROM stage_sales
ON CONFLICT (row_id) DO UPDATE SET
    order_date=EXCLUDED.order_date, ship_date=EXCLUDED.ship_date,
    product_id=EXCLUDED.product_id, product_name=EXCLUDED.product_name,
    country=EXCLUDED.country, state=EXCLUDED.state, city=EXCLUDED.city,
    region=EXCLUDED.region, market=EXCLUDED.market, customer_id=EXCLUDED.customer_id,
    order_id=EXCLUDED.order_id, weeknum=EXCLUDED.weeknum,
    sales=EXCLUDED.sales, profit=EXCLUDED.profit, quantity=EXCLUDED.quantity,
    discount=EXCLUDED.discount, shipping_cost=EXCLUDED.shipping_cost,
    profit_margin=EXCLUDED.profit_margin;
COMMIT;
ANALYZE dw.dim_date;
ANALYZE dw.dim_customer;
ANALYZE dw.dim_product;
ANALYZE dw.dim_geography;
ANALYZE dw.dim_order;
ANALYZE dw.fact_sales;
