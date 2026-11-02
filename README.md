# WOT 涂装工作台 3.3 R1 / WOT Camouflage Workbench

[中文版](#中文版) | [English](#english)

## English

WOT Camouflage Workbench is a Windows desktop toolkit for creating World of Tanks camouflage, models, lighting and animated effects. Version 3.3 R1 includes 35 importable and exportable AE effect presets, animated previews, bilateral controls and optional classic or glass-style interface themes.

### Features

- **Camouflage:** search an index built from the selected client; combine colors, patterns, weathering and named image decals, or reuse a recipe. Generate resources and an optional `.wotmod`.
- **3D painting:** preview a stock vehicle or an existing single-vehicle camouflage, place images on a model surface, and adjust their position, size and angle.
- **Model editing:** create a Blender project for a selected part and LOD, edit its mesh and export with read-back checks. Other LODs require separate work.
- **Lighting:** open an existing camouflage or project in the light editor, select light surfaces, adjust colors and animation recipes, and preview the result.
- **AE effects:** import transparent animations or use 35 presets; position effects, fit them to armor, crop, scale and configure mirrored sides.
- **Validation and installation:** inspect output reports and hashes, install to the selected client with backups, and roll back using an installation record. File checks do not replace in-game testing.
### Download and run

Download the **3.3 R1 portable ZIP** from [Releases](https://github.com/shenshi258/wot-camouflage-workbench/releases), extract it to a writable folder, and run `启动wot涂装工作台 3.3.cmd`. The source repository does not include the portable Python runtime. The glass appearance uses colors and highlights; it does not provide real-time background blur or refraction.

### R1 changes

- Locks the AE tint-intensity slider and light-effect recovery controls during processing, restoring their previous states afterwards.
- Updates existing dropdown colors when switching themes.
- Retains all 35 presets and adds no changes to native effect assets in this revision.

### Validation

The existing release record reports background regression and isolated desktop UI checks. The original EU Pz70 camouflage was a **user-confirmed** working baseline. An offline generated sample was inspected, but complete in-game vehicle loading and visual effects have **not been tested** (`not_tested`). Check the actual game client and version before use, and verify loading, visibility and effects in game.

### Acknowledgements

Thanks to **コイカツ** and **GPT** for their help and support.

---

## 中文版

### 功能介绍

- **涂装制作：** 从所选客户端建立车型索引，组合颜色、图案、做旧和指定图片贴花，也可用配方再次生成；输出资源和可选 `.wotmod`。
- **三维贴图：** 预览原版车型或同车已有涂装，在模型表面放置图片并调整位置、大小和角度。
- **模型编辑：** 为选定部件和 LOD 创建 Blender 工程，编辑网格并导出回读检查；其他 LOD 需分别处理。
- **灯效制作：** 导入已有涂装或工程，选择灯面，调整颜色和动画配方并预览。
- **AE 特效：** 导入透明动画或使用 35 款预设，调整位置、贴合装甲、裁剪、长宽及左右双侧。
- **校验与安装：** 查看产物报告和哈希，向所选客户端安装并备份，按安装记录回滚。文件校验不能代替游戏内测试。

便携版请从 Releases 下载，解压到可写目录后运行「启动wot涂装工作台 3.3.cmd」。本仓库为 3.3 R1 源码与预设；源码不包含便携版运行环境。内置全部 35 款可导入、导出的 AE 特效预设，并附有「预设预览」：32 秒动态总览、离线搜索页面与逐款动画。

## 可选液态玻璃界面

默认是经典界面。点击工作台、AE、灯效或三维预览窗口顶部的界面按钮，可在经典与液态玻璃风格之间切换。选择统一保存在程序目录中；其他编辑器及弹窗获得焦点时同步，三维预览随状态刷新同步。保存失败时会提示。桌面窗口以配色模拟玻璃，不是系统级实时背景模糊。

本次统一了主窗口、AE、灯效窗口的参数选项卡、输入框、列表、滚动区域和帮助提示的配色及交互状态；切换风格时同步变化。预览图和颜色样本保持其原有颜色。

## R1 界面问题修订

- AE 处理期间，着色强度滑条现在与其他参数一起锁定，处理结束后恢复原状态。
- 灯效处理期间，「恢复自动保存工程」同步锁定，并在操作入口阻止中途更换来源。所有参数采用统一的忙碌状态逻辑，恢复时保留原本禁用或只读的状态。
- 经典与液态玻璃界面互切时，已经创建的下拉列表同步更新底色和选中色。

上述 3 个问题均先通过测试复现，再修正。相关代码注释与回归测试已更新。此次不改动原生特效资源，保留全部 35 款预设。

## 液态玻璃 AE 预设

新增 34「液态玻璃水滴」、35「液态玻璃流带」。进入 AE 特效窗口选择预设并套用，可在播放与透明调整颜色和强度，也能设置位置、独立长宽、裁剪和左右双侧。水滴与流带是普通透明动画，以高光模拟玻璃；不实时折射或模糊车身底图。预设可通过「管理 / 导入…」导出或导入，也会随本次生成的涂装 ZIP 附带。

## 双侧与变形

独立平面左右双侧现在分别生成镜像后的网格、法线及序列；拖动变形时两侧同步。新建流动平面会保留当前方向、位置、长宽与双侧设置。贴面依据选中区域镜像，不会自动匹配另一侧不对称装甲；车体中线上的双侧平面会重合。较小窗口可滚动 AE 右侧找到尺寸、位置、变形与裁剪。

此前生成的涂装包不会自动变化，需重新生成。同一车型避免同时启用冲突的多份涂装或 AE 包。

## 验证范围

完成 84 项无窗口后台回归、32 项隔离桌面真实界面检查、双侧拖动脚本检查、全部 35 款预设与动态预览检查。包内自带运行环境另执行 39 项后台检查与同一套 32 项界面检查；后两组属于复核，不计为新增测试。界面测试在独立桌面运行，不切换当前桌面，不操作游戏。

此前以用户确认可正常使用的欧服 Pz70 原涂装为基线，离线生成玻璃双侧样例并回读 96 帧、192 个材质及两侧网格；原始资源逐字节保留。原包存在一处既有炮塔网格分组警告，该项未改动。此前欧服客户端资源检查为 2.4.1.1 #989。离线样例的整车状态为 not_tested；此次 R1 仅修订工作台界面，未重新生成该样例或启动、安装游戏。实际整车加载、玻璃效果、遮挡和远近显示需游戏内验证。你的实际客户端更新后需重新核对。


## 致谢

感谢 コイカツ 和 GPT 对本项目的帮助与支持。




