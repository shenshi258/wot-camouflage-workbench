# 本地涂装屏蔽 2.1.1：游戏内搜索与拖框

2.1 在用户欧服实际点击时没有窗口。原因是原生 `BrowserController.load`
使用 `adisp_async`，调用返回等待调度的函数；旧版只调用而没有执行。
2.1.1 使用原生 `adisp_process` 协程并 `yield load(...)`。回归使用客户端
实际的 `adisp.pyc`，明确复现旧行为并验证新调用，仍需用户观察游戏窗口。

直接安装 `.wotmod`，在车库模组列表打开“本地涂装屏蔽 · 搜索与框选”。
按车型名称／编号搜索，与国家筛选叠加，鼠标拖矩形圈选多行。支持 Ctrl
追加、Shift 连选、边缘自动滚动、全选筛选结果及“一键屏蔽全部敌车”。
选中车型可批量设置不屏蔽、仅敌车、仅队友或敌我都屏蔽；自己的车不变。
2.0 已保存的规则和总开关继续保留。

界面使用客户端内置浏览器和包内自包含页面，设置在本机传递。页面工作
线程只收取带本次随机令牌的请求并入队，游戏及 UI API 留在主线程。没有
外部网站、外部浏览器、进程注入或反作弊规避。`selector.html` 是可编辑源，
构建器将其编译成包内资源模块，不依赖用户电脑安装 Node 或浏览器。

欧服／亚服读取各自原版资源和已安装覆盖列表。只为识别到原版车型目录
有覆盖的车型准备原版缓存，避免全选时复制全游戏；准备只在车库进行，
完整回读后才发布。原 `.pkg` 与旧模组不改写。缓存位于自己的
`res_mods/<version>/vehicles/_lsf2/` 目录；缺少缓存、异常、观察者和不明队伍
都保留当前外观。UML／AE 独立挂载及共享全局覆盖仍需适配。

保留原版材质标识、着色器、网格字节和标量文本，只隔离可视资源引用；
碰撞、可见性、点亮、瞄准、输入与反作弊入口未修改。依赖原作者
[ModsSettings API](https://github.com/izeberg/modssettingsapi) 及 ModsList API，
不重新分发它们。Packed XML 解析器的 GPLv3 许可证和源码保留。

验证包括 32 项行为测试、两区最终 Python 2.7 字节码／资源／本机页面复核，
以及实际 Chromium 中 11 项交互与布局检查。窗口调度使用原生代码，原生
浏览器的创建和 UI 引擎使用替身。实际
游戏内 CEF、视觉与整车状态仍为 `not_tested`；没有官方审核或零误报保证。

源码测试：`python -m unittest discover -s game_mods -t game_mods -p test_*.py`
构建及复核工具见仓库 `tools/build_in_game_skin_filter.py`、
`tools/check_in_game_filter27.py`、`tools/check_selector_browser.py`。
