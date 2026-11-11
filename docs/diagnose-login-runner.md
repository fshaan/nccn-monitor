# 登录诊断运行器

云端没有执行真实登录。认证原因仍然未知。周检也还没有在那台机器上替换原脚本。

## 退出码不是同一件事

- `check_and_download` 返回 1：至少归档了一份 PDF。
- 这个诊断进程退出码 0：只表示打印了一份结构化诊断，不是登录成功，也不是归档成功。
- pytest 进程退出码 0：测试运行器成功结束，不是周检返回值。

## 返回字段

只允许 `status_code`、`host_class`（`nccn` 或 `other`）、`path_class`（`login`、`known-root` 或 `other`）、`content_type`（允许的 media type，否则 `other`）、`has_login_form`、`has_account`、`has_logout`。失败时可以多一个 `error`，只能是 `credentials_not_configured` 或 `request_failed`。

不返回原始 host、path、query、header、cookie、token、页面或异常文本。`/login/Index` 归类为 `login`，`/` 归类为 `known-root`，其它路径一律 `other`。`nccn.org` 与 `www.nccn.org` 归类为 `nccn`，其它主机为 `other`。

调用期间丢弃全部日志，结束后恢复原来的 logging 禁用阈值。`Referer` 固定为 `https://www.nccn.org/`，不使用响应 URL。`login()` 的成功判断没有改。TLS 校验保持开启。

## 本地命令

在隔离副本里运行，不要在生产检出里跑，也不要覆盖 `~/.hermes/scripts/nccn_weekly_check.py`。不要加参数，不要 `set -x`，不要把口令放进命令行或环境变量。配置仍由脚本按周检的同一顺序自己读取，包括原样保留的 `/Users/[REDACTED]/Workspace/devs/nccn_watcher/config.yaml`。不要猜测被删掉的用户名。

```bash
python scripts/diagnose_nccn_login.py
```

进程退出码 0 表示打印了诊断；退出码 2 表示没有可用凭据或请求失败。父流程的编码评审先看这个运行器，然后才可以做一次授权的本机测试。本机上未提交的 `downloader.py` / `scraper.py` 不要并入，也不要关掉 TLS。

## 这次诊断测试输出

pytest 进程退出码 0 只表示这些测试通过。没有对 NCCN 发起登录。

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
collecting ... collected 4 items

tests/test_login_diagnostic.py::test_path_and_query_secrets_stay_out_of_diagnostic PASSED [ 25%]
tests/test_login_diagnostic.py::test_transport_errors_do_not_leak_and_logging_is_restored PASSED [ 50%]
tests/test_login_diagnostic.py::test_diagnostic_runner_without_config_prints_only_allowlisted_error PASSED [ 75%]
tests/test_auth_download_regression.py::test_login_diagnostic_returns_only_safe_fields PASSED [100%]

============================== 4 passed in 0.36s ===============================
```
