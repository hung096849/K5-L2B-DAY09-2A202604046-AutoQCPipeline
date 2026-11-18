"""CHECK 6 — Ý kiến thứ hai: so nhãn với một model LỚN HƠN (yolo26l).   ★★★ (khó nhất, đáng điểm nhất)

Test:  pytest tests/test_second_opinion.py -q

Máy kiểm quy tắc, người kiểm ý nghĩa (slide). Các lỗi như thiếu nhãn / gán nhầm lớp hợp lệ / box lỏng
KHÔNG bắt được bằng quy tắc cú pháp. Ta nhờ một model mạnh hơn "nhìn lại" và CHỈ CẢNH BÁO (model cũng có thể sai):
những ảnh bị cờ sẽ vào hàng đợi cho NGƯỜI duyệt.

`preds[stem]` = list `[id_lớp, conf, cx, cy, w, h]` của model (lấy qua `get_preds(ds, cfg, "checker")` nếu preds=None).
`L = ds.valid_boxes(stem)` = list `(id_lớp, cx, cy, w, h)` của nhãn (đã bỏ dòng hỏng).
Ngưỡng ở `cfg["second_opinion"]`: conf, min_area_px, fp_conf, iou_missing, iou_match, iou_loose.

Thuật toán gợi ý, với từng ảnh (bỏ qua ảnh không có trong preds hoặc không có file nhãn):
  P = dự đoán có conf >= conf  VÀ diện tích px (w*W * h*H) >= min_area_px
  Với mỗi dự đoán r trong P: lấy các nhãn có IoU(r, nhãn) >= iou_missing  (cands)
   - không có cands                            -> POSSIBLE_MISSING     (model thấy vật mà nhãn không có box)
   - có cands cùng lớp, tốt nhất IoU < iou_loose -> POSSIBLE_LOOSE_BOX  (đúng vật, box lỏng/lệch)
   - không có cands cùng lớp, nhưng cands tốt nhất IoU >= iou_match (khác lớp) -> POSSIBLE_WRONG_CLASS
  Với mỗi dòng nhãn hợp lệ: nếu IoU với MỌI dự đoán (conf >= fp_conf, không lọc diện tích) đều < iou_missing
                                             -> POSSIBLE_FALSE_POS  (box nhãn không khớp vật nào model thấy; Issue.line = số dòng)

Chi tiết các ca biên (test kiểm đúng các ca này)
- `cands` gồm nhãn MỌI lớp có IoU >= iou_missing; "tốt nhất cùng lớp" = cands cùng lớp có IoU lớn nhất; "tốt nhất khác lớp" tương tự với cands khác lớp.
- Thứ tự quyết định cho mỗi dự đoán: (1) cands rỗng -> MISSING. (2) có cands cùng lớp: IoU tốt nhất < iou_loose -> LOOSE_BOX, ngược lại KHÔNG cờ
  (nhãn đúng lớp đã phủ vật này, kể cả khi còn nhãn khác lớp chồng lên). (3) không có cands cùng lớp: nếu IoU tốt nhất khác lớp >= iou_match -> WRONG_CLASS;
  nếu chỉ có khác lớp với IoU trong [iou_missing, iou_match) -> không cờ gì (mơ hồ: để cho FALSE_POS / lần duyệt khác).
- Một dự đoán sinh tối đa MỘT issue (MISSING / LOOSE_BOX / WRONG_CLASS); một ảnh có thể có nhiều issue.
- Thứ tự issue: theo `ds.image_files()` rồi theo thứ tự dự đoán trong `preds[stem]`, cuối cùng là các FALSE_POS theo số dòng; `Issue.image` = stem, `Issue.line` chỉ đặt cho FALSE_POS.

Lưu ý số dòng: dùng `ds.read_label_lines(stem)` (giữ số dòng gốc, kể cả dòng hỏng/trống) để lấy `Issue.line`; `valid_boxes` KHÔNG giữ số dòng.

Tất cả severity WARN; `Issue.extra` nên có {"conf": ...} hoặc {"iou": ...} (hàng đợi duyệt dùng conf để xếp ưu tiên).

Gợi ý
- `iou_xywh` có sẵn. Dòng nhãn hỏng không được làm script chết (dùng `ds.valid_boxes` và `parse_yolo_line` trong try).
- Kết quả phụ thuộc mạnh vào ngưỡng: calibrate chúng ở Bước 3 thay vì đoán.
"""
from ..common import WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401
from ..model_cache import get_preds  # noqa: F401


def _labels_with_lines(ds, stem):
    """[(số dòng gốc, cls, cx, cy, w, h)] của các dòng hợp lệ. Dòng trống/hỏng bị bỏ nhưng vẫn đếm số dòng."""
    out = []
    for n, raw in ds.read_label_lines(stem):
        if not raw.strip():
            continue
        try:
            cls, x, y, w, h = parse_yolo_line(raw)
        except ValueError:
            continue
        if not (0 <= int(cls) < len(ds.classes)) or w <= 0 or h <= 0:
            continue
        out.append((n, int(cls), x, y, w, h))
    return out


def run(ds, cfg, preds=None):
    c = cfg["second_opinion"]
    if preds is None:
        preds = get_preds(ds, cfg, "checker")
    issues = []

    for img in ds.image_files():
        stem = img.stem
        if stem not in preds or not ds.label_path(stem).exists():
            continue
        try:
            W, H = ds.image_size(stem)
        except Exception:
            continue                                   # ảnh hỏng: việc của check `images`

        labels = _labels_with_lines(ds, stem)
        P = [r for r in preds[stem]
             if r[1] >= c["conf"] and (r[4] * W) * (r[5] * H) >= c["min_area_px"]]

        # 1. Mỗi dự đoán sinh tối đa MỘT issue
        for r in P:
            rcls, rconf, rbox = int(r[0]), r[1], tuple(r[2:6])
            cands = []                                 # (iou, lớp nhãn)
            for _, lcls, x, y, w, h in labels:
                iou = iou_xywh(rbox, (x, y, w, h))
                if iou >= c["iou_missing"]:
                    cands.append((iou, lcls))

            if not cands:
                issues.append(Issue("second_opinion", WARN, "POSSIBLE_MISSING", stem,
                                    f"model thấy lớp {rcls} (conf {rconf:.2f}) mà nhãn không có box",
                                    None, {"conf": rconf}))
                continue
            same = [i for i, lc in cands if lc == rcls]
            if same:
                best = max(same)
                if best < c["iou_loose"]:
                    issues.append(Issue("second_opinion", WARN, "POSSIBLE_LOOSE_BOX", stem,
                                        f"box đúng lớp nhưng lỏng/lệch (IoU {best:.2f})",
                                        None, {"conf": rconf, "iou": best}))
                continue                               # nhãn đúng lớp đã phủ vật này
            best_other = max(i for i, _ in cands)
            if best_other >= c["iou_match"]:
                issues.append(Issue("second_opinion", WARN, "POSSIBLE_WRONG_CLASS", stem,
                                    f"model nói lớp {rcls} (conf {rconf:.2f}), nhãn khác lớp (IoU {best_other:.2f})",
                                    None, {"conf": rconf, "iou": best_other}))
            # còn lại: mơ hồ, không cờ

        # 2. FALSE_POS: dùng fp_conf, KHÔNG lọc diện tích
        fp_preds = [r for r in preds[stem] if r[1] >= c["fp_conf"]]
        for n, lcls, x, y, w, h in labels:
            if all(iou_xywh(tuple(r[2:6]), (x, y, w, h)) < c["iou_missing"] for r in fp_preds):
                issues.append(Issue("second_opinion", WARN, "POSSIBLE_FALSE_POS", stem,
                                    f"box nhãn dòng {n} không khớp vật nào model thấy",
                                    n, {"iou": 0.0}))
    return issues