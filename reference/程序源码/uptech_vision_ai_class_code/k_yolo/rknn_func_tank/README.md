# k_yolo/rknn_func_tank

车辆类别检测的推理辅助代码。

| 文件或目录 | 功能 |
|---|---|
| [func.py](<func.py>) | 车辆类别定义及检测结果解码、过滤和绘制。 |
| [rknnpool.py](<rknnpool.py>) | 创建 RKNN 推理实例并用线程池调度图像推理。 |

类别包括 civilian_vehicle、field_ambulance、infantry_fighting_vehicle 和 tank。

