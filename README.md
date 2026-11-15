# WOT 涂装工作台 3.9 / WOT Camouflage Workbench

[中文版](#中文版) | [English](#english)

3.9 增加普通涂装的“应用范围”：所有同资源车辆（默认）或仅自己的车辆。基础涂装、三维贴图和已有普通涂装转换均支持，范围随草稿保存。仅控制本机显示；仅自己模式生成独立资源路径，暂不支持 UML、第三方脚本或共享覆盖包。游戏内效果待实测，本次不包含车库闪烁修复。

Version 3.9 adds a scope choice for ordinary skins: all vehicles sharing the same resources (default), or only your vehicle. It applies to texture builds, 3D painting and conversion of existing ordinary skins, and is retained in drafts. Own-vehicle mode uses private resource paths and excludes UML, third-party scripts and shared-resource override packages. This controls local rendering only. In-game behavior remains untested; the garage flicker diagnostic is separate.

另有独立 [本地涂装屏蔽 2.0 游戏内插件](game_mods/local_skin_filter/README.md)：直接安装 `.wotmod`，在游戏内按车型分别选择不屏蔽、仅敌车、仅队友或敌我都屏蔽，保留自己的涂装。插件自行读取当前欧服／亚服原版资源并准备独立缓存，无需桌面工具。需 ModsSettings API 及 ModsList API；UML／AE／第三方脚本独立挂载物暂不保证屏蔽。欧服 2.4.1.1 #993 和亚服 #991 完成离线检查，游戏内效果仍待实测；未经官方审核，不保证反作弊零误报。本次没有发布远程 Release，也不包含旧 AE 闪烁修复。

## English

WOT Camouflage Workbench is a Windows desktop toolkit for creating World of Tanks camouflage, models, lighting and animated effects. Version 3.8 adds a persistent thumbnail library for your own image elements, with batch import, search, categories and direct reuse in 3D painting. It includes GIF/video import, 36 AE presets, animated previews, bilateral controls and optional classic or glass-style interface themes.

### Features

- **Camouflage:** search an index built from the selected client; combine colors, patterns, weathering and named image decals, or reuse a recipe. Generate resources and an optional `.wotmod`.
- **3D painting:** preview a stock vehicle or an existing single-vehicle camouflage, place images on a model surface, and adjust their position, size and angle.
- **Model editing:** create a Blender project for a selected part and LOD, edit its mesh and export with read-back checks. Other LODs require separate work.
- **Lighting:** open an existing camouflage or project in the light editor, select light surfaces, adjust colors and animation recipes, and preview the result.
- **AE effects:** import transparent animations or use 36 presets; recolour, copy/paste parameters, preserve the image aspect ratio, repeat patterns, fit them to armor, crop, scale and configure mirrored sides.
- **Validation and installation:** inspect output reports and hashes, install to the selected client with backups, and roll back using an installation record. File checks do not replace in-game testing.

### New in 3.8: import your own thumbnail library

R1 aligns primary buttons across themes, bounds long labels, adds missing hover help, and keeps compact preview actions visible. When selecting multiple assets quickly, late responses no longer replace the most recent selection. The current revision passes 131 backend and 46 desktop UI checks, with browser theme/layout and interaction verification.

Open **涂装制作 → 管理图片素材库** to batch-import PNG, JPG or WebP files/folders, search by name/category, and edit labels. The library works without selecting a client or vehicle. In the 3D painting window, open **图片素材库**, select a thumbnail and choose **使用素材**, then click the model to place it.

Original image files remain unchanged. Copies and thumbnails persist under `程序/素材库/图片元素`; carry the `素材库` folder into the new program directory when upgrading. Removing an asset moves it to the library recycle folder and can be undone. Limits: 8 MB / 25 megapixels per image, 128 imports per batch, 1000 assets. Personal library content is excluded from release packages.

### New in 3.7: import GIF and video elements

In the AE editor, choose **导入 GIF / 视频动画…**, select a local GIF, MP4, MOV, WEBM, AVI, MKV or M4V, then choose its start/end times, output FPS and background handling. Each import supports up to 128 frames at 1–60 FPS; the dialog shows the selected duration and frame count. Video reading depends on its codec; the portable build includes the decoder. Audio is omitted.

GIF timing, disposal and transparency are sampled into the existing atlas format. Ordinary video can keep its rectangular picture or convert a black background into an additive light effect. Import replaces the current animation, retaining vehicle placement. The new standalone preview plays, pauses and restarts the material without a client; existing colour, fitting, project and preset controls remain available. This version delivers the requested import feature; the reported static-package flicker remains for the next investigation.

### New in 3.6: adjustable meteor rain and colour fixes

Select **36 彩色流星雨** for a 96-frame, 24 FPS, four-second loop. Tint strength 0% keeps its rainbow colours; 100% uses the selected colour. Typing a complete colour code or picking a colour now enables tint when strength is zero. The 3D picker and strength slider update during dragging, retain pending edits during refresh, and load the texture matching each colour version. Re-export existing packages to apply changes; very high brightness can wash out colour differences.

### New in 3.5: copy settings and fit patterns

Use **复制设置 / 粘贴设置** (Copy / Paste settings) in the AE editor to reuse position, size, brightness and other effect parameters. The destination vehicle, animation, selected faces and client stay selected. Check copied positions when changing vehicles.

Open **长宽与贴合 → 图案适配** (Size and fitting → Pattern fit) to choose **contain** (keep the whole image with empty margins), **cover** (fill the area and crop edges), **tile** (repeat without stretching), or legacy stretch. Tiling has an adjustable horizontal repeat count of 0.25–16. The 3D preview offers the same controls under **缩放与裁剪** (Scale and crop), alongside copy/paste. Explicit independent axis scaling and corner deformation can still change proportions.

Old projects and presets retain legacy stretch. New fitting and repeat settings persist in projects, presets and generated packages; use 3.5 to reopen them. All 35 bundled preset files are retained.

### 3.4 R1 UI review

Slider palettes and disabled/focus states now follow both themes. Preview branding uses the current application version; decimal precision and help text are aligned. Key appearance-processing code has explanatory comments.

### New in 3.4: AE appearance sliders

Open the AE window, then select **播放与透明** (Playback and transparency). Brightness (0.01–100×), contrast (0–3×), and transparency (0–100%) can be adjusted with sliders or numeric input. The 3D preview has the same three sliders. Transparency 0% preserves the source alpha; 100% makes the effect invisible. Reset restores 1× / 1× / 0%.

Settings are saved in editable projects and exported presets, and applied to generated packages. Existing projects and presets use neutral defaults for the new controls. Previously generated packages must be generated again. Very high brightness can wash out highlights. Native shader rendering and in-game effects still need testing.

### Download and run

Extract the supplied **3.8 local portable ZIP** to a writable folder and run `启动wot涂装工作台 3.8.cmd`. Published downloads are listed in [Releases](https://github.com/shenshi258/wot-camouflage-workbench/releases); this local build has not been published. Project introductions, release notes and acknowledgements stay outside the portable ZIP. The source repository does not include the portable Python runtime. The glass appearance uses colors and highlights; it does not provide real-time background blur or refraction.

### Earlier R1 changes

- Locks the AE tint-intensity slider and light-effect recovery controls during processing, restoring their previous states afterwards.
- Updates existing dropdown colors when switching themes.
- Retains all 35 presets and adds no changes to native effect assets in this revision.

### Validation

Version 3.8 passed 131 backend checks and 44 isolated desktop UI checks, plus real-browser import/search/persistence/recycle/painting-export checks and preview interaction scripts. The portable build repeats the backend and desktop suites with its included runtime and video decoder. Export checks use synthetic fixtures to compare imported media, preview/export geometry and texture pixels; they do not prove native shader rendering. Complete in-game vehicle loading and visual effects have **not been tested** (`not_tested`). The actual running client is unconfirmed. The reported static-package flicker remains for investigation.

### Acknowledgements

Thanks to **コイカツ** and **GPT** for their help and support.

---

## 中文版

### 3.8 新增：自己的图片也能导入缩略图素材库

R1 统一主题下的主按钮，限制长名称占用，补齐悬停帮助并保留小窗口操作栏；连续使用素材时，迟到请求不再覆盖最新选择。当前修订通过 131 项后台、46 项桌面界面检查，并复核浏览器主题、布局与交互。

打开 **涂装制作 → 管理图片素材库**，可多选图片或按文件夹导入 PNG、JPG、WebP，自动生成缩略图，支持搜索、分类、改名及移出撤销。无需先选车型或客户端。三维贴图中点击 **图片素材库**，选中缩略图后按 **使用素材**，再点模型放置；保存当前贴图后可继续添加。

原图保留，素材副本和缩略图保存在「程序/素材库/图片元素」，再次打开仍能使用。升级时将旧版「素材库」文件夹复制到新版程序目录。单张最多 8 MB / 2500 万像素，每批最多 128 张，库内最多 1000 项；个人导入内容不附入新发布包。

### 3.7 新增：GIF / 视频动画元素直接导入

AE 窗口点击 **导入 GIF / 视频动画…**，选择片段时间、1～60 FPS 和背景处理，最多转换 128 帧。支持 GIF、MP4、MOV、WEBM、AVI、MKV、M4V；便携包自带视频读取组件，实际支持还取决于素材编码，仅导入画面，不含音轨。GIF 按原逐帧延时和清除方式取样；普通视频可保留完整矩形画面，黑底光效可转为透明。

导入后自动打开素材动画预览，可暂停、继续及重播，无需先选择客户端。导入替换当前动画，车辆和摆放参数保留；之后可继续调色、贴面、裁剪并保存工程或预设。此次先交付新功能，静帧闪烁按用户安排留到下个包排查。

### 3.6 新增：可调色的彩色流星雨，修正改色反馈

套用 **36 彩色流星雨**，获得 96 帧、24 FPS、4 秒循环的透明动画。着色强度 0% 保留彩虹原色，100% 统一为所选颜色。现在直接输入完整色号也会自动启用原为 0% 的着色；三维取色器与强度滑条拖动时同步，避免旧同步状态覆盖新选择，并按颜色版本读取贴图。高亮度可能使色差变淡，已有成品需重新生成。便携包不附项目双语介绍、更新说明和致谢。

### 3.5 新增：参数复刻、等比适配与重复平铺

- **复制 / 粘贴设置：** 复用位置、尺寸、亮度等 AE 制作参数，目标车辆、动画素材、承载面选区和客户端保持当前选择。换车型后请检查位置是否合适。
- **保持原比例：** 在 **长宽与贴合 → 图案适配** 选择「等比完整（留空）」或「等比铺满（裁边）」，避免把图片强行拉伸到整个区域。
- **重复平铺：** 选择「等比重复平铺」，横向重复次数可调 0.25～16，纵向按素材比例自动计算。三维预览展开 **缩放与裁剪**，也可调整适配、平铺并复制或粘贴设置。

主动调整独立长宽比例或四角变形仍会改变图案比例。旧工程和旧预设继续使用原来的拉伸填充；新参数随工程、预设及新生成的涂装包保存，重新打开请使用 3.5。内置 35 款预设原文件保留。

### 3.4 R1 界面复核

滑条统一主题配色和禁用/焦点状态；预览和灯效入口统一当前版本文字；外观栏统一小数精度，并补全悬停说明和关键代码注释。

### 3.4 新增：AE 外观滑条

打开 AE 窗口，进入 **播放与透明** 页，可拖动或输入：**亮度 0.01～100 倍、对比度 0～3 倍、透明度 0～100%**。三维预览也提供相同滑条。透明度 0% 保留素材原透明度，100% 完全透明；一键重置恢复 1 倍 / 1 倍 / 0%。

参数随 AE 工程、导出预设和新生成的涂装包保存。旧工程和预设读取时，新增参数采用中性默认值；旧成品需重新生成。高亮度可能使高光发白。游戏原生着色器及实际效果仍待实测。

### 功能介绍

- **涂装制作：** 从所选客户端建立车型索引，组合颜色、图案、做旧和指定图片贴花，也可用配方再次生成；输出资源和可选 `.wotmod`。
- **三维贴图：** 预览原版车型或同车已有涂装，在模型表面放置图片并调整位置、大小和角度。
- **模型编辑：** 为选定部件和 LOD 创建 Blender 工程，编辑网格并导出回读检查；其他 LOD 需分别处理。
- **灯效制作：** 导入已有涂装或工程，选择灯面，调整颜色和动画配方并预览。
- **AE 特效：** 导入透明动画或使用 36 款预设，调色、复制/粘贴参数，按原比例适配或重复平铺，调整位置、贴合装甲、裁剪、长宽及左右双侧。
- **校验与安装：** 查看产物报告和哈希，向所选客户端安装并备份，按安装记录回滚。文件校验不能代替游戏内测试。

3.8 本地便携包解压到可写目录后运行「启动wot涂装工作台 3.8.cmd」。在线已发布版本见 Releases；本次本地版尚未上传。本仓库为 3.8 源码与预设；源码不包含便携版运行环境。内置全部 36 款可导入、导出的 AE 特效预设，保留原 35 款总览和逐款动画，新流星雨预览位于「程序/预设/AE预览」。

## 可选液态玻璃界面

默认是经典界面。点击工作台、AE、灯效或三维预览窗口顶部的界面按钮，可在经典与液态玻璃风格之间切换。选择统一保存在程序目录中；其他编辑器及弹窗获得焦点时同步，三维预览随状态刷新同步。保存失败时会提示。桌面窗口以配色模拟玻璃，不是系统级实时背景模糊。

本次统一了主窗口、AE、灯效窗口的参数选项卡、输入框、列表、滚动区域和帮助提示的配色及交互状态；切换风格时同步变化。预览图和颜色样本保持其原有颜色。

## 此前 R1 界面问题修订

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

3.8 完成 131 项后台回归、44 项隔离桌面真实界面检查，以及真实浏览器中的图库导入、搜索、持久保存、回收撤销、点选贴图和导出检查。最终便携包使用自带运行环境和视频读取组件复核相同后台和界面测试；复核不计为新增测试。界面检查不切换当前桌面，不操作游戏。导出测试使用合成夹具，比较媒体导入、改色像素、预览与导出网格及原始资源，不能证明原生着色器或游戏整车加载成功。

此前欧服 Pz70 原涂装属于用户确认可用的基线，并非代理亲自游戏实测。本次实际运行客户端尚未确认，未安装或启动游戏；整车加载、实际光效、遮挡和远近显示状态均为 not_tested。此次制作器功能更新不代表此前反馈的游戏内闪烁已经解决。实际客户端或最终生成包改变后，需重新核对并游戏内验证。


## 致谢

感谢 コイカツ 和 GPT 对本项目的帮助与支持。
