"""鲁班猫 AprilTag 测距预览，浏览器通过 SSH 隧道读取画面和距离。"""

import argparse
import base64
from collections import deque
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import re
import sys
import threading
import time
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from .config import load_config, validate_config
from .pipeline import VisionPipeline


LOOPBACK = "127.0.0.1"
STALE_S = 2.5
CAMERA_RETRY_S = 1.0
PAGE = Path(__file__).with_name("web_preview.html")
RAW_PATH = re.compile(r"/raw/(checkerboard-[0-9A-Za-z-]{1,80}\.png)")


class PreviewState:
    """只持有同一帧的图像和测距结果，多个页面共用一次检测和编码。"""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.seq = 0
        self.stamp, self.frame, self.original = None, None, None
        self.target_stamp, self.targets = None, None
        self.failure = None

    def publish_targets(self, payload, stamp):
        with self.lock:
            self.target_stamp = stamp
            self.targets = json_bytes(dict(payload, state="live", timestamp_s=stamp))
            self.failure = None

    def read_targets(self):
        with self.lock:
            if self.failure is not None:
                return self.failure
            if self.targets is None:
                return json_bytes({"state": "waiting"})
            if self.clock() - self.target_stamp > STALE_S:
                return json_bytes({"state": "stale"})
            return self.targets

    def publish(self, payload, stamp, original):
        raw = original.copy()
        with self.lock:
            self.seq += 1
            self.frame = json_bytes(dict(payload, state="live", seq=self.seq))
            self.stamp = stamp
            self.original = raw
            self.failure = None

    def fail(self, message, *, reconnecting=False):
        with self.lock:
            self.failure = json_bytes({"state": "reconnecting" if reconnecting else "error",
                                       "message": message})
            self.stamp, self.frame, self.original = None, None, None
            self.target_stamp, self.targets = None, None

    def raw(self):
        with self.lock:
            if self.original is not None and self.clock() - self.stamp <= STALE_S:
                return self.seq, self.original
            return None

    def read(self, after):
        with self.lock:
            if self.failure is not None:
                return self.failure
            if self.frame is None:
                return json_bytes({"state": "waiting", "message": "等待第一帧"})
            if self.clock() - self.stamp > STALE_S:
                return json_bytes({"state": "stale", "message": "相机画面暂停，距离已清除"})
            return self.frame if self.seq != after else None


def json_bytes(data):
    return json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def start_server(state, port):
    page = PAGE.read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlsplit(self.path)
            download = RAW_PATH.fullmatch(path.path)
            if path.path == "/":
                self.reply(200, "text/html; charset=utf-8", page)
            elif path.path == "/api/frame":
                try:
                    after = int(parse_qs(path.query).get("after", ["0"])[0])
                except ValueError:
                    self.reply(400, "application/json", json_bytes({"error": "无效帧号"}))
                    return
                body = state.read(after)
                self.reply(204 if body is None else 200, "application/json; charset=utf-8", body or b"")
            elif path.path == "/api/targets":
                self.reply(200, "application/json; charset=utf-8", state.read_targets())
            elif path.path == "/raw.png" or download:
                raw = state.raw()
                if raw is None:
                    self.reply(503, "text/plain; charset=utf-8", "暂无新鲜相机原图".encode("utf-8"))
                    return
                from .apriltag import cv2
                seq, image = raw
                ok, encoded = cv2.imencode(".png", image, [cv2.IMWRITE_PNG_COMPRESSION, 1])
                if not ok:
                    self.reply(500, "text/plain; charset=utf-8", "原图编码失败".encode("utf-8"))
                    return
                name = (download.group(1) if download else
                        time.strftime("checkerboard-%Y%m%d-%H%M%S") + f"-{seq:06d}-{uuid4().hex[:8]}.png")
                self.reply(200, "image/png", encoded.tobytes(), filename=name)
            else:
                self.reply(404, "text/plain", b"Not found")

        def reply(self, code, kind, data, filename=None):
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            try:
                if data:
                    self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, format, *args):
            pass

    return ThreadingHTTPServer((LOOPBACK, port), Handler)


def block_targets(positions):
    """方块中心的欧氏距离以及光轴前向深度，统一用米。"""
    targets = []
    for point in positions:
        if point.kind != "block":
            continue
        xyz = point.position_m
        targets.append({
            "id": point.target_id, "tag_ids": point.tag_ids, "xyz_m": xyz,
            "distance_m": math.sqrt(sum(value * value for value in xyz)),
            "raw_distance_m": math.sqrt(sum(value * value for value in point.raw_position_m)),
            "forward_m": xyz[2],
        })
    return sorted(targets, key=lambda target: target["distance_m"])


def draw_block_centers(cv2, np, frame, targets, calibration):
    if not targets or calibration is None:
        return
    height, width = frame.shape[:2]
    positions = np.asarray([item["xyz_m"] for item in targets], dtype=float)
    projected, _ = cv2.projectPoints(positions, np.zeros(3), np.zeros(3),
                                     np.asarray(calibration["camera_matrix"], dtype=float),
                                     np.asarray(calibration["dist_coeffs"], dtype=float))
    for target, (x, y) in zip(targets, projected.reshape(-1, 2)):
        if not (0 <= x < width and 0 <= y < height):
            continue
        center = int(x), int(y)
        color = (0, 155, 255)
        cv2.drawMarker(frame, center, color, cv2.MARKER_TILTED_CROSS, 16, 2)
        cv2.putText(frame, f"Block {target['distance_m'] * 100:.1f} cm",
                    (max(4, center[0] - 45), min(height - 4, center[1] + 22)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, color, 2, cv2.LINE_AA)


def target_payload(result, config, pose_status):
    fusion = config.get("multi_tag_fusion", {})
    return {
        "family": config["family"], "pose_status": pose_status,
        "center_geometry": config["block_center_offset_m"] is not None or
        bool(fusion.get("enabled") and fusion.get("blocks")),
        "tags": [{"id": item.tag_id, "pose_status": item.pose_status} for item in result.detections],
        "blocks": block_targets(result.positions), "warnings": result.warnings,
    }


class PreviewRectifier:
    """缓存预览的去畸变映射，像素标注与画面使用同一套新内参。"""

    def __init__(self, calibration):
        from .apriltag import cv2, np

        size = tuple(calibration["image_size"])
        self.matrix = np.asarray(calibration["camera_matrix"], dtype=float)
        self.distortion = np.asarray(calibration["dist_coeffs"], dtype=float)
        corrected, _ = cv2.getOptimalNewCameraMatrix(self.matrix, self.distortion, size, 0)
        self.projection = {"camera_matrix": corrected, "dist_coeffs": np.zeros(5)}
        self.maps = cv2.initUndistortRectifyMap(self.matrix, self.distortion, None, corrected,
                                               size, cv2.CV_16SC2)

    def apply(self, frame, detections):
        from .apriltag import cv2, np

        image = cv2.remap(frame, *self.maps, cv2.INTER_LINEAR)
        if not detections:
            return image, detections
        pixels = np.asarray([(*item.corners_px, item.center_px) for item in detections], dtype=float)
        corrected = cv2.undistortPoints(pixels.reshape(-1, 1, 2), self.matrix, self.distortion,
                                        P=self.projection["camera_matrix"]).reshape(-1, 5, 2)
        annotations = [replace(item, corners_px=tuple(map(tuple, points[:4])), center_px=tuple(points[4]))
                       for item, points in zip(detections, corrected)]
        return image, annotations


def preview_payload(frame, result, config, pose_status, *, targets=None, rectifier=None):
    from .apriltag import annotate_frame, cv2, np

    started = time.monotonic()
    targets = target_payload(result, config, pose_status) if targets is None else targets
    calibration = config["camera"]["calibration"]
    detections = result.detections
    if rectifier is not None:
        frame, detections = rectifier.apply(frame, detections)
        calibration = rectifier.projection
    image = annotate_frame(frame, detections)
    draw_block_centers(cv2, np, image, targets["blocks"], calibration)
    height, width = image.shape[:2]
    if width > 640:
        image = cv2.resize(image, (640, max(1, round(height * 640 / width))), interpolation=cv2.INTER_AREA)
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 70])
    if not ok:
        raise OSError("无法编码预览画面")
    return {
        **targets,
        "jpeg": base64.b64encode(encoded).decode("ascii"), "jpeg_bytes": len(encoded),
        "image_size": [width, height],
        "undistorted": rectifier is not None,
        "preview_ms": (time.monotonic() - started) * 1000,
    }


class CameraUnavailable(RuntimeError):
    """打开设备或读取视频帧失败。"""


def preview_capture(cv2, pipeline, config, preview_fps, state, stopping, rectifier):
    camera = config["camera"]
    source = camera["source"]
    if isinstance(source, str) and source.startswith("/dev/") and not Path(source).exists():
        raise CameraUnavailable(f"相机设备未连接：{source}")
    capture = cv2.VideoCapture(source)
    try:
        if not capture.isOpened():
            raise CameraUnavailable(f"无法打开相机 {source}")
        width, height = (camera["calibration"]["image_size"] if camera["calibration"] else
                         (camera["width"], camera["height"]))
        for prop, value in ((cv2.CAP_PROP_FRAME_WIDTH, width), (cv2.CAP_PROP_FRAME_HEIGHT, height),
                            (cv2.CAP_PROP_FPS, camera["fps"]), (cv2.CAP_PROP_BUFFERSIZE, 1)):
            capture.set(prop, value)
        next_detection = next_preview = 0.0
        frame_times, preview_times = deque(maxlen=16), deque(maxlen=16)
        while not stopping.is_set():
            ok, frame = capture.read()
            stamp = time.monotonic()
            if not ok or frame is None:
                raise CameraUnavailable("相机读帧失败")
            if stamp < next_detection:
                continue
            next_detection = stamp + 0.9 / camera["fps"]
            result = pipeline.detect(frame, timestamp_s=stamp)
            targets = target_payload(result, config, pipeline.pose_status)
            state.publish_targets(targets, stamp)
            now = time.monotonic()
            detect_ms = (now - stamp) * 1000
            frame_times.append(stamp)
            if now < next_preview:
                continue
            next_preview = now + 1 / preview_fps
            preview_times.append(now)
            payload = preview_payload(frame, result, config, pipeline.pose_status,
                                      targets=targets, rectifier=rectifier)
            payload.update(detect_ms=detect_ms, detect_fps=rate(frame_times), preview_fps=rate(preview_times))
            state.publish(payload, stamp, frame)
    finally:
        capture.release()


def run_camera(config, preview_fps, state, stopping):
    try:
        from .apriltag import cv2

        cv2.setNumThreads(config["detector"]["opencv_threads"])
        pipeline = VisionPipeline(config)
        camera = config["camera"]
        calibration = camera["calibration"]
        rectifier = PreviewRectifier(calibration) if calibration is not None else None
        source = camera["source"]
        live_device = isinstance(source, int) or source.startswith("/dev/")
        while not stopping.is_set():
            try:
                preview_capture(cv2, pipeline, config, preview_fps, state, stopping, rectifier)
            except CameraUnavailable as error:
                if not live_device:
                    raise
                state.fail(f"{error}，正在尝试重新连接相机", reconnecting=True)
                pipeline.reset()
                stopping.wait(CAMERA_RETRY_S)
    except Exception as error:
        state.fail(str(error))
        print(f"相机预览失败：{error}", file=sys.stderr, flush=True)


def rate(stamps):
    return (len(stamps) - 1) / (stamps[-1] - stamps[0]) if len(stamps) > 1 and stamps[-1] > stamps[0] else None


def camera_config(args):
    config = load_config(args.config)
    if args.camera is not None:
        config["camera"]["source"] = args.camera
    source = config["camera"]["source"]
    if isinstance(source, str) and source.isdecimal():
        config["camera"]["source"] = int(source)
    if args.tag_size_m is not None:
        config["tag_size_m"] = args.tag_size_m
    if args.block_edge_m is not None:
        if not math.isfinite(args.block_edge_m) or args.block_edge_m <= 0:
            raise ValueError("--block-edge-m 必须为正的实测边长")
        config["block_center_offset_m"] = [0, 0, -args.block_edge_m / 2]
    validate_config(config)
    return config


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, help="默认为 config/vision.json")
    parser.add_argument("--camera", help="相机编号或设备路径，如 0 或 /dev/video0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--preview-fps", type=int, default=6, help="浏览器预览的帧率上限")
    parser.add_argument("--tag-size-m", type=float, help="AprilTag 黑框实测边长，单位米")
    parser.add_argument("--block-edge-m", type=float, help="立方体实测边长，标签贴在面中心时使用")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535 or not 1 <= args.preview_fps <= 20:
        parser.error("端口须在 1～65535，预览帧率须在 1～20")
    try:
        config = camera_config(args)
        state = PreviewState()
        stopping = threading.Event()
        with start_server(state, args.port) as server:
            worker = threading.Thread(target=run_camera, args=(config, args.preview_fps, state, stopping),
                                      daemon=True, name="camera-preview")
            worker.start()
            print(f"相机预览已启动：http://{LOOPBACK}:{args.port}，按 Ctrl+C 退出", flush=True)
            try:
                server.serve_forever(poll_interval=0.2)
            finally:
                stopping.set()
                worker.join(timeout=2)
        return 0
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"无法启动相机预览：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
