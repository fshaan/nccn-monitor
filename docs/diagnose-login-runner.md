# 登录诊断隔离产物

云端没有执行真实登录。认证原因仍然未知。每周原脚本没有在本机被替换。不要把带 `[REDACTED]` 的路径猜成真实用户名，也不要覆盖 `~/.hermes/scripts/nccn_weekly_check.py` 或本机脏的 `downloader.py` / `scraper.py`。TLS 校验保持开启。

## 退出码

- 周检函数 `check_and_download` 返回 1：至少归档了一份 PDF。
- 本诊断进程退出码 0：只表示打印了一行白名单 JSON，不是登录成功，也不是归档成功。
- pytest 进程退出码 0：测试运行器成功结束。上面两条都不是这个意思。

## 三份固定 blob

装配只允许这三份已经过方法层审查、并含本轮运行器修复的文件。不要做整仓 checkout，不要放进生产检出、`~/.hermes/scripts/` 或归档目录。`$ISOLATE` 是隔离目录。

| 隔离路径 | git blob |
| --- | --- |
| `$ISOLATE/scripts/diagnose_nccn_login.py` | `c287b0ca348dcc5826c8ac8c4df6450a2325deb9` |
| `$ISOLATE/src/nccn_monitor/__init__.py` | `da9ae4c80b8b962cb8564294c6cf3f9fe20c4225` |
| `$ISOLATE/src/nccn_monitor/downloader.py` | `8a5c9b3247ac51e02c05a526d4b7bfa9b03a9e59` |

`8345886` 上的运行器 blob `fc3141a39c538eca76f810896d251f3f0ef2f420` 已被本轮替换。downloader 与 `__init__.py` 的 blob 没有变。

核对命令（不要在这条命令里实例化 downloader，也不要发网络请求）：

```bash
git hash-object "$ISOLATE/scripts/diagnose_nccn_login.py"
git hash-object "$ISOLATE/src/nccn_monitor/__init__.py"
git hash-object "$ISOLATE/src/nccn_monitor/downloader.py"
PYTHONPATH="$ISOLATE/src" "$PYTHON" -c "import nccn_monitor.downloader as d, inspect, pathlib; print(pathlib.Path(inspect.getfile(d)).resolve())"
"$PYTHON" -c "import httpx, bs4, yaml; print(httpx.__version__)"
```

前三行必须依次是上面的三个 blob。打印的模块路径必须是 `$ISOLATE/src/nccn_monitor/downloader.py`。运行器还会把自己旁边的 `src` 插到 `sys.path` 最前，避免生产仓的可编辑安装悄悄载入 dirty 模块。不要使用 `/Users/f.sh/Workspace/devs/nccn_watcher/.venv`，除非核实结果就是这份隔离副本。

## 一次诊断命令

评审确认 blob 之后，才可以做一次不超过客户端已有 60 秒超时的本机诊断。不要加参数，不要 `set -x`，不要改 `HOME`，不要把配置复制进 `$ISOLATE`，不要把口令放进命令行或环境变量。

```bash
PYTHONPATH="$ISOLATE/src" "$PYTHON" "$ISOLATE/scripts/diagnose_nccn_login.py"
```

stdout 只能是一行白名单 JSON。stderr 若非空，整次输出视为可能污染，不要写入对外报告。`/Users/[REDACTED]/Workspace/devs/nccn_watcher/config.yaml` 保持占位。找不到已有配置时，预期是 `credentials_not_configured` 和退出码 2。YAML 或关闭失败时是 `request_failed` 和退出码 2，stderr 不带 traceback。

## 本仓库没有 CI

没有 `.github` 工作流，也没有既有的 Check Run 惯例。本轮不新增 GitHub Actions 或其它付费检查服务。下面是在将要提交的工作区文件上执行的 pytest 输出，供评审对同一 blob 复跑；它还不是第三方 CI 日志。

红灯（运行器修复之前，3 failed，1 passed）：坏 YAML 的 stderr 含 Traceback 和配置路径；`PYTHONPATH` 上的 dirty 模块被导入；`close()` 抛出的异常冒出进程。`test_runner_does_not_create_state_or_pdf` 当时已经通过。

绿灯命令：

```bash
.venv/bin/python -m pytest tests/test_login_diagnostic.py tests/test_auth_download_regression.py::test_login_diagnostic_returns_only_safe_fields -v --tb=short
```

pytest 进程退出码 0。这不是周检返回 1，也不是诊断进程退出码 0。

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
collecting ... collected 8 items

tests/test_login_diagnostic.py::test_path_and_query_secrets_stay_out_of_diagnostic PASSED [ 12%]
tests/test_login_diagnostic.py::test_transport_errors_do_not_leak_and_logging_is_restored PASSED [ 25%]
tests/test_login_diagnostic.py::test_diagnostic_runner_without_config_prints_only_allowlisted_error PASSED [ 37%]
tests/test_login_diagnostic.py::test_yaml_failure_stdout_is_allowlisted_and_stderr_has_no_traceback PASSED [ 50%]
tests/test_login_diagnostic.py::test_runner_loads_script_src_not_pythonpath_dirty_module PASSED [ 62%]
tests/test_login_diagnostic.py::test_runner_does_not_create_state_or_pdf PASSED [ 75%]
tests/test_login_diagnostic.py::test_close_failure_does_not_print_traceback PASSED [ 87%]
tests/test_auth_download_regression.py::test_login_diagnostic_returns_only_safe_fields PASSED [100%]

============================== 8 passed in 0.72s ===============================
```
