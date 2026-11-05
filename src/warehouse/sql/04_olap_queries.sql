-- name: 01_overview
SELECT COUNT(*) AS sales_lines,
       COUNT(DISTINCT (order_id,order_date,customer_id)) AS order_groups,
       COUNT(DISTINCT customer_id) AS customers,
       SUM(sales) AS sales,SUM(profit) AS profit,SUM(quantity) AS quantity,
       SUM(shipping_cost) AS shipping_cost,
       ROUND(SUM(profit)/NULLIF(SUM(sales),0),8) AS profit_margin
FROM dw.v_sales_analysis;

-- name: 02_monthly_growth
WITH monthly AS (
 SELECT calendar_year,calendar_month,SUM(sales) AS sales,SUM(profit) AS profit,
        COUNT(DISTINCT (order_id,order_date,customer_id)) AS order_groups
 FROM dw.v_sales_analysis GROUP BY calendar_year,calendar_month
), previous AS (
 SELECT *,LAG(sales) OVER (ORDER BY calendar_year,calendar_month) AS previous_month_sales,
        LAG(sales,12) OVER (ORDER BY calendar_year,calendar_month) AS previous_year_sales
 FROM monthly
)
SELECT *,ROUND((sales-previous_month_sales)/NULLIF(previous_month_sales,0),8) AS mom_growth,
         ROUND((sales-previous_year_sales)/NULLIF(previous_year_sales,0),8) AS yoy_growth,
         ROUND(profit/NULLIF(sales,0),8) AS profit_margin
FROM previous ORDER BY calendar_year,calendar_month;

-- name: 03_time_rollup
SELECT calendar_year,calendar_quarter,calendar_month,
       GROUPING(calendar_year,calendar_quarter,calendar_month) AS grouping_level,
       SUM(sales) AS sales,SUM(profit) AS profit,SUM(quantity) AS quantity,
       COUNT(DISTINCT (order_id,order_date,customer_id)) AS order_groups
FROM dw.v_sales_analysis
GROUP BY ROLLUP(calendar_year,calendar_quarter,calendar_month)
ORDER BY calendar_year NULLS LAST,calendar_quarter NULLS LAST,calendar_month NULLS LAST;

-- name: 04_product_drilldown
SELECT category,sub_category,SUM(sales) AS sales,SUM(profit) AS profit,
       SUM(quantity) AS quantity,ROUND(SUM(profit)/NULLIF(SUM(sales),0),8) AS profit_margin
FROM dw.v_sales_analysis
GROUP BY ROLLUP(category,sub_category)
ORDER BY category NULLS LAST,sub_category NULLS LAST;

-- name: 05_geography
SELECT market_group,market,region,country,SUM(sales) AS sales,SUM(profit) AS profit,
       SUM(quantity) AS quantity,ROUND(SUM(profit)/NULLIF(SUM(sales),0),8) AS profit_margin
FROM dw.v_sales_analysis
GROUP BY market_group,market,region,country
ORDER BY profit DESC,market,country;

-- name: 06_customer_segments
SELECT segment,COUNT(DISTINCT customer_id) AS customers,
       COUNT(DISTINCT (order_id,order_date,customer_id)) AS order_groups,
       SUM(sales) AS sales,SUM(profit) AS profit,
       ROUND(SUM(profit)/NULLIF(SUM(sales),0),8) AS profit_margin
FROM dw.v_sales_analysis GROUP BY segment ORDER BY profit DESC;

-- name: 07_top_customers
SELECT customer_id,customer_name,segment,
       COUNT(DISTINCT (order_id,order_date,customer_id)) AS order_groups,
       SUM(sales) AS sales,SUM(profit) AS profit
FROM dw.v_sales_analysis
GROUP BY customer_id,customer_name,segment
ORDER BY profit DESC,customer_id LIMIT 20;

-- name: 08_order_shipping
SELECT ship_mode,order_priority,
       COUNT(DISTINCT (order_id,order_date,customer_id)) AS order_groups,
       COUNT(*) AS sales_lines,SUM(sales) AS sales,SUM(profit) AS profit,
       SUM(shipping_cost) AS shipping_cost
FROM dw.v_sales_analysis
GROUP BY ship_mode,order_priority ORDER BY ship_mode,order_priority;

-- name: 09_market_category_cube
SELECT market,category,GROUPING(market,category) AS grouping_level,
       SUM(sales) AS sales,SUM(profit) AS profit,
       ROUND(SUM(profit)/NULLIF(SUM(sales),0),8) AS profit_margin
FROM dw.v_sales_analysis
GROUP BY CUBE(market,category)
ORDER BY market NULLS LAST,category NULLS LAST;

-- name: 10_slice_dice
SELECT calendar_year,calendar_quarter,market,category,sub_category,
       SUM(sales) AS sales,SUM(profit) AS profit,SUM(quantity) AS quantity
FROM dw.v_sales_analysis
WHERE calendar_year=2014 AND market IN ('US','EU') AND category='Technology'
GROUP BY calendar_year,calendar_quarter,market,category,sub_category
ORDER BY calendar_quarter,market,sub_category;

-- name: 11_loss_making_products
SELECT product_id,product_name,category,sub_category,
       COUNT(*) AS sales_lines,SUM(sales) AS sales,SUM(profit) AS profit,
       ROUND(SUM(profit)/NULLIF(SUM(sales),0),8) AS profit_margin
FROM dw.v_sales_analysis
GROUP BY product_id,product_name,category,sub_category
HAVING SUM(profit)<0
ORDER BY profit,product_id,product_name;

-- name: 12_discount_analysis
SELECT CASE WHEN discount=0 THEN '0%'
            WHEN discount<=0.2 THEN '(0%,20%]'
            WHEN discount<=0.4 THEN '(20%,40%]' ELSE '>40%' END AS discount_band,
       COUNT(*) AS sales_lines,SUM(sales) AS sales,SUM(profit) AS profit,
       COUNT(*) FILTER (WHERE profit<0) AS loss_lines,
       ROUND(SUM(profit)/NULLIF(SUM(sales),0),8) AS profit_margin
FROM dw.v_sales_analysis GROUP BY 1 ORDER BY MIN(discount);
