# 传感器实验报告

- `report.tex`：当前报告的 LaTeX 源文件。
- `传感器实验报告_简洁版.pdf`：与当前源文件对应的报告。
- `传感器实验报告.pdf`：之前的报告版本。
- `figures/`：报告使用的图，`plot_figures.py` 和 `plot_gray_light.py` 可重新生成配图。

在此目录中编译报告：

```powershell
xelatex report.tex
```

重新运行 `plot_figures.py` 会重新生成原有配图；`plot_gray_light.py` 单独生成表 8 的灰度光照曲线。
