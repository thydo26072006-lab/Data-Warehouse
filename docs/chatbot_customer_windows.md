# Bổ sung đối chiếu báo cáo và chatbot quy tắc

Phụ lục ngày 15/11/2026 cho phần KPI khách hàng trong báo cáo. Bản PDF và
bộ bằng chứng nghiệm thu trước đó được giữ nguyên; kết quả kiểm thử cho phần
bổ sung này nằm riêng tại `evidence/chatbot-windows/`.

Chatbot quy tắc nay dùng cùng `insights.customer_window` với chế độ Gemini
cho câu hỏi về khách mới, quay lại, hoạt động, không hoạt động và mua lặp.

| Câu hỏi mẫu | Khoảng tính khi sidebar chọn toàn bộ dữ liệu |
| --- | --- |
| Khách hàng quay lại trong 3 tháng? | 01/10/2014–31/12/2014 |
| Khách hàng quay lại trong 6 tháng? | 01/07/2014–31/12/2014 |
| Khách hàng quay lại trong 12 tháng? | 01/01/2014–31/12/2014 |
| Tỷ lệ khách hàng quay lại là bao nhiêu? | Mặc định 12 tháng: 01/01/2014–31/12/2014 |

Năm được hỏi được áp dụng trước khi tính cửa sổ. Cửa sổ kết thúc tại cuối kỳ
đang chọn, không mở rộng trước ngày bắt đầu sidebar. Câu trả lời nêu cả độ dài
cửa sổ yêu cầu và khoảng ngày thực tế, nên bộ lọc ngắn hơn 12 tháng không bị
diễn giải là đủ 12 tháng dữ liệu.

Lịch sử mua trước cửa sổ vẫn được truy vấn trong phạm vi thị trường/ngành hàng
đang chọn để nhận diện khách mới và quay lại. KPI chỉ tính trong cửa sổ thực
tế. Khách không hoạt động vẫn là chỉ số đại diện, không kết luận rời bỏ.
Câu hỏi có số tháng không thuộc 3/6/12 hoặc có nhiều số tháng khác nhau được
yêu cầu chọn lại, không âm thầm đổi sang kỳ mặc định.

Để tuân thủ yêu cầu chỉ bổ sung, các dòng mã cũ được giữ nguyên. Một nhánh
được thêm trước nhánh KPI cũ để xử lý câu hỏi bằng hàm mới; nhánh cũ không còn
được gọi cho các câu hỏi đó. Quy tắc bảo vệ, giới hạn năm và định tuyến các
câu hỏi phân khúc, OLAP khác vẫn chạy theo luồng hiện có.

Kiểm thử bổ sung:

```powershell
python -B src/dashboard/test_chatbot_windows.py
python -B src/dashboard/check_dashboard.py
```

Bộ thứ nhất kiểm tra các kỳ khác nhau bằng dữ liệu có kiểm soát, lịch sử trước
kỳ, mặc định 12 tháng, giao với sidebar/năm, dữ liệu rỗng, kỳ không hợp lệ và
định tuyến. Bộ thứ hai kiểm tra hồi quy Dashboard với PostgreSQL cục bộ.
Manifest mới ghi hash mã nguồn và log; manifest cũ vẫn mô tả commit đã được
nghiệm thu trước khi có phần bổ sung này.
