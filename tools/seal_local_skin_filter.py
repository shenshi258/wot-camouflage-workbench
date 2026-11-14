"""Seal the locally prepared Pz70 candidate and bind offline results to its hash."""
import hashlib,json,shutil,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
WORKSPACE=ROOT.parents[1]


def digest(path):
    with Path(path).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    record_path=Path((ROOT/'.cache/filter10_final_record.txt').read_text('utf-8').strip())
    record=json.loads(record_path.read_text('utf-8'));target=Path(record['artifact']['path'])
    assert digest(target)==record['artifact']['sha256']
    runtime=ROOT/'.cache/enemy_filter/final_runtime27/结果.txt'
    assert runtime.read_text().startswith('PASS:')
    name='Pz70_本地涂装屏蔽_欧服2.4.1.1_待实测';out=WORKSPACE/'交付'/name
    out.mkdir(exist_ok=False)
    for source in target.parent.iterdir():
        if source.is_file():shutil.copy2(source,out/source.name)
    shutil.copy2(runtime,out/'离线脚本检查.txt')
    delivered=out/target.name
    assert digest(delivered)==record['artifact']['sha256']
    record['artifact']['path']=str(delivered)
    record['offline_validation']['runtime_probe']=dict(status='passed',game_process_started=False,
        artifact_sha256=digest(delivered),scope='delivered py27 + native cosmetic getter, API doubles, 100 x 3 state cycles',
        evidence='离线脚本检查.txt',visual_result='not_tested')
    (out/'验证记录.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/(delivered.name+'.sha256')).write_text(digest(delivered)+'  '+delivered.name+'\n',encoding='utf-8')
    archive=out.with_name(name+'.zip')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=6)as z:
        for item in out.iterdir():z.write(item,name+'/'+item.name)
    with zipfile.ZipFile(archive)as z:
        assert z.testzip()is None
        with z.open(name+'/'+delivered.name)as f:assert hashlib.file_digest(f,'sha256').hexdigest()==record['artifact']['sha256']
    report=WORKSPACE/'交付/本地涂装屏蔽_1.0_检查记录.md'
    helper=WORKSPACE/'交付/本地涂装屏蔽 1.0_独立准备工具_待实测.zip'
    source=WORKSPACE/'交付/本地涂装屏蔽 1.0_源码.zip'
    report.write_text(f'''# 本地涂装屏蔽 1.0 · 离线检查记录

本版是独立准备程序和待实测游戏内 MOD。采用逐车外观选择的思路，读取原版 .pkg 创建私有资源副本，不修改旧涂装。默认只为敌车恢复原版，队友可选，自己的车与车库保留原外观。按车型选择，设置在车辆下次正常加载时生效。

## 交付

- 独立便携程序：`{helper.name}`；{helper.stat().st_size} 字节；SHA256 `{digest(helper)}`。
- 源码：`{source.name}`；SHA256 `{digest(source)}`。
- Pz70 样包 ZIP：`{archive.name}`；SHA256 `{digest(archive)}`。
- 最终游戏包：`{delivered}`；{delivered.stat().st_size} 字节；SHA256 `{digest(delivered)}`。

## 环境与基线

用户明确目标为 Wargaming 欧服／美服／亚服。实际当前启动目录未确认；本次仅从已安装欧服 `D:\\wot\\World_of_Tanks_EU` 的 `v.2.4.1.1 #993` 提取原版资源供离线准备，不自动安装、不启动游戏。原版在当前环境是否正常加载未由代理或用户完成本次确认。其他客户端需在准备工具中选择实际目录并重新生成。

Pz70 最终包含 {record['offline_validation']['resources']} 项原版资源，映射 {record['offline_validation']['model_paths']} 个模型路径。材质参数、着色器标识与原版网格字节保持原值，仅 XML 依赖路径迁移至私有位置。共享贴图依赖一并隔离；碰撞、物理、点亮、可见性与输入入口没有修改。

## 已完成的离线检查

- 14 项后台行为检查、5 项独立桌面真实控件检查通过；便携包使用自己的运行环境重复复核，未重复计算测试数量。
- 包内程序识别实际 Pz70 输入包，并从欧服原版生成最终候选，不执行输入包脚本。最终包 ZIP CRC、无压缩条目、XML 回读、资源清单与哈希复核完成。
- 回读 {record['offline_validation']['groups_checked']} 个网格分组，另有 {len(record['offline_validation']['preexisting_group_issues'])} 项损毁车体分组范围被离线解析器标出，复制前后相同。它们是原版数据中的既有离线提示，未验证为游戏故障；没有新增分组问题。
- 使用最终包内 Python 2.7 字节码和当前欧服原生外观路径选择函数，在独立进程及接口替身中检查 100 × 3 次普通／损毁／爆炸状态、敌我开关、刷新、身份变化、观察者、原描述对象保持及碰撞入口保持。没有运行游戏、Compound 或原生着色器。
- AMX 50B 原版依赖规划另读到 609 项资源／161 个模型；只完成规划，没有生成或实测该车型包。

## 尚未验证与适用范围

最终样包 `whole_vehicle_loading.status = not_tested`；`in_game_tested = false`。车库整车、训练房同款敌我车辆、姿态、LOD、损毁、切车重载、不同画质、实际样式和其他模组兼容均待实测。脚本模拟通过不证明实际屏蔽可见，也不证明整车兼容通过。

只保护原版路径模型／贴图替换。UML／AE／第三方脚本自有命名空间和独立挂载物不保证被屏蔽，不能称为通用 UML 拦截器。需要另装原作者 ModsSettings API 与 ModsList API；本机欧服已发现 1.7.1 和 1.8.0，但没有验证其游戏内设置窗口，本交付不再分发它们。

已核对 [WG 禁止模组规则](https://worldoftanks.eu/en/content/guide/fair-play/prohibited-mods/) 和 [2026 公平游戏更新](https://worldoftanks.eu/en/news/general-news/ban-wave-jan-2026/)。实现不包含反作弊隐藏／规避或进程注入，不代表获得官方审核或保证零误报。本次未提交 Mod Hub、未上传 GitHub，也不包含旧 AE 闪烁修复。
''',encoding='utf-8')
    print('SAMPLE',archive,digest(archive),archive.stat().st_size)
    print('REPORT',report)


if __name__=='__main__':main()
