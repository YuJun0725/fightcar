"""视觉配置独立于 robot.json；未知的标定量必须保留为 None。"""

from copy import deepcopy
import json
import math
from pathlib import Path


FAMILIES = ("tag16h5", "tag25h9", "tag36h10", "tag36h11")
TAG_COUNTS = dict(zip(FAMILIES, (30, 35, 2320, 587)))

POSITION_FILTER_DEFAULTS = {
    "enabled": False, "method": "ema", "alpha": 0.6,
    "window": 3, "reset_after_s": 0.3,
}
MULTI_TAG_FUSION_DEFAULTS = {
    "enabled": False, "min_tags": 2, "max_spread_m": 0.08,
    "fallback_to_single": True, "blocks": [], "same_id_max_spread_m": None,
}


def default_path():
    root = Path(__file__).resolve().parents[2]
    deployed = root / "config" / "vision.json"
    return deployed if deployed.is_file() else root.parent / "config" / "vision.json"


def _keys(value, names, label, optional=""):
    required = set(names.split())
    allowed = required | set(optional.split())
    if not isinstance(value, dict) or not required <= set(value) or not set(value) <= allowed:
        raise ValueError(label + " 必填字段：" + names + ("；可选字段：" + optional if optional else ""))


def _number(value, label, positive=False):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or (positive and value <= 0)):
        raise ValueError(label + (" 必须为有限正数" if positive else " 必须为有限数值"))


def _integer(value, label, minimum=1):
    if type(value) is not int or value < minimum:
        raise ValueError(label + " 必须为不小于 {} 的整数".format(minimum))


def _vector(value, lengths, label):
    if not isinstance(value, (list, tuple)) or len(value) not in lengths:
        raise ValueError(label + " 长度应为 " + str(lengths))
    for item in value:
        _number(item, label)


def _section(config, key, defaults):
    if not isinstance(config, dict):
        raise ValueError("vision 配置必须是对象")
    values = config.get(key, {})
    _keys(values, "", key, " ".join(defaults))
    merged = deepcopy(defaults)
    merged.update(deepcopy(values))
    return merged


def _boolean(value, label):
    if type(value) is not bool:
        raise ValueError(label + " 必须为 true 或 false")


def position_filter_config(config):
    """旧配置缺少此段时关闭滤波；合并默认值不修改调用者的配置。"""
    options = _section(config, "position_filter", POSITION_FILTER_DEFAULTS)
    _boolean(options["enabled"], "position_filter.enabled")
    if options["method"] not in ("ema", "mean", "median"):
        raise ValueError("position_filter.method 应为 ema、mean 或 median")
    _number(options["alpha"], "position_filter.alpha", positive=True)
    if options["alpha"] > 1:
        raise ValueError("position_filter.alpha 应不大于 1")
    _integer(options["window"], "position_filter.window")
    if options["window"] > 31 or (options["method"] == "median" and options["window"] % 2 == 0):
        raise ValueError("position_filter.window 应为 1～31；median 必须为奇数")
    _number(options["reset_after_s"], "position_filter.reset_after_s", positive=True)
    return options


def multi_tag_fusion_config(config):
    """每个标签只能属于一个方块；安装偏移以该标签自身坐标系、米为单位。"""
    options = _section(config, "multi_tag_fusion", MULTI_TAG_FUSION_DEFAULTS)
    _boolean(options["enabled"], "multi_tag_fusion.enabled")
    _boolean(options["fallback_to_single"], "multi_tag_fusion.fallback_to_single")
    _integer(options["min_tags"], "multi_tag_fusion.min_tags", minimum=2)
    if options["min_tags"] > 6:
        raise ValueError("multi_tag_fusion.min_tags 应为 2～6")
    _number(options["max_spread_m"], "multi_tag_fusion.max_spread_m", positive=True)
    if options["same_id_max_spread_m"] is not None:
        _number(options["same_id_max_spread_m"], "multi_tag_fusion.same_id_max_spread_m",
                positive=True)
    blocks = options["blocks"]
    if not isinstance(blocks, list):
        raise ValueError("multi_tag_fusion.blocks 必须为数组")
    if options["enabled"] and not blocks:
        raise ValueError("开启多标签融合前，请先配置 multi_tag_fusion.blocks 的标签归属和中心偏移")
    family = config.get("family")
    if family not in FAMILIES:
        raise ValueError("不支持的 AprilTag family：" + str(family))
    block_ids, tag_ids = set(), set()
    for index, block in enumerate(blocks):
        label = "multi_tag_fusion.blocks[{}]".format(index)
        _keys(block, "block_id tags", label)
        block_id = block["block_id"]
        if not isinstance(block_id, str) or not block_id.strip():
            raise ValueError(label + ".block_id 必须为非空字符串")
        if block_id in block_ids:
            raise ValueError("重复的 block_id：" + block_id)
        block_ids.add(block_id)
        tags = block["tags"]
        if not isinstance(tags, list) or not 1 <= len(tags) <= 6:
            raise ValueError(label + ".tags 应含 1～6 个标签")
        for tag in tags:
            _keys(tag, "id center_offset_m", label + ".tags")
            tag_id = tag["id"]
            _integer(tag_id, label + ".tags.id", minimum=0)
            if tag_id >= TAG_COUNTS[family]:
                raise ValueError("{} 的标签 ID 应为 0～{}".format(family, TAG_COUNTS[family] - 1))
            if tag_id in tag_ids:
                raise ValueError("标签 ID {} 重复，不能分配给多个面或方块".format(tag_id))
            tag_ids.add(tag_id)
            _vector(tag["center_offset_m"], (3,), label + ".tags.center_offset_m")
    return options


def validate_config(config):
    _keys(config, "schema_version family tag_size_m block_center_offset_m camera detector", "vision",
          "position_filter multi_tag_fusion")
    if type(config["schema_version"]) is not int or config["schema_version"] != 1:
        raise ValueError("仅支持 vision schema_version=1")
    if config["family"] not in FAMILIES:
        raise ValueError("不支持的 AprilTag family：" + str(config["family"]))
    if config["tag_size_m"] is not None:
        _number(config["tag_size_m"], "tag_size_m", positive=True)
    if config["block_center_offset_m"] is not None:
        _vector(config["block_center_offset_m"], (3,), "block_center_offset_m")

    camera = config["camera"]
    _keys(camera, "source width height fps calibration", "camera")
    source = camera["source"]
    if not ((type(source) is int and source >= 0) or (isinstance(source, str) and source.strip())):
        raise ValueError("camera.source 应为非负相机编号或设备/视频路径")
    for key in ("width", "height"):
        _integer(camera[key], "camera." + key)
    _number(camera["fps"], "camera.fps", positive=True)

    calibration = camera["calibration"]
    if calibration is not None:
        _keys(calibration, "image_size camera_matrix dist_coeffs", "camera.calibration")
        size = calibration["image_size"]
        if not isinstance(size, (list, tuple)) or len(size) != 2:
            raise ValueError("calibration.image_size 应为 [宽, 高]")
        for item in size:
            _integer(item, "calibration.image_size")
        matrix = calibration["camera_matrix"]
        if not isinstance(matrix, (list, tuple)) or len(matrix) != 3:
            raise ValueError("camera_matrix 必须是 3×3 矩阵")
        for row in matrix:
            _vector(row, (3,), "camera_matrix")
        if (matrix[0][0] <= 0 or matrix[1][1] <= 0
                or matrix[0][1] != 0 or matrix[1][0] != 0
                or list(matrix[2]) != [0, 0, 1]):
            raise ValueError("camera_matrix 应为 [[fx,0,cx],[0,fy,cy],[0,0,1]]，fx/fy>0")
        _vector(calibration["dist_coeffs"], (4, 5, 8, 12, 14), "dist_coeffs")

    detector = config["detector"]
    _keys(detector, "opencv_threads max_reprojection_error_px", "detector")
    _integer(detector["opencv_threads"], "opencv_threads")
    _number(detector["max_reprojection_error_px"], "max_reprojection_error_px", positive=True)
    position_filter_config(config)
    multi_tag_fusion_config(config)


def load_config(path=None):
    path = Path(path) if path is not None else default_path()
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    validate_config(config)
    return config
