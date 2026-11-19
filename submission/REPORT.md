# Báo cáo Day 09 — Hoàng Mạnh Hùng, 2A202604046

## 1. Kết luận trước
**Hold.** Lô 224 ảnh qua intake còn 203 ảnh (loại 21), xuất **bản nháp** 203 ảnh (chưa phát hành). Không còn lỗi bắt buộc (n_errors = 0 ở v3), nhưng 38/203 ảnh (18,7%) còn cảnh báo, vượt ngưỡng 10%. Ngân sách người duyệt 80 ảnh không đủ cho hàng đợi 125 ảnh.

## 2. Lỗi và phân việc
Số liệu từ `02_error_list_v1` (đếm issue/dòng). Mẫu số: 224 ảnh cho lỗi intake, 203 ảnh cho các lỗi còn lại.

| Mã lỗi | Số | Ai sửa | Vì sao |
|---|---:|---|---|
| DUP_IMAGE_EXACT / DUP_IMAGE_NEAR / LEAK_TEST | 8 / 3 / 5 (/224) | máy (loại ở intake) | quy tắc rõ, xoá ảnh |
| CORRUPT_IMAGE / BAD_SIZE | 2 / 3 (/224) | máy (loại ở intake) | ảnh không dùng được |
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX | 3, 6, 4, 7 (/203) | máy (20 `drop_line`) | lỗi cú pháp, xoá dòng |
| BOX_OUT_OF_IMAGE | 8 (/203) | máy (8 `clip_box`) | cắt box về [0,1] |
| BAD_CLASS_NAME | 2 (/203) | máy (1 `rename_classes`) | ghi lại `names` theo cấu hình |
| MISSING_LABEL_FILE | 6 (/203) | người (6 `needs_label`) | máy không được bịa nhãn |
| POSSIBLE_MISSING / LOOSE_BOX / FALSE_POS / WRONG_CLASS | 53 / 28 / 25 / 18 (/203) | người | lỗi ý nghĩa, model chỉ cảnh báo |
| EMPTY_LABEL, BOX_TINY, BOX_HUGE, CLASS_RARE | 12, 6, 3, 4 (/203) | người | cảnh báo |

Hàng đợi `05_review_queue.csv` (125 ảnh) xếp ưu tiên: ảnh thiếu file nhãn (`NEEDS_LABEL`, 10,0) trước vì không có nhãn thì không dùng được; rồi ảnh vừa bị máy xoá dòng và có cảnh báo conf cao của model (đầu hàng là `img_0020`, 11,5). Người xem được 80/125 ảnh, 45 ảnh không ai xem. Cảnh báo ý nghĩa giảm từ 123 (v2) xuống 57 (v3).

## 3. Calibration (2 ngưỡng)
Calib: 39 ảnh có đáp án lỗi chèn sẵn (`DUP_IMAGE_NEAR`: 6 cặp, `POSSIBLE_MISSING`: 8, `POSSIBLE_WRONG_CLASS`: 6, `POSSIBLE_LOOSE_BOX`: 5). "Trước" là cấu hình khởi đầu, "sau" là giá trị đã chọn (nguồn: `submission/calibration/calibration_report.md`).

| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | **8** | NEAR: 1.00 / 0.50 → 1.00 / 0.67. EXACT: 1.00 / 1.00 → 1.00 / 1.00 | Từ 4 đến 14 là cao nguyên, chọn giữa vùng phẳng cho ổn định. Ở 2, recall NEAR chỉ 0.50. Không chọn 16 (F1 0.91) vì sát vực: ở 20 recall EXACT rơi xuống 0.33, và xoá nhầm ảnh là mất dữ liệu thật. |
| `second_opinion.conf` | 0.25 | **0.6** | MISSING: 0.50 / 1.00 → 0.57 / 1.00. WRONG_CLASS: 0.56 / 0.83 → 0.62 / 0.83. LOOSE_BOX: 0.29 / 0.40 → 0.20 / 0.20 (kém đi). FALSE_POS: 0.36 / 1.00, không đổi | 0.6 là mức cao nhất mà MISSING còn giữ recall 1.00, precision tăng nên hàng đợi bớt báo động giả. Ở 0.7 MISSING mất 1 ca (R 0.88) mà precision chỉ +0.01; ở 0.8 mất 2/8 ca. Cái giá: LOOSE_BOX còn 0.20 / 0.20. `POSSIBLE_FALSE_POS` dùng `fp_conf` cố định nên không phụ thuộc `conf`. |

**Một chỗ calibration có thể đánh lừa bạn.** Với `phash_dist`, giá trị 16 có F1 cao nhất (NEAR 0.91), nhưng mức tăng recall 0.67 lên 0.83 chỉ là thêm **1 cặp trên 6 cặp chèn**, tín hiệu quá mỏng. Precision 1.00 ở calib chỉ phản ánh 39 ảnh ít ảnh nào giống nhau tự nhiên. Tương tự, precision của `second_opinion` tính theo lỗi được chèn, trong khi ảnh COCO gốc có sai sót thật mà model lớn có thể bắt đúng, nên precision thật có thể cao hơn bảng.

**Bằng chứng trên raw sau `make run`:** `01_intake` loại 3/224 ảnh `DUP_IMAGE_NEAR` (img_0076, img_0143 có phash 0; img_0223 phash 6). Chỉ cặp `img_0223` / `img_0077` thật sự phụ thuộc ngưỡng (ngưỡng khởi đầu 2 sẽ bỏ sót); tôi đã mở xem, đây là cùng một cảnh nên loại là đúng. Hai cặp còn lại ngưỡng nào cũng bắt. Hạn chế: raw không có cặp "gần trùng nhưng khác cảnh" trong khoảng phash 3–8, nên **chưa kiểm được precision của ngưỡng 8 trên dữ liệu thật**.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được
**(a) Cổng chặn thật sự chặn.** Chạy `python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb` (không có người duyệt): vòng 2 còn 6 lỗi bắt buộc (6 ảnh `MISSING_LABEL_FILE`, máy không bịa nhãn), kết luận **Rework**, mã thoát **20**, log ghi "KHÔNG xuất: còn lỗi bắt buộc", và `work/exp_nb` **không được tạo**. Với ngân sách 80 ảnh thì người gán nhãn các ảnh đó, lỗi bắt buộc về 0 và kết luận là Hold.

**Ba lỗi tự quan sát ở Bước 1 và cách pipeline xử lý:**

| Ảnh | Quan sát bằng mắt | Pipeline |
|---|---|---|
| `img_0010` | Không mở được ảnh (`UnidentifiedImageError`) | `CORRUPT_IMAGE` (check `images`), loại ở intake |
| `img_0050` | Box thành một đường thẳng | `BOX_ZERO` dòng 1 (`label_format`), máy `drop_line`; sau đó `POSSIBLE_MISSING` (conf 0,93); người duyệt thay bằng nhãn người |
| `img_0020` | Box đen, không có tên nhãn | `BAD_CLASS_ID` dòng 3, id 93 (`label_format`), máy `drop_line`; sau đó `POSSIBLE_MISSING` (conf 0,84) và `POSSIBLE_WRONG_CLASS` (model nói lớp 3, conf 0,95); người duyệt thay bằng nhãn người |

**(b) Điểm mù (có bằng chứng):**
1. **Máy xoá nhãn thật khi sửa lỗi cú pháp.** `img_0050` và `img_0020` mất nhãn người sau `drop_line`; máy không khôi phục được, chỉ cảnh báo `POSSIBLE_MISSING` để người gán lại. `EMPTY_LABEL` tăng từ 12 (v1) lên 15 (v2): 3 ảnh (img_0050, img_0104, img_0194) bị rỗng vì autofix xoá hết dòng của file (kiểm bằng so danh sách EMPTY_LABEL v1 và v2). Máy không phân biệt được "ảnh nền" với "mất nhãn", nên các ảnh này phải do người xem lại.
2. **Box lỏng gần như không bắt được.** `POSSIBLE_LOOSE_BOX` ở calib chỉ đạt P 0,20 / R 0,20 tại conf 0,6, và v3 vẫn còn 20 ảnh cảnh báo loại này.
3. **45/125 ảnh trong hàng đợi không ai xem** (ngân sách 80), nên cảnh báo ý nghĩa trên các ảnh đó vẫn nằm trong 38/203 ảnh còn cảnh báo.

## 5. Train: raw vs clean (tùy chọn, chấm riêng)
Chưa chạy. Lý do: phần train Colab là tùy chọn, chấm riêng; em ưu tiên hoàn thiện pipeline, calibration và báo cáo lỗi. Vì vậy không có kết luận nào về việc clean tốt hơn raw.

## 6. Quyết định và ghi chú AI
**(a) Quyết định cuối: Hold.** Không còn lỗi bắt buộc (n_errors = 0), nhưng 38/203 ảnh (18,7%) còn cảnh báo, vượt ngưỡng 10%. Dataset xuất ra chỉ là bản nháp, chưa phát hành.
Điều kiện để thành Release: giảm số ảnh còn cảnh báo xuống ≤ 20/203 (9,85%). Cách làm: người duyệt thêm 45 ảnh còn lại của hàng đợi (125 ảnh, mới duyệt 80), ưu tiên ảnh có `POSSIBLE_MISSING` và `POSSIBLE_WRONG_CLASS` conf cao; sau đó chạy lại pipeline và đối chiếu `07_error_list_v3`. Không hạ ngưỡng 10% để đạt Release.

**(b) Ghi chú AI.**
- Prompt chính: nhờ AI viết `gate.decide`, `autofix.fix`, `second_opinion.run` theo docstring và test; `label_format` em viết theo khung AI gợi ý.
- Cách kiểm: chạy pytest, đọc từng dòng, tự thử thêm ca biên, rồi đối chiếu lỗi thật qua `make run` và ảnh `viz_labels.py` (img_0020, img_0050).
- 1 lần AI sai: AI giả định `ds.read_label_lines` trả về list chuỗi, thực tế trả về cặp `(số dòng, nội dung)`; pytest báo `'tuple' object has no attribute 'strip'`, em đọc hàm gốc và sửa thành `for n, raw in ds.read_label_lines(stem):`.