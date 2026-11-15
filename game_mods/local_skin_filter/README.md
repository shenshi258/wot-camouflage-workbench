# 本地涂装屏蔽 2.1.2：游戏内搜索与拖框

用户在本机欧服实测 2.1.1 时窗口能打开，但内容空白。本次运行日志记录
CEF 白名单开启，插件网址连续返回 418；同一进程的本机页面服务返回
200 HTML。2.1.2 改用独立的原生 Gameface 界面资源与 ViewModel，
不再导航 CEF，不启动 HTTP 服务，不改变浏览器白名单或安全设置。
旧版失败记录、脱敏日志与截图在工作区单独保留。新版仍待游戏内复测。

直接安装 `.wotmod`，在车库模组列表打开“本地涂装屏蔽 · 搜索与框选”。
按车型名称／编号搜索，与国家筛选叠加，鼠标拖矩形圈选多行。支持 Ctrl
追加、Shift 连选、边缘自动滚动、全选筛选结果及“一键屏蔽全部敌车”。
选中车型可批量设置不屏蔽、仅敌车、仅队友或敌我都屏蔽；自己的车不变。
2.0、2.1、2.1.1 已保存的规则和总开关继续保留。

界面通过 `gui/gen_resources/local.skin_filter.json` 注册到自有
`R.mods.local_skin_filter` 资源树。原生 WULF 窗口打开包内页面，ViewModel
传递状态与指令；保存复用原有主线程队列。采用 Flexbox、自制下拉框与
勾选按钮，避免依赖 Gameface 不支持的原生 SELECT。进入战斗关闭面板，
关闭、重新打开与退出游戏时释放窗口。无需外部网站、浏览器或桌面工具。

`selector.html` 是页面源，`gameface.py` 是原生界面适配；`selector.py`
仅用于开发预览和隔离测试，不装入游戏包。构建不重新分发游戏 SDK。
原生资源注册方式参见 [OpenWG 文档](https://gitlab.com/openwg/wot.gameface/-/blob/master/README.md#wg-native-resources)，
界面控件限制参见 [Gameface 文档](https://docs.coherent-labs.com/cpp-gameface/content_development/supported_features_tables/htmlelements/)。

欧服／亚服读取各自原版资源和已安装覆盖列表。只为识别到原版车型目录
有覆盖的车型准备原版缓存，避免全选时复制全游戏；准备只在车库进行，
完整回读后才发布。原 `.pkg` 与旧涂装不改写。缓存位于自己的
`res_mods/<version>/vehicles/_lsf2/`；异常、观察者、不明队伍和未完成缓存
均保留当前外观。UML／AE 独立挂载及共享全局覆盖仍需适配。

保留原版材质标识、着色器、网格字节和标量文本，只隔离可视资源引用。
碰撞、可见性、点亮、瞄准、游戏输入和反作弊入口未修改。依赖原作者
[ModsSettings API](https://github.com/izeberg/modssettingsapi) 及 ModsList API，
不重新分发它们。Packed XML 解析器的 GPLv3 许可证和源码保留。

离线验证包含 32 项行为测试、两区最终 Python 2.7 字节码／资源回读、
Gameface 接口替身的打开／关闭／重开／指令检查，以及独立 Chromium
中 13 项交互检查，覆盖页面的 ViewModel 分支。原生 UI 引擎与整车渲染
未在本次亲自实测；`whole_vehicle_loading.status = not_tested`。
没有官方审核或反作弊零误报保证。

源码测试：`python -m unittest discover -s game_mods -t game_mods -p test_*.py`
构建及复核工具见仓库 `tools/build_in_game_skin_filter.py`、
`tools/check_in_game_filter27.py`、`tools/check_selector_browser.py`。
