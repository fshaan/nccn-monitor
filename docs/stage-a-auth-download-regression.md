# Stage A：NCCN 周更认证/下载失败诊断

本文件是阶段 A 的作者说明。其中的「44 passed / 11 failed」是当时的叙述，不是阶段 B 开工时的闸门复跑。闸门复跑的完整 pytest 输出在 `docs/stage-b-auth-download-implementation.md`。

本文件只记录 2026-11-11 调查结果、可复现的失败测试，以及建议的修复边界。生产实现没有改动。

## 远程基线

云端工作区在调查开始时工作树干净。`git fetch origin feat/mvp` 之后：

| 引用 | SHA |
| --- | --- |
| `HEAD` | `07050876277b32cdf3bdeb3a18835cc2b8103603` |
| `origin/feat/mvp` | `07050876277b32cdf3bdeb3a18835cc2b8103603` |
| 本地 `main`（跟踪 `origin/main`） | `07050876277b32cdf3bdeb3a18835cc2b8103603` |

提交说明：`docs: fix OpenClaw plugin config format in README`（F.Sh，2026-03-20 22:49:02 +0800）。

这次云端检出与远程 `feat/mvp` 相同。用户本机当时观察到的 HEAD 也是这个 SHA，但本机未提交差异没有在这台机器上核对；本报告只对远程仓库和这次干净检出负责。

Stage A 分支：`cursor/nccn-auth-download-regression-d4cb`。

## 调查范围

读了 `src/nccn_monitor/`、现有 `tests/`、`README.md`、`CLAUDE.md`、`config.example.yaml`。没有读取 `config.yaml`、`.env`、家目录里的状态、索引或 PDF，也没有登录 NCCN、发送消息或部署。

外部包装脚本 `~/.hermes/scripts/nccn_weekly_check.py` 不在仓库里，本报告不假设它的内容。仓库内定时入口是 MCP 工具 `check_updates`；`openclaw-plugin/src/tools.ts` 只是把 `nccn_check_updates` 桥接到这个工具。

新鲜安装 `mcp[cli]>=1.11.0` 在 2026-11-11 解析到 `mcp 2.3.0`。`import mcp.server.fastmcp` 会抛出 `ModuleNotFoundError`。这与本次事故不是同一件事：事故日志已经进入 `NCCNDownloader.login`，说明当时的运行环境能导入下载器。回归测试只在导入 `server.py` 之前放入一个 FastMCP 装饰器垫片，用来调用 `check_updates` 协程。垫片不是修复方案，`pyproject.toml` 也没有改。

## 已由源码和失败测试证实的机制

这些结论不依赖包装脚本，也不依赖真实登录响应。

### 1. 版本先写入状态，下一次检查就不再下载

`StateManager.detect_changes` 在返回变化列表之前，把新版本写进 `guidelines` 并 `_save()`（`src/nccn_monitor/state.py`）。`check_updates` 先调用它，再下载（`src/nccn_monitor/server.py`）。下载失败只在报告里追加 `PDF download failed. Check NCCN credentials.`，不会回滚刚写入的版本。

因此下一次 `check_updates` 看到版本已经相等，返回：

`No guideline updates detected. Checked N guidelines.`

并且不再调用 `download_and_archive`。公开扫描已经发现的更新，会在 PDF 仍缺失时被当成完成。

两条测试把这个行为钉住，并且都在完整性断言之后才失败：

- `test_check_updates_retries_when_recorded_version_has_no_pdf`：状态里 Gastric Cancer 已经是 `2.2026`，归档只有 `v1.2026`。这是 MBP16 再次运行时的形状。失败点是报告仍包含 `No guideline updates detected`（`tests/test_auth_download_regression.py:419`）。在此之前，Colon 仍是 `4.2026`，未监控的 Breast 仍停在状态里的 `1.2026`，旧 PDF 和 `meta.json` 字节未变，状态文件不含 fixture 密码。
- `test_check_updates_retries_after_download_failure`：同一次进程里，基线之后的第一次更新会下载并得到 `PDF download failed`，再下一次又变成 `No guideline updates detected`（同文件第 466 行）。Colon 版本和旧归档字节在失败断言之前仍然保持原样；未监控的 Breast 没有被写进状态。

仓库里没有 `sys.exit(2)`。用户看到的 exit 2 只能来自未提供的包装脚本，本仓库无法解释这个退出码。

### 2. `Content-Type: application/pdf` 的正文会被直接归档

`download_pdf` 只要响应头包含 `application/pdf` 就把 body 写入文件（`src/nccn_monitor/downloader.py`）。它不检查 `%PDF`，也不读取标题或版本。`download_and_archive` 随后把该文件移动到：

`archive/{slug}/v{version}/NCCN_<CamelCase>_<Year>.V<Num>_EN.pdf`

并写入 `meta.json`，返回该路径。`check_updates` 把非空路径当作下载成功。

参数化测试把登录页 HTML、患者指南 PDF、Breast Cancer `2.2026` PDF、Gastric Cancer `1.2025` PDF 都标成 `application/pdf` 去归档 Gastric Cancer `2.2026`。四次都失败在 `assert result is None`，返回值是 `NCCN_GastricCancer_2026.V2_EN.pdf` 的路径。旧的 `v1.2026` 断言还没有执行到；从源码看，写新版本目录时不会打开旧目录。

### 3. 已经落在标准文件名上的登录页 HTML 会被当成完成

目标 PDF 已存在且大小大于 0 时，`download_and_archive` 直接返回该路径，不再请求网络（同文件 “Already archived” 分支）。

`test_existing_login_html_named_as_pdf_is_not_archived_completion` 预先写入登录页 HTML 和一份宣称成功的 `meta.json`。失败点是函数返回了这个路径，而不是 `None`。

`test_non_pdf_occupant_can_be_replaced_by_matching_professional_pdf` 进一步证明当前字节就是登录页：返回文件以 `<!DOCTYPE html>` 开头，`startswith(b"%PDF")` 为假（第 346 行）。测试期望这次重试能换成 fixture `professional_gastric_v2_2026.pdf`，同时 `v1.2026` 的 `%PDF` 字节保持不变。当前实现没有发起替换。

`get_archived_versions` 在 `meta.json` 存在时会收录该版本，不检查 PDF 魔数。现有 HTML 测试的“不得列入 2.2026”断言位于返回值断言之后，这次 pytest 输出还没有跑到它。源码已经能独立说明这个收录行为。

### 4. 患者指南链接会被当成主指南

`parse_detail_page_for_pdf` 取 Guidelines 列表里的第一个 `.pdf` 链接；没有 Guidelines 标题时，取第一个 `/professionals/physician_gls/pdf/*.pdf`，只排除 `_blocks`、`_core`、`_basic`、`_enhanced`（`src/nccn_monitor/scraper.py`）。

失败结果：

- 患者链接排在专业版前面时，返回 `.../stomach-patient.pdf`。
- 列表里只有患者指南时，返回该患者 URL，而不是 `None`。
- 没有 Guidelines 标题时，返回 `gastric_patient.pdf`，跳过后面的 `gastric.pdf`。

现有 `tests/fixtures/detail_page.html` 把患者指南放在另一个小节，所以旧测试仍然通过。新 fixture 覆盖的是“患者链接出现在主列表或回退顺序里”这一缺口。

### 5. 登录失败这条日志只能证明控制流走到了哪一步

`login()` 里唯一会写出 `Login failed: bad credentials or NCCN form changed` 的位置是 POST 之后的判断：

```python
if "/login" in str(result.url) or "Log in" in result.text:
    logger.error("Login failed: bad credentials or NCCN form changed")
    return False
```

能到达这里，说明当时同时满足：

- 用户名和密码都是非空字符串；
- GET 目标 URL 返回 HTTP 200；
- 页面上存在 `action="/login/Index/"` 的 form；
- 向 `https://www.nccn.org/login/Index/` 的 POST 没有抛异常；
- 最终 URL 含有子串 `/login`，或者正文含有 `Log in`。

空凭据、非 200、找不到该 form、以及异常，走的是别的日志，不会打出这一句。事故描述与这一句对应，所以那些分支可以被排除。

这一句不能区分：凭据被站点拒绝、最终停在 POST URL `https://www.nccn.org/login/Index/`、成功页 URL 仍含 `/login`，或页面任意位置仍有 `Log in`。两条子条件共用同一个日志。

## 认证原因现在不能判定

不能。缺少两类未提供、且不应含机密的本地材料：

1. `~/.hermes/scripts/nccn_weekly_check.py` 的源码：它调用的是 `check_updates`，还是自己组合 `detect_changes` 与 `download_and_archive`；exit 2 对应哪一个分支。
2. 那次 httpx 登录响应的脱敏特征：HTTP 状态、最终 URL 的路径（查询参数值抹掉）、`Content-Type`、正文里是否仍有 `form action="/login/Index/"` 或密码输入框、是否出现 `Log Out` / `Account Settings`、以及命中的是 URL 子串还是 `Log in` 文本。不要附带密码、cookie、token 或 PDF 正文。

同日浏览器里 1Password 填表后出现 Account Settings / Log Out，并且 3 份官方专业版 PDF 能下载，说明该账号在浏览器流程里可以完成公开站点登录。浏览器和 httpx 是两次独立请求。浏览器成功不能推出 httpx POST 的字段、cookie 和最终 URL。

因此测试没有修改登录成功条件，也没有把某一种登录失败写成唯一根因。

## 假设

下面几项与源码相容，但没有响应证据，回归测试故意不锁定它们：

- 成功页或中间页因为 URL 含 `/login`，或正文含 `Log in`，被现有判断记成失败。
- form 的 `action` 仍是 `/login/Index/`，但站点还要求隐藏字段以外的字段；当前代码只复制 `type="hidden"`，再加 `Username`、`Password`、`RememberMe`。
- 站点返回了仍包含登录表单的挑战页或错误页。
- httpx 使用的配置口令与浏览器里 1Password 填入的口令不同。

相邻观察，同样没有放进失败测试：`check_updates` 在下载之前调用 `health.record_success()`。登录失败不会增加连续失败次数。这不影响“归档是否完成”的判断，最小修复不必改健康状态。

## 修复前的实际命令

环境：Python 3.12.3，本机新建 `.venv`，`pip install -e ".[dev]"`。`.venv` 不入库。

既有单元测试：

```bash
.venv/bin/python -m pytest tests/test_archive.py tests/test_state.py tests/test_scraper.py tests/test_health.py -q
```

结果：`44 passed`。

新回归测试：

```bash
.venv/bin/python -m pytest tests/test_auth_download_regression.py --tb=line -q
```

结果：`11 failed`。失败名称：

- `test_detail_page_skips_patient_link_listed_before_professional`
- `test_detail_page_returns_none_when_only_patient_guide_is_listed`
- `test_detail_page_fallback_skips_patient_and_blocks_filenames`
- `test_download_and_archive_rejects_html_patient_wrong_title_or_version` 的四组参数：`login_wall.html`、`patient_stomach.pdf`、`professional_breast_v2_2026.pdf`、`professional_gastric_v1_2025.pdf`
- `test_existing_login_html_named_as_pdf_is_not_archived_completion`
- `test_non_pdf_occupant_can_be_replaced_by_matching_professional_pdf`
- `test_check_updates_retries_when_recorded_version_has_no_pdf`
- `test_check_updates_retries_after_download_failure`

测试使用 `tmp_path` 和重定向后的 `HOME`。HTTP 使用 `httpx.MockTransport`，主机限制为 `www.nccn.org` / `nccn.org` 的模拟响应。`check_updates` 测试替换了抓取和 `download_and_archive`，并让真实 `_get_client` 直接抛错，避免开 socket。

Fixture 都是合成的。四个 PDF 各一页，由 pypdf 在本地生成，可抽出的文本分别是：

- `patient_stomach.pdf`：`NCCN Guidelines for Patients Stomach Cancer`
- `professional_breast_v2_2026.pdf`：`NCCN Clinical Practice Guidelines in Oncology Breast Cancer Version 2.2026`
- `professional_gastric_v1_2025.pdf`：`NCCN Clinical Practice Guidelines in Oncology Gastric Cancer Version 1.2025`
- `professional_gastric_v2_2026.pdf`：`NCCN Clinical Practice Guidelines in Oncology Gastric Cancer Version 2.2026`

`login_wall.html` 含有 `action="/login/Index/"` 和 `Log in`，隐藏字段值是 `fixture-token`。它们不是 NCCN 页面，也不是指南正文。

## 建议的最小修复边界

尚未实现。Stage B 只应让上面 11 个测试通过，并补上下面的正向锁定测试。不要先改登录成功判断。

建议改动落在：

- `download_pdf` / `download_and_archive`：新写入归档之前，正文必须以 `%PDF` 开头；抽出的文本同时包含所请求的指南名和版本号，且不包含 `Guidelines for Patients`。患者 URL（路径中含 `/patients/`）和 `*patient*` 文件名不能作为专业版归档。拒绝时返回 `None`，不写成功用的 `meta.json`。
- 目标文件名上已经有非 `%PDF` 内容时，允许用一次新的、通过上述检查的响应替换该占用文件。已经以 `%PDF` 开头的旧版本文件保持原字节，包括用户现有的正式归档。
- `get_archived_versions`：非 PDF 或被拒绝的占用文件不能作为已归档版本返回。
- `parse_detail_page_for_pdf`：跳过患者指南和现有的 blocks/core/basic/enhanced 链接；主列表里没有专业版 `physician_gls` PDF 时返回 `None`。
- `check_updates`：监控列表内的指南，若状态中的当前版本没有一份通过校验的归档 PDF，再次调用下载。版本号已经相等不能单独当作完成。未出现在监控列表中的指南保持现状，即使公开目录里的版本变了也不下载。Colon 这类已经有归档文件的版本不要重新下载。

`detect_changes` 现在会在下载前提交版本。只改 `check_updates` 可以让本仓库的 MCP / OpenClaw 入口按缺失 PDF 重试，从而覆盖测试和已经写入状态的 MBP16 形状。如果外部包装脚本自己调用 `detect_changes`，并在返回空列表时直接结束，那么它仍会跳过。包装脚本读到之前，不要为了猜测它的结构去改 `detect_changes` 的比较语义；空列表必须继续表示“版本没有变化”。共享的“当前版本还没有有效 PDF”判断可以放在下载层，供 `check_updates` 使用，包装脚本确认后再接上。

不要改登录 POST 的成功条件，除非拿到上一节的脱敏响应。不要新增依赖。

Stage B 需要新增、而当前会通过或尚未覆盖的正向测试：

- 匹配的专业版 PDF 归档一次，写出 `meta.json`，旧版本字节不变。
- 该有效 PDF 已存在时，`check_updates` 不再调用下载，也不改写文件。
- `text/html` 且登录失败时仍然不写文件。这条今天已经成立，修复时不能退回。

## 回滚与本地验收

本 PR 只有测试、合成 fixture 和本报告。回滚这个提交即可恢复生产代码，不涉及状态或归档迁移。

Stage B 之后的真实验收放在 MBP16 上，由用户既有授权执行：

- 使用隔离的输出目录和状态文件，把 `archive_dir` / `state_file` 指到空目录，或指向生产数据的副本。第一次不要指向 `~/.nccn-monitor/archive` 的正式目录。
- 目标是那 3 份已经在官方站点手工下过的专业版 PDF。验收时核对文件以 `%PDF` 开头、指南名和版本与目标一致，并且不是患者指南。
- 不把浏览器会话、cookie 或口令交给云端。认证仍走公开网站上的普通登录表单。
- 正式归档里已有的 PDF 保持原路径和原字节。新版本只追加。若隔离副本里某个标准文件名上已经是 HTML，先把该 HTML 挪到旁边再写入通过校验的 PDF，不要删除唯一副本，也不要改写其他版本目录。
- 隔离状态里版本已经是新版本、PDF 仍缺失时，再跑一次必须继续尝试下载。有效 PDF 写好之后，再跑一次必须跳过该文件且不覆盖它。
- 若需要回滚 Stage B 代码，已有正式 PDF 不受影响。已经前进的状态版本号不会因为回滚代码而自动退回；缺失 PDF 的重试必须在版本号已经写过的状态下仍然可用，这正是预置状态那条测试的要求。

## 停止点

Stage A 到此结束。请 CASE 和编码评审先看失败测试与本边界，再决定生产实现。在那之前不要修改 `src/nccn_monitor/`。
