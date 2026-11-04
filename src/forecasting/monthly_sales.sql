-- One observation per category and order month. No future explanatory variables.
SELECT category, date_trunc('month', order_date)::date AS month,
       SUM(sales) AS sales
FROM dw.v_sales_analysis
GROUP BY category, date_trunc('month', order_date)::date
ORDER BY category, month;
