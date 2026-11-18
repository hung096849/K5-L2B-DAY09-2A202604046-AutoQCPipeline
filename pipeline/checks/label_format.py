"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401


def run(ds, cfg):
    c = cfg["label_format"]
    issues = []
    for stem in sorted(p.stem for p in ds.label_files()):
        size = ds.image_size(stem)       # None nếu ảnh hỏng
        kept = []                        # các box hợp lệ ở dòng trước, để tìm DUP_BOX
        text = (ds.labels_dir / f"{stem}.txt").read_text(encoding="utf-8", errors="replace")
        for n, raw in enumerate(text.splitlines(), start=1):
            if not raw.strip():
                continue                 # dòng trống: bỏ qua nhưng n vẫn tăng
            try:
                cls, x, y, w, h = parse_yolo_line(raw)
            except ValueError:
                issues.append(Issue("label_format", ERROR, "BAD_FORMAT", stem,
                                    "dòng không đúng 5 cột số", line=n))
                continue
            if cls < 0 or cls >= len(ds.classes):
                issues.append(Issue("label_format", ERROR, "BAD_CLASS_ID", stem,
                                    f"id lớp {cls} ngoài phạm vi", line=n))
                continue
            if w <= 0 or h <= 0:
                issues.append(Issue("label_format", ERROR, "BOX_ZERO", stem,
                                    "box có w hoặc h <= 0", line=n))
                continue
            overflow = max(-(x - w / 2), (x + w / 2) - 1, -(y - h / 2), (y + h / 2) - 1)
            if overflow > c["overflow_tol"]:
                issues.append(Issue("label_format", ERROR, "BOX_OUT_OF_IMAGE", stem,
                                    f"box tràn ảnh {overflow:.3f}", line=n,
                                    extra={"overflow": overflow}))
            for pcls, px, py, pw, ph in kept:
                if pcls == cls and iou_xywh((px, py, pw, ph), (x, y, w, h)) > c["dup_box_iou"]:
                    issues.append(Issue("label_format", ERROR, "DUP_BOX", stem,
                                        "box trùng với một dòng trước", line=n))
                    break
            if size is not None and min(w * size[0], h * size[1]) < c["min_box_px"]:
                issues.append(Issue("label_format", WARN, "BOX_TINY", stem,
                                    "box quá nhỏ", line=n))
            if w * h > c["max_box_frac"]:
                issues.append(Issue("label_format", WARN, "BOX_HUGE", stem,
                                    "box quá lớn", line=n))
            kept.append((cls, x, y, w, h))
    return issues