# CV04 — Mô phỏng Monte Carlo 12 tháng: tham số và kiểm định

## Định nghĩa chỉ tiêu

Đếm customer_id phân biệt theo ngày đặt hàng, điền 0 ở ngày không giao dịch. Tổng tháng là tổng lượt khách giao dịch theo ngày; cùng khách ở hai ngày được tính hai lượt. Không phải số khách duy nhất trong tháng hay lượt ghé thăm không mua hàng.

## Tham số tái lập

- 2.000 kịch bản; seed 2026; dự báo 12 tháng sau cuối tháng lịch sử.
- Lấy mẫu có hoàn lại theo tháng trong năm và thứ. Nếu nhóm có dưới 4 quan sát, dùng nhóm cùng thứ trong toàn bộ lịch sử.
- Lịch sử phải liên tục, không trùng ngày, có ít nhất 28 ngày; giá trị nguyên không âm.
- Tổng hợp từng đường mô phỏng theo tháng rồi tính mean và quantile 10%/90%. Không cộng các quantile ngày để suy ra quantile tháng.

## Sửa test

history.iloc[1:] còn 91 ngày liên tục nên hợp lệ. Đã thay kỳ vọng sai bằng hai trường hợp thực sự không hợp lệ: dưới 28 ngày hoặc thiếu ngày giữa chuỗi. Thêm kiểm tra chấp nhận lịch sử 91 ngày, fallback thiếu mùa và cách đếm tổng lượt theo ngày. Không thay đổi thuật toán hoặc các giá trị dự báo đã công bố.

## Kiểm định ngoài mẫu

Giữ cố định tham số, dùng hai mốc dự báo 12 tháng: huấn luyện 2011–2012/kiểm tra 2013 và huấn luyện 2011–2013/kiểm tra 2014. Chỉ dữ liệu trước mốc dự báo được dùng tạo nhóm lấy mẫu. Đối chứng: tổng lượt cùng tháng năm trước.

| Tập kiểm tra | WAPE Monte Carlo | WAPE đối chứng | Bias Monte Carlo | Tỷ lệ tháng trong P10–P90 |
|---|---:|---:|---:|---:|
| 2013 | 27.58% | 20.42% | -27.58% | 0.00% |
| 2014 | 36.52% | 22.39% | -36.52% | 0.00% |
| pooled | 32.61% | 21.53% | -32.61% | 0.00% |

Monte Carlo có WAPE cao hơn đối chứng trong phép kiểm tra này; không nên giới thiệu mô phỏng như mô hình dự báo đã chứng minh tốt hơn phương pháp đơn giản.
Dải P10–P90 là dải kịch bản tham khảo, chưa được hiệu chỉnh thành khoảng dự báo. Mô hình không ngoại suy xu hướng tăng trưởng và không mô hình hóa phụ thuộc giữa các ngày. Hai tập kiểm tra chỉ có tổng cộng 24 tháng; chưa đủ để kết luận khả năng áp dụng rộng.

## Tái lập năm 2015

Tổng dự kiến 6389.2775 lượt, trung bình 532.4398 lượt/tháng; tháng cao nhất 2015-12-01. Đây là mô phỏng tham khảo vì không có dữ liệu thực tế 2015 để đánh giá.

## Tệp bằng chứng và lệnh chạy

- `results/monte_carlo/evaluation.json`: cấu hình, giao thức và chỉ số.
- `results/monte_carlo/backtest_monthly.csv`: actual/predicted/baseline/dải của 24 tháng.
- `results/monte_carlo/forecast_2015_monthly.csv`: kết quả 12 tháng.
- `evidence/monte-carlo-tests-final.log`: log unit test sau sửa.

```powershell
& .runtime/forecast-venv/Scripts/python.exe -X utf8 -m unittest discover -s src/dashboard -p test_daily_customers.py -v
& .runtime/forecast-venv/Scripts/python.exe -X utf8 tools/evaluate_monte_carlo.py
```

Nội dung này là phần bổ sung báo cáo CV04. Khi hoàn thiện báo cáo PDF cuối ở CV05/CV11, cần đưa tham số, bảng kết quả và giới hạn trên vào phần Monte Carlo; việc sửa PDF gốc chưa thực hiện ở CV04.
