"""Fixed-configuration 12-month holdouts for customer-day resampling, no fitting on future data."""
from pathlib import Path
from datetime import datetime
import sys
import json
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/dashboard'))
from daily_customers import daily_purchasing_customers,seasonal_customer_scenarios,monthly_summary

def main():
    output=ROOT/'results/monte_carlo'; output.mkdir(parents=True,exist_ok=True)
    report=ROOT/'results/report'; report.mkdir(parents=True,exist_ok=True)
    source=pd.read_csv(ROOT/'data/processed/superstore_processed.csv',usecols=['order_date','customer_id'])
    source.order_date=pd.to_datetime(source.order_date)
    # Target definition is sum of daily unique purchasers, not monthly unique customers.
    observed=daily_purchasing_customers(source,'2011-01-01','2015-01-01')
    records=[]
    for year in (2013,2014):
        cutoff=pd.Timestamp(year,1,1)
        training=daily_purchasing_customers(source.loc[source.order_date.lt(cutoff)],'2011-01-01',cutoff)
        assert training.index.max()<cutoff
        monthly=monthly_summary(seasonal_customer_scenarios(training,months=12,simulations=2000,seed=2026))
        for row in monthly.itertuples(index=False):
            month=pd.Timestamp(row.month); stop=month+pd.DateOffset(months=1)
            prev=month-pd.DateOffset(years=1); prevstop=prev+pd.DateOffset(months=1)
            actual=int(observed.loc[(observed.index>=month)&(observed.index<stop)].sum())
            baseline=int(observed.loc[(observed.index>=prev)&(observed.index<prevstop)].sum())
            records.append({'test_year':year,'train_end':str(training.index.max().date()),
                            'month':str(month.date()),'actual':actual,'predicted':row.expected,
                            'low_p10':row.low,'high_p90':row.high,'seasonal_naive':baseline,
                            'covered_p10_p90':bool(row.low<=actual<=row.high)})
    backtest=pd.DataFrame(records)
    backtest.to_csv(output/'backtest_monthly.csv',index=False)
    def metrics(frame,column):
        error=(frame[column]-frame.actual).abs()
        return {'mae':float(error.mean()),'wape_pct':float(100*error.sum()/frame.actual.sum()),
                'bias_pct':float(100*(frame[column]-frame.actual).sum()/frame.actual.sum())}
    summary={}
    for label,frame in [('2013',backtest.loc[backtest.test_year.eq(2013)]),
                        ('2014',backtest.loc[backtest.test_year.eq(2014)]),('pooled',backtest)]:
        summary[label]={'months':len(frame),'monte_carlo':metrics(frame,'predicted'),
                        'seasonal_naive':metrics(frame,'seasonal_naive'),
                        'p10_p90_coverage_pct':float(100*frame.covered_p10_p90.mean())}
    forecast=monthly_summary(seasonal_customer_scenarios(observed,months=12,simulations=2000,seed=2026))
    forecast.to_csv(output/'forecast_2015_monthly.csv',index=False)
    result={'created_at':datetime.now().astimezone().isoformat(),
        'target':'Sum of daily distinct purchasing customers; same customer on different days counts again.',
        'configuration':{'simulations':2000,'seed':2026,'horizon_months':12,'band':'P10-P90',
                         'sampling':'month + weekday; weekday fallback if fewer than 4 observations',
                         'missing_transaction_days':'zero-filled calendar days','minimum_history_days':28},
        'protocol':'Two fixed-origin 12-month holdouts: train 2011-2012/test 2013; train 2011-2013/test 2014. No parameter search. Baseline: same calendar month last year.',
        'metrics':summary,
        'forecast_2015':{'total':float(forecast.expected.sum()),'monthly_average':float(forecast.expected.mean()),
                         'peak_month':str(forecast.loc[forecast.expected.idxmax(),'month'].date())},
        'limitations':['Only 24 monthly holdout observations; overlapping training periods.',
                      'Scenario bands describe historical resampling variation, not calibrated prediction intervals.',
                      'Independent daily sampling does not model temporal dependence or extrapolate growth.',
                      'No actual 2015 observations exist in the dataset; forecast 2015 cannot be scored.']}
    (output/'evaluation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# CV04 — Mô phỏng Monte Carlo 12 tháng: tham số và kiểm định','',
           '## Định nghĩa chỉ tiêu','',
           'Đếm customer_id phân biệt theo ngày đặt hàng, điền 0 ở ngày không giao dịch. Tổng tháng là tổng lượt khách giao dịch theo ngày; cùng khách ở hai ngày được tính hai lượt. Không phải số khách duy nhất trong tháng hay lượt ghé thăm không mua hàng.','',
           '## Tham số tái lập','',
           '- 2.000 kịch bản; seed 2026; dự báo 12 tháng sau cuối tháng lịch sử.',
           '- Lấy mẫu có hoàn lại theo tháng trong năm và thứ. Nếu nhóm có dưới 4 quan sát, dùng nhóm cùng thứ trong toàn bộ lịch sử.',
           '- Lịch sử phải liên tục, không trùng ngày, có ít nhất 28 ngày; giá trị nguyên không âm.',
           '- Tổng hợp từng đường mô phỏng theo tháng rồi tính mean và quantile 10%/90%. Không cộng các quantile ngày để suy ra quantile tháng.','',
           '## Sửa test','',
           'history.iloc[1:] còn 91 ngày liên tục nên hợp lệ. Đã thay kỳ vọng sai bằng hai trường hợp thực sự không hợp lệ: dưới 28 ngày hoặc thiếu ngày giữa chuỗi. Thêm kiểm tra chấp nhận lịch sử 91 ngày, fallback thiếu mùa và cách đếm tổng lượt theo ngày. Không thay đổi thuật toán hoặc các giá trị dự báo đã công bố.','',
           '## Kiểm định ngoài mẫu','',
           'Giữ cố định tham số, dùng hai mốc dự báo 12 tháng: huấn luyện 2011–2012/kiểm tra 2013 và huấn luyện 2011–2013/kiểm tra 2014. Chỉ dữ liệu trước mốc dự báo được dùng tạo nhóm lấy mẫu. Đối chứng: tổng lượt cùng tháng năm trước.','',
           '| Tập kiểm tra | WAPE Monte Carlo | WAPE đối chứng | Bias Monte Carlo | Tỷ lệ tháng trong P10–P90 |',
           '|---|---:|---:|---:|---:|']
    for key,v in summary.items():
        lines.append(f"| {key} | {v['monte_carlo']['wape_pct']:.2f}% | {v['seasonal_naive']['wape_pct']:.2f}% | {v['monte_carlo']['bias_pct']:.2f}% | {v['p10_p90_coverage_pct']:.2f}% |")
    better=summary['pooled']['monte_carlo']['wape_pct']<summary['pooled']['seasonal_naive']['wape_pct']
    lines += ['',('Monte Carlo có WAPE thấp hơn đối chứng trong phép kiểm tra này.' if better else 'Monte Carlo có WAPE cao hơn đối chứng trong phép kiểm tra này; không nên giới thiệu mô phỏng như mô hình dự báo đã chứng minh tốt hơn phương pháp đơn giản.'),
              'Dải P10–P90 là dải kịch bản tham khảo, chưa được hiệu chỉnh thành khoảng dự báo. Mô hình không ngoại suy xu hướng tăng trưởng và không mô hình hóa phụ thuộc giữa các ngày. Hai tập kiểm tra chỉ có tổng cộng 24 tháng; chưa đủ để kết luận khả năng áp dụng rộng.','',
              '## Tái lập năm 2015','',
              f"Tổng dự kiến {result['forecast_2015']['total']:.4f} lượt, trung bình {result['forecast_2015']['monthly_average']:.4f} lượt/tháng; tháng cao nhất {result['forecast_2015']['peak_month']}. Đây là mô phỏng tham khảo vì không có dữ liệu thực tế 2015 để đánh giá.",'',
              '## Tệp bằng chứng và lệnh chạy','',
              '- `results/monte_carlo/evaluation.json`: cấu hình, giao thức và chỉ số.',
              '- `results/monte_carlo/backtest_monthly.csv`: actual/predicted/baseline/dải của 24 tháng.',
              '- `results/monte_carlo/forecast_2015_monthly.csv`: kết quả 12 tháng.',
              '- `evidence/monte-carlo-tests-final.log`: log unit test sau sửa.','',
              '```powershell',
              '& .runtime/forecast-venv/Scripts/python.exe -X utf8 -m unittest discover -s src/dashboard -p test_daily_customers.py -v',
              '& .runtime/forecast-venv/Scripts/python.exe -X utf8 tools/evaluate_monte_carlo.py','```','',
              'Nội dung này là phần bổ sung báo cáo CV04. Khi hoàn thiện báo cáo PDF cuối ở CV05/CV11, cần đưa tham số, bảng kết quả và giới hạn trên vào phần Monte Carlo; việc sửa PDF gốc chưa thực hiện ở CV04.']
    (report/'CV04_MonteCarlo_KiemDinh.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
