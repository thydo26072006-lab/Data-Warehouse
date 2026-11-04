CREATE OR REPLACE VIEW dw.v_sales_analysis AS
SELECT f.*,d.calendar_year,d.calendar_quarter,d.calendar_month,d.iso_year,d.iso_week,
       s.calendar_year AS ship_year,s.calendar_month AS ship_month,
       p.category,p.sub_category,c.customer_name,c.segment,g.market_group,
       o.ship_mode,o.order_priority
FROM dw.fact_sales f
JOIN dw.dim_date d ON d.full_date=f.order_date
JOIN dw.dim_date s ON s.full_date=f.ship_date
JOIN dw.dim_customer c ON c.customer_id=f.customer_id
JOIN dw.dim_product p ON (p.product_id,p.product_name)=(f.product_id,f.product_name)
JOIN dw.dim_geography g ON (g.country,g.state,g.city,g.region,g.market)=
                          (f.country,f.state,f.city,f.region,f.market)
JOIN dw.dim_order o ON (o.order_id,o.order_date,o.customer_id)=
                      (f.order_id,f.order_date,f.customer_id);
