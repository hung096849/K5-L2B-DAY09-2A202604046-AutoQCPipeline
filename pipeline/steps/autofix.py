"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict  # noqa: F401

import yaml  # noqa: F401

from ..common import ERROR, parse_yolo_line  # noqa: F401


DROP_CODES = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
REMOVE_CODES = {"LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}


def _is_remove(code):
    return code in REMOVE_CODES or code.startswith("DUP_IMAGE_")


def _clip(raw):
    """Cắt box về [0,1]. Trả về dòng mới, hoặc None nếu box không còn diện tích / dòng không đọc được."""
    try:
        cls, x, y, w, h = parse_yolo_line(raw)
    except ValueError:
        return None
    x1, x2 = max(0.0, x - w / 2), min(1.0, x + w / 2)
    y1, y2 = max(0.0, y - h / 2), min(1.0, y + h / 2)
    nw, nh = x2 - x1, y2 - y1
    if nw <= 0 or nh <= 0:
        return None
    return f"{int(cls)} {(x1 + x2) / 2:.6f} {(y1 + y2) / 2:.6f} {nw:.6f} {nh:.6f}"


def fix(ds, issues, cfg):
    fixes = []
    errs = [i for i in issues if i.severity == ERROR]

    # 1. Xoá ảnh (mỗi ảnh một fix), nhớ lại để bỏ qua các issue khác của ảnh đó
    removed = set()
    for stem in sorted({i.image for i in errs if _is_remove(i.code)}):
        for p in [p for p in ds.image_files() if p.stem == stem]:
            p.unlink()
            lab = ds.label_path(stem)
            if lab.exists():
                lab.unlink()
            fixes.append({"image": stem, "line": None, "action": "remove_image",
                          "before": p.name, "after": "(đã xoá)"})
            removed.add(stem)

    # 2. Thiếu file nhãn: KHÔNG tạo file, chỉ ghi để chuyển người gán
    for stem in sorted({i.image for i in errs if i.code == "MISSING_LABEL_FILE"} - removed):
        fixes.append({"image": stem, "line": None, "action": "needs_label",
                      "before": "(không có file)", "after": "chuyển người gán"})

    # 3. Tên lớp trong data.yaml
    if any(i.code == "BAD_CLASS_NAME" for i in errs):
        yp = getattr(ds, "yaml_path", None) or (ds.root / "data.yaml")
        data = yaml.safe_load(yp.read_text()) or {}
        before = data.get("names")
        data["names"] = list(cfg["classes"])
        yp.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
        fixes.append({"image": "data.yaml", "line": None, "action": "rename_classes",
                      "before": str(before), "after": str(data["names"])})

    # 4. Sửa dòng nhãn: gom theo file, dùng số dòng GỐC, ghi lại MỘT lần
    by_stem = defaultdict(lambda: defaultdict(set))   # stem -> số dòng -> tập mã lỗi
    for i in errs:
        if i.line is not None and i.image not in removed and (
                i.code in DROP_CODES or i.code == "BOX_OUT_OF_IMAGE"):
            by_stem[i.image][i.line].add(i.code)

    for stem in sorted(by_stem):
        path = ds.label_path(stem)
        if not path.exists():
            continue
        old = path.read_text().splitlines()
        new = []
        for n, raw in enumerate(old, start=1):
            codes = by_stem[stem].get(n)
            if not codes:
                new.append(raw)
                continue
            if codes & DROP_CODES:                       # xoá thắng clip
                fixes.append({"image": stem, "line": n, "action": "drop_line",
                              "before": raw, "after": "(đã xoá)"})
                continue
            clipped = _clip(raw)                         # chỉ còn BOX_OUT_OF_IMAGE
            if clipped is None:
                fixes.append({"image": stem, "line": n, "action": "drop_line",
                              "before": raw, "after": "(đã xoá)"})
            else:
                new.append(clipped)
                fixes.append({"image": stem, "line": n, "action": "clip_box",
                              "before": raw, "after": clipped})
        if new != old:
            path.write_text("\n".join(new) + ("\n" if new else ""))
    return fixes