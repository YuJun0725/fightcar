# k_yolo/rknn_func

通用 YOLO 检测的推理辅助代码。

| 文件或目录 | 功能 |
|---|---|
| [func.py](<func.py>) | 图像预处理、输出框解码、阈值过滤、非极大值抑制及结果绘制；定义通用类别名称。 |
| [rknnpool.py](<rknnpool.py>) | 创建 RKNN 推理实例并用线程池调度图像推理。 |

