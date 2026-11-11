# Stage B 窄修正

编码评审没有接受 `d4d6a60` 为完成态。这次只补它指出的口径，仍然没有合并、部署或登录。认证原因仍然未知。每周下载没有修好。

## 已有 `%PDF` 不再只凭文件头算完成

`classify_current_archive` 对已有文件和新下载使用同一套抽出文本条件：`%PDF`、`Clinical Practice Guidelines in Oncology`、所请求的指南名、所请求的版本。患者系列短语本身仍然不构成拒绝。

分类结果：

| 状态 | 含义 | 自动处理 |
| --- | --- | --- |
| `valid` | 匹配的专业版 | 保持原字节，不重下 |
| `missing` | 标准路径上没有非空文件 | 可以下载 |
| `replaceable_non_pdf` | 登录页 HTML 等非 PDF 占用 | 可以替换 |
| `blocked_invalid_existing` | 已有 `%PDF` 但损坏、指南名不对或版本不对 | 不删除、不覆盖，报告 `blocked-invalid-existing pending manual disposition` |

`get_archived_versions` 在 meta 同时有名称和版本、且文件以 `%PDF` 开头但不匹配时，不再把该版本列入已归档。没有名称的旧测试夹具维持原来的列出方式。

新增测试覆盖：错名、错版、截断 `%PDF` 的字节不变且不接受随后的正确响应；一份已经匹配的专业版保持完成且字节不变；`check_updates` 对错名占用只报告 blocked，不调用下载。

## 周检可调用的最小接口

`archive_followups_for_recorded_versions` 在 `detect_changes` 之外计算监控范围内、已记录当前版本里尚未成为有效专业版的项。它不下载、不改文件，也不改变「空列表表示版本未变」。

现场 AST 只说明周检脚本自己调用 `detect_changes`，空则返回整数，否则对 changes 调用 `download_and_archive`。摘要不是源码，不能据此写 wrapper 补丁。该函数现在由 `check_updates` 使用；wrapper 集成要等安全源码副本。因此每周入口的缺档重试仍然没有接上。

## 登录诊断入口

`NCCNDownloader.diagnose_login` 供授权后的本地运行。它不改 `login()` 的成功/失败判断，也不在云端对 NCCN 发起请求。返回只有：状态码、host、去掉 query 的 path、content type 的 media type，以及登录表单、Account Settings、Log Out 三个布尔值。不记录用户名、密码、请求体、headers、cookies、token、原始页面或带 query 的 URL。测试使用模拟响应。

## 这次复跑

```bash
.venv/bin/python -m pytest tests/test_archive.py tests/test_state.py tests/test_scraper.py tests/test_health.py tests/test_auth_download_regression.py -q --tb=no
```

结果：`62 passed`。这是本工作区这次命令的输出，不是评审侧的独立复跑。

## 仍然阻塞

1. 没有真实 httpx 的状态码、去 query 后的最终 path、Content-Type，以及登录表单 / Account Settings / Log Out 的现场布尔值。不能改登录判断，也不能把认证写成已修复。
2. 周检脚本仍不调用 `check_updates` 或 `archive_followups_for_recorded_versions`。版本已写入且有效 PDF 缺失时，它是否再次下载仍未接到代码上。每周下载未修好。
3. MBP 工作区里未提交的 `downloader.py` / `scraper.py` 与这份候选不是同一份文件。摘要不能说明那些本地差异。没有把它们并入。
4. 没有脱敏 wrapper 源码，因此没有 wrapper 补丁。
