# 本地涂装屏蔽 2.0：游戏内插件

直接安装 `.wotmod`，在 ModsSettings API 的游戏内设置窗口按国家找车型，
每款车选择不屏蔽、仅敌车、仅队友或敌我都屏蔽；自己的车不变。
欧服和亚服读取各自原版车型与资源，无需桌面准备工具。

用户保存选择后，插件只在车库准备所需原版资源，保存在自己的
`res_mods/<version>/vehicles/_lsf2/` 空间。完成并确认引擎能看到文件后，
才允许模型路径切换。冷缓存、异常、观察者或不明队伍均保留原外观。
首次动态文件挂载不可见时提示正常重启；不强制战斗中的模型刷新。

缓存工作线程不调用游戏 API；UI、通知及引擎文件可见性检查在主线程执行。
原版 `.pkg` 和已有模组均只读。原版材质/着色器标识和网格字节保留，
只隔离可视资源引用；碰撞、可见性、点亮、瞄准、输入和反作弊入口未修改。
不执行输入涂装包脚本，不保证移除第三方独立挂载物。

依赖原作者 [ModsSettings API](https://github.com/izeberg/modssettingsapi)
及 ModsList API，不重新分发这两个框架。Packed XML 解析器沿用项目中
GPLv3 的 XmlUnpacker，许可证和可审阅源码同时保留。

离线验证目标为 EU `2.4.1.1 #993` 和 ASIA `2.4.1.1 #991`，包括最终包内
Python 2.7 模块、实际本区资源和原生可视路径选择函数；引擎/UI 使用替身。
所有游戏内视觉与整车结果仍为 `not_tested`，没有官方审核或反作弊零误报保证。

源码检查：`python -m unittest discover -s game_mods -t game_mods -p test_*.py`
构建与最终字节码核对脚本见仓库 `tools/build_in_game_skin_filter.py`、
`tools/check_in_game_filter27.py`。它们只在独立进程进行离线检查，不启动游戏。
