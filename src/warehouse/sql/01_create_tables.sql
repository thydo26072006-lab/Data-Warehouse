BEGIN;
CREATE SCHEMA IF NOT EXISTS dw;

CREATE TABLE IF NOT EXISTS dw.dim_date (
    full_date date PRIMARY KEY,
    calendar_year smallint NOT NULL,
    calendar_quarter smallint NOT NULL CHECK (calendar_quarter BETWEEN 1 AND 4),
    calendar_month smallint NOT NULL CHECK (calendar_month BETWEEN 1 AND 12),
    iso_year smallint NOT NULL,
    iso_week smallint NOT NULL CHECK (iso_week BETWEEN 1 AND 53),
    CHECK (calendar_year = EXTRACT(YEAR FROM full_date)),
    CHECK (calendar_quarter = EXTRACT(QUARTER FROM full_date)),
    CHECK (calendar_month = EXTRACT(MONTH FROM full_date)),
    CHECK (iso_year = EXTRACT(ISOYEAR FROM full_date)),
    CHECK (iso_week = EXTRACT(WEEK FROM full_date))
);
CREATE TABLE IF NOT EXISTS dw.dim_customer (
    customer_id varchar(20) PRIMARY KEY,
    customer_name varchar(100) NOT NULL,
    segment varchar(30) NOT NULL
);
CREATE TABLE IF NOT EXISTS dw.dim_product (
    product_id varchar(30) NOT NULL,
    product_name varchar(255) NOT NULL,
    category varchar(50) NOT NULL,
    sub_category varchar(50) NOT NULL,
    PRIMARY KEY (product_id, product_name)
);
CREATE TABLE IF NOT EXISTS dw.dim_geography (
    country varchar(100) NOT NULL,
    state varchar(100) NOT NULL,
    city varchar(100) NOT NULL,
    region varchar(50) NOT NULL,
    market varchar(20) NOT NULL,
    market_group varchar(30) NOT NULL,
    PRIMARY KEY (country, state, city, region, market)
);
CREATE TABLE IF NOT EXISTS dw.dim_order (
    order_id varchar(30) NOT NULL,
    order_date date NOT NULL,
    customer_id varchar(20) NOT NULL,
    ship_mode varchar(30) NOT NULL,
    order_priority varchar(20) NOT NULL,
    PRIMARY KEY (order_id, order_date, customer_id)
);
CREATE TABLE IF NOT EXISTS dw.fact_sales (
    row_id integer PRIMARY KEY CHECK (row_id > 0),
    order_date date NOT NULL,
    ship_date date NOT NULL,
    product_id varchar(30) NOT NULL,
    product_name varchar(255) NOT NULL,
    country varchar(100) NOT NULL,
    state varchar(100) NOT NULL,
    city varchar(100) NOT NULL,
    region varchar(50) NOT NULL,
    market varchar(20) NOT NULL,
    customer_id varchar(20) NOT NULL,
    order_id varchar(30) NOT NULL,
    weeknum smallint NOT NULL CHECK (weeknum BETWEEN 1 AND 53),
    sales numeric(18,5) NOT NULL CHECK (sales >= 0),
    profit numeric(18,5) NOT NULL,
    quantity smallint NOT NULL CHECK (quantity > 0),
    discount numeric(6,4) NOT NULL CHECK (discount BETWEEN 0 AND 1),
    shipping_cost numeric(18,5) NOT NULL CHECK (shipping_cost >= 0),
    profit_margin numeric(18,8),
    CONSTRAINT fk_order_date FOREIGN KEY (order_date) REFERENCES dw.dim_date (full_date),
    CONSTRAINT fk_ship_date FOREIGN KEY (ship_date) REFERENCES dw.dim_date (full_date),
    CONSTRAINT fk_customer FOREIGN KEY (customer_id) REFERENCES dw.dim_customer (customer_id),
    CONSTRAINT fk_product FOREIGN KEY (product_id, product_name)
        REFERENCES dw.dim_product (product_id, product_name),
    CONSTRAINT fk_geography FOREIGN KEY (country, state, city, region, market)
        REFERENCES dw.dim_geography (country, state, city, region, market),
    CONSTRAINT fk_order FOREIGN KEY (order_id, order_date, customer_id)
        REFERENCES dw.dim_order (order_id, order_date, customer_id),
    CHECK (ship_date >= order_date),
    CHECK ((sales = 0 AND profit_margin IS NULL) OR
           (sales > 0 AND profit_margin IS NOT NULL
            AND abs(profit_margin - round(profit / NULLIF(sales,0),8)) <= 0.00000001))
);
CREATE INDEX IF NOT EXISTS fact_sales_order_date_idx ON dw.fact_sales (order_date);
CREATE INDEX IF NOT EXISTS fact_sales_ship_date_idx ON dw.fact_sales (ship_date);
CREATE INDEX IF NOT EXISTS fact_sales_product_idx ON dw.fact_sales (product_id, product_name);
CREATE INDEX IF NOT EXISTS fact_sales_customer_idx ON dw.fact_sales (customer_id);
CREATE INDEX IF NOT EXISTS fact_sales_order_idx ON dw.fact_sales (order_id, order_date, customer_id);
CREATE INDEX IF NOT EXISTS fact_sales_geography_idx ON dw.fact_sales (country, state, city, region, market);
COMMIT;
