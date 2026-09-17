# 代码复现说明 · 邮件自动分类 Agent

本文《邮件自动分类 Agent：分类即建模，动作即风险》的可运行代码，共 3 个脚本。
**纯 Python 标准库，零第三方依赖，不需要真实邮箱账号、不发任何网络请求。**

## 数据源

全部为**内置合成样例数据**，脚本里硬编码，无需下载、无需联网：

| 项 | 说明 |
|---|---|
| 样例邮件 | 5 封合成邮件（u1–u5），覆盖白名单命中、规则冲突、含 PII、纯垃圾、正常通知 |
| 规则集 | 2 条：`发票归档`(优先级 1 → 账单)、`抽奖垃圾`(优先级 5 → 垃圾箱) |
| 白名单 | `boss@company.com`、`ceo@company.com` |
| 垃圾关键词 | 优惠 / 中奖 / 免费 / 点击 / 立即领取 |
| PII 示例 | 身份证 `11010119900307651X`（公开格式示例）、银行卡 `6222...0123`、`api_key=sk-abc123def`，**均为占位伪造值，不含任何真实个人信息** |
| IMAP 后端 | `FakeIMAP` 内存模拟，实现 `add / copy / store_del / health_check / expunge`，可注入 `connected=False` 确定性复现断连 |

> 为什么不用真实邮箱数据集：邮件内容受隐私与授权限制，公开语料（Enron 等）既涉及第三方隐私又不覆盖 IMAP 动作语义。本文要复现的是**动作层不变量**（幂等、可恢复、失败可见），合成数据足够且可完全复现。

## 运行方式

```bash
cd code/mail-agent

# 1. 分类层：白名单优先 / 优先级裁决 / 落库前脱敏
python 01_mail_classifier.py --self-test

# 2. 动作层：白名单 > dry-run > 回收站 / UID 幂等 / 断连告警
python 02_action_safety.py --self-test

# 3. 端到端：四阶段完整链路（推荐先看这个）
python 03_demo.py
python 03_demo.py --self-test   # 等价，供 CI 断言
```

环境：Python 3.8+。三个脚本都支持 `--self-test`，全部通过时输出 `ALL_SELFTESTS_PASSED`（03 为 `DEMO_OK`），退出码 0。

## 03_demo.py 四阶段输出含义

| 阶段 | 验证的不变量 | 期望结果 |
|---|---|---|
| 一 dry-run | 默认不执行，只报告 | IMAP 命令数 = 0 |
| 二 apply | 删除 = 移入 Trash，绝不 expunge | Trash 含 `u4`，`expunged` 列表为空 |
| 三 重复触发 | at-least-once 下 UID 幂等 | 第二批新增命令 = 0 |
| 四 断连 | 失败必须抛 `ActionAlert` | 捕获 `ActionAlert`，不静默吞 |

阶段一/二打印的表格列：`uid / from / label / action / dest`。

## 想接真实邮箱改哪里

只改 IMAP 适配层，另两个脚本不动：

- 把 `FakeIMAP` 换成 `imaplib.IMAP4_SSL` 的薄封装，实现同样 5 个方法（`copy` → `imap.copy`，`store_del` → `imap.store(uid, '+FLAGS', '\\Deleted')`）。
- `Actioner` 构造保持 `dry_run=True` 先跑一周，确认分类准确率后再切 `False`。
- **永远不要调用 `expunge()`**——这是本文第 ④ 坑的唯一硬约束。

## 文件清单

```
code/mail-agent/
├── README.md              本文件
├── 01_mail_classifier.py  分类层：Mail/Rule/Verdict + 白名单 + 优先级 + mask_text
├── 02_action_safety.py    动作层：Actioner + FakeIMAP + ActionAlert + 三道闸
└── 03_demo.py             端到端四阶段演示（导入前两个脚本）
```
