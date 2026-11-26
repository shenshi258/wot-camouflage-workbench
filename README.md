# wot涂装工作台 4.1

[中文](#中文) | [English](#english)

## 中文

wot涂装工作台是面向《坦克世界》（World of Tanks）的 Windows 工具，提供涂装制作、三维贴图、模型编辑、灯效和动画特效制作。

### 功能

- **涂装制作**：从所选游戏客户端建立车型索引，组合颜色、图案、做旧与图片贴花，保存配方并生成涂装资源。
- **三维贴图**：预览车型或已有涂装，在模型表面放置图片，调整位置、大小和角度。
- **应用范围**：普通单车型涂装可选择作用于所有同资源车辆，或使用“仅自己的车辆”。仅本车模式适用于支持的普通涂装包，UML、第三方脚本和已有动画等特殊包需另外适配。
- **模型编辑**：为所选部件和 LOD 创建 Blender 工程，编辑网格并导出。其他 LOD 需要分别处理。
- **灯效制作**：选择灯面，设置颜色、亮度和动画配方并预览。
- **图片与 GIF 素材库**：导入图片及 GIF，使用缩略图、分类和搜索管理素材。素材副本保存在本地，升级时保留“程序/素材库”目录。
- **AE 动画特效**：导入 GIF、视频、透明 PNG 序列或图集，选择片段、帧率和透明处理，调整亮度、对比度、透明度、颜色、位置、长宽、裁剪、左右双侧和贴合方式。支持等比适配、重复平铺、复制参数，以及移动、旋转、缩放和透明度的动画节点。内置 36 款 AE 预设。
- **工程与校验**：保存和重新打开工程或预设，查看导出结果的文件检查记录。支持向选定客户端安装、备份及按记录回滚。

### 4.1 成品体积优化

AE 导出会共用完全相同的画面和模型、重排图集减少空白，并省去游戏包内额外的图集 PNG。优化发生在导出阶段，保留导入后动画的播放帧数、帧率及逐帧像素；可编辑工程和预设仍保留素材图集。重复画面较多时节省更明显，每帧都不同且图集已经排得紧时节省可能很少。要应用优化，请用 4.1 重新导出已有工程或预设。

离线样例中，480×270、24 FPS、2 秒、含重复画面的成品从 32.47 MiB 降到 8.21 MiB，逐帧回读一致。这是样例结果，实际大小取决于素材和原涂装。GIF/视频导入有采样和最多 128 帧限制，每帧最长边超过 512 像素时会缩小；普通三维贴图使用 GIF 首帧。

### 下载和使用

从 [Releases](https://github.com/shenshi258/wot-camouflage-workbench/releases) 下载 **wot涂装工作台 4.1**，解压到可写文件夹，运行“启动wot涂装工作台 4.1.cmd”。源码仓库不含便携包的完整 Python 运行环境。

动画与灯效的新导出包仍需在对应客户端检查整车加载、播放、遮挡和 LOD。此前反馈的游戏内闪烁原因尚未确认。文件和离线预览检查不能替代游戏内验收。

### 致谢

感谢 **GPT** 在开发与整理中的协助。

---

## English

wot涂装工作台 4.1 (WOT Camouflage Workbench) is a Windows toolkit for World of Tanks camouflage, 3D painting, model editing, lighting and animated effects.

### Features

- **Camouflage**: index vehicles from the selected client, combine colours, patterns, weathering and image decals, and save recipes.
- **3D painting**: preview a vehicle or existing skin and place images on its surface with position, size and rotation controls.
- **Application scope**: supported ordinary single-vehicle skins can be applied to all vehicles sharing the resource, or only to the player's own vehicle. UML, third-party scripts and existing animated packages require separate support.
- **Model editing**: create a Blender project for a selected part and LOD, edit the mesh and export it. Other LODs need separate work.
- **Lighting**: select light surfaces, adjust colour, brightness and animation recipes, and preview the effect.
- **Image and GIF library**: import, categorise, search and reuse local assets with thumbnails. Preserve the `程序/素材库` folder when upgrading.
- **AE animation**: import GIFs, videos, transparent PNG sequences or atlases; adjust timing, transparency, colour, brightness, contrast, placement, fitting and mirrored sides. Animation nodes control movement, rotation, scale and opacity. The workbench includes 36 AE presets.
- **Projects and checks**: save editable projects and presets, inspect export reports, and install with backups and rollback records.

### Smaller AE exports in 4.1

The exporter shares identical frame assets, rearranges atlas tiles to reduce unused space and omits the extra PNG from the game package. It preserves the imported animation's frame count, frame rate and frame pixels; editable projects and presets retain the source atlas. Savings depend on the input. Re-export an existing project or preset to apply the optimization.

In an offline example with repeated frames, a 480×270, 24 FPS, two-second output decreased from 32.47 MiB to 8.21 MiB, with matching decoded frames. GIF and video imports are sampled, limited to 128 frames, and resized when the longest edge exceeds 512 pixels. Ordinary 3D decals use the first GIF frame.

### Download and verification

Download **wot涂装工作台 4.1** from [Releases](https://github.com/shenshi258/wot-camouflage-workbench/releases), extract it to a writable folder and run `启动wot涂装工作台 4.1.cmd`. The source repository does not contain the complete portable Python runtime.

New animation and lighting exports require in-game validation for vehicle loading, playback, visibility and LOD in the target client. The previously reported in-game flicker remains unconfirmed. Offline checks and previews do not establish in-game compatibility.

### Acknowledgements

Thanks to **GPT** for development and documentation assistance.
