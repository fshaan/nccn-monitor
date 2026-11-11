# 周检入口与本地脏差异

原 wrapper 工作区 SHA-256 是 `bd134c5fd9ba2b76a86abd7128ec83e6f4178112346d58e2e89dc737671a0801`（4698 字节）。脱敏副本只把两处路径里的用户名换成了 `/Users/[REDACTED]/`。仓库里的 `scripts/nccn_weekly_check.py` 原样保留这两处占位，不猜测用户名，也不写回那台机器。

`check_and_download` 的可维护实现在 `nccn_monitor.weekly`。shim 只保留原来的路径引导、配置加载、`--dry-run` 和 `sys.exit`。下载补档逻辑不在 shim 里再写一份。

## 与原脚本一致的部分

- 抓取失败返回 2。
- 第一次建立基线：`detect_changes` 返回空列表，返回 0，不下载。
- `--dry-run` 不下载，返回 0。
- 至少一份 PDF 归档成功返回 1；需要下载但全部失败返回 2。
- `detect_changes` 的空列表仍然只表示比较过的版本没有变化。

基线已经存在、版本没变、但当前版本没有有效专业版 PDF 时，原脚本返回 0。库内入口会再下载这一份。这是这次要修的周检缺口。已有但不匹配的 `%PDF` 只记录 `blocked-invalid-existing pending manual disposition`，不调用下载；这种情况下没有成功归档时返回 2。

## 不要并入的本地脏差异

downloader 工作区相对其 HEAD 只多了三处：`httpx.AsyncClient(..., verify=False)`，把 HTML 判断扩成 `text/html` 或 `charset=` 并且正文含 `login` 或 URL 含 `/login`，以及 `logger.error` 增加 `url=%s` 和 `resp.url`。scraper 工作区在三处 `AsyncClient` 上加了 `verify=False`。

候选保持 TLS 校验，没有 `verify=False`，诊断和报告也不输出完整 URL、query 或 headers。这些脏文件仍留在本机工作区，本仓库不覆盖、不合并、不部署。

把那份 downloader 脏 diff 套到当前候选上会对不上：候选的 `download_and_archive` 已经改成正文校验和禁止覆盖已有 `%PDF`，而脏 diff 的上下文还是「文件非空就当作已归档」。scraper 的 `verify=False` 行和详情页选链改动位置不同，也不能靠关闭校验来通过测试。

## 认证

wrapper 不直接调用 `login()`。登录发生在 `download_and_archive` 内部。脱敏材料和脏 diff 都没有那次 httpx 响应的状态码、去 query 的 path、Content-Type 或登录表单 / Account Settings / Log Out 布尔值。`diagnose_login` 仍是给授权本地运行的观察入口。认证原因仍然未知。


## 周检路径的红灯再绿灯

红灯时，`check_and_download` 仍按脱敏源码在 `detect_changes` 为空时返回 0。状态里已经是 Gastric Cancer `2.2026`，有效 PDF 不存在。命令 exit 1。

```
/workspace/.venv/lib/python3.12/site-packages/pytest_asyncio/plugin.py:300: PytestDeprecationWarning: The configuration option "asyncio_default_fixture_loop_scope" is unset.
The event loop scope for asynchronous fixtures will default to the "fixture" caching scope. Future versions of pytest-asyncio will default the loop scope for asynchronous fixtures to "function" scope. Set the default fixture loop scope explicitly in order to avoid unexpected behavior in the future. Valid fixture loop scopes are: "function", "class", "module", "package", "session"

  warnings.warn(PytestDeprecationWarning(_DEFAULT_FIXTURE_LOOP_SCOPE_UNSET))
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.2.0, pluggy-1.7.0 -- /workspace/.venv/bin/python
cachedir: .pytest_cache
rootdir: /workspace
configfile: pyproject.toml
plugins: asyncio-1.4.1.post1, anyio-4.16.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 1 item

tests/test_weekly_check.py::test_wrapper_path_retries_recorded_version_when_valid_pdf_is_missing FAILED [100%]

=================================== FAILURES ===================================
_____ test_wrapper_path_retries_recorded_version_when_valid_pdf_is_missing _____
tests/test_weekly_check.py:90: in test_wrapper_path_retries_recorded_version_when_valid_pdf_is_missing
    assert code == 1
E   assert 0 == 1
=========================== short test summary info ============================
FAILED tests/test_weekly_check.py::test_wrapper_path_retries_recorded_version_when_valid_pdf_is_missing
============================== 1 failed in 0.14s ===============================
```

接上 `archive_followups_for_recorded_versions` 之后，同一条 pytest 进程退出码是 0，表示测试通过。这和周检函数返回 1 不是同一件事：函数返回 1 只表示至少归档了一份 PDF。随后整套 pytest 也是进程退出码 0，`69 passed`。

```
/workspace/.venv/lib/python3.12/site-packages/pytest_asyncio/plugin.py:300: PytestDeprecationWarning: The configuration option "asyncio_default_fixture_loop_scope" is unset.
The event loop scope for asynchronous fixtures will default to the "fixture" caching scope. Future versions of pytest-asyncio will default the loop scope for asynchronous fixtures to "function" scope. Set the default fixture loop scope explicitly in order to avoid unexpected behavior in the future. Valid fixture loop scopes are: "function", "class", "module", "package", "session"

  warnings.warn(PytestDeprecationWarning(_DEFAULT_FIXTURE_LOOP_SCOPE_UNSET))
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.2.0, pluggy-1.7.0 -- /workspace/.venv/bin/python
cachedir: .pytest_cache
rootdir: /workspace
configfile: pyproject.toml
plugins: asyncio-1.4.1.post1, anyio-4.16.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 1 item

tests/test_weekly_check.py::test_wrapper_path_retries_recorded_version_when_valid_pdf_is_missing PASSED [100%]

============================== 1 passed in 0.12s ===============================
```
