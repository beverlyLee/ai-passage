# 本地文件监控 Agent — 可运行代码

纯标准库，无第三方依赖，可直接进 CI。

## 01_file_watcher.py — 事件层

把 watch 原始事件收敛成「每个文件每个窗口一个确定性事件」：

- **排除**：`.git/`、`node_modules/`、`.tmp`、`.DS_Store` 等噪音路径直接丢弃
- **防抖**：同一路径 0.4s 窗口内的多个事件合并为一个
- **幂等**：2s 内同一 `(path, op)` 的重复投递丢弃，不重复触发

生产用法：把 `simulate_event_stream` 换成 watchdog 的 `on_modified` 回调，定时 `flush()` 即可。

```bash
python3 01_file_watcher.py --self-test
```

## 02_rule_engine.py — 动作层（规则引擎）

把「删除」做成不可轻易触发的动作：

- **白名单优先**：命中白名单的文件绝不删（优先级高于一切删除规则）
- **默认 dry-run**：必须显式 `--apply` 才落地
- **删除走回收站**：`shutil.move` 进回收站而非 `os.remove`，留后悔药

```bash
python3 02_rule_engine.py --self-test
python3 02_rule_engine.py --apply /path/to/old_photo_2020.jpg
```

## 配套文章

`../2026-09-15-本地文件监控Agent/本地文件监控Agent-掘金-2026-09-15.md`
