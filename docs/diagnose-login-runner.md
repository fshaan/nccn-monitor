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
| `$ISOLATE/scripts/diagnose_nccn_login.py` | `b9005212d3de6e6733f6de2527ed2b49ff3bec3f` |
| `$ISOLATE/src/nccn_monitor/__init__.py` | `da9ae4c80b8b962cb8564294c6cf3f9fe20c4225` |
| `$ISOLATE/src/nccn_monitor/downloader.py` | `b9536715c285d19958d5908956905a97346971e8` |

`ce9c78c5` 的 downloader blob `8d0533fa52551e5958d56e79831729f26c6f7734` 仍会宣传 `br`，不能再用于下一次诊断。运行器和 `__init__.py` 的 blob 这次没变。`login()` 的成功判断没变。

## 这次新增的观测字段

最终响应仍用原来的 `status_code`、`host_class`、`path_class`、`content_type` 和三个布尔值。GET 与最终响应分开命名：

- `observed_stage`：`not-reached`、`get`、`post`
- `get_form_action_class`：`not-decoded`、`absent`、`exact-relative`、`slash-or-case-variant`、`absolute-nccn`、`other`
- `get_password_control`：`not-decoded`、`absent`、`type-password`、`other-type`
- `get_username_control`：`not-decoded`、`absent`、`present`
- `get_hidden_count_class`：`not-decoded`、`zero`、`one`、`several`
- `get_challenge_class`：`not-decoded`、`none`、`captcha-marker`、`interstitial-marker`
- `get_content_encoding_class` 与 `final_content_encoding_class`：`absent`、`gzip`、`deflate`、`br`、`other`
- `get_body_decodable`、`brotli_decoder_present`：布尔

GET 上只要识别到 challenge，诊断立刻返回，不提交凭据。生产 `login()` 仍会按原条件找表单。没有 brotli 且 GET 编码是 `br` 时，正文标成不可解码，也不提交。这些都只是观测。

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

## 编码协商与这次测试记录

第二次隔离诊断（head `ce9c78c5403b07ad7772427339a2870c44bf12d4`，解释器 `/opt/homebrew/bin/python3`，无 brotli）得到 `observed_stage=get`、`get_content_encoding_class=br`、`get_body_decodable=false`。客户端当时写死 `Accept-Encoding: gzip, deflate, br`。这次只删掉这层写死，把编码协商交回 httpx 的默认值，也就是只宣传当前解释器能解码的编码。没有安装新包，没有改 `login()`。

下一次本机诊断仍用隔离三文件和 60 秒总限。若 GET 的 `get_challenge_class` 是 `captcha-marker` 或 `interstitial-marker`，应看到 `observed_stage=get` 且没有 POST，并立即停止，不要把它解释成密码错误。若编码不再是 `br` 且 `get_body_decodable=true`，才够看表单分类。生产仓 `.venv` 有没有 brotli 是本机非网络探查，命令只检查模块是否存在，不读配置、不登录、不改本机源码：

```bash
/Users/f.sh/Workspace/devs/nccn_watcher/.venv/bin/python -c "import importlib.util; print('brotli' if importlib.util.find_spec('brotli') or importlib.util.find_spec('brotlicffi') else 'no-brotli')"
```

本仓库没有 GitHub Actions。下面两段是这次工作区命令的原始输出，不是第三方独验。红灯绑定的是仍含 `Accept-Encoding: gzip, deflate, br` 的 downloader。绿灯绑定的提交是 `d1cb7995f79003a1e28c2fe310390a18d5d081f3`。其中 downloader blob 是 `b9536715c285d19958d5908956905a97346971e8`，运行器 blob 是 `b9005212d3de6e6733f6de2527ed2b49ff3bec3f`，`__init__.py` blob 是 `da9ae4c80b8b962cb8564294c6cf3f9fe20c4225`。这是本工作区执行，不是第三方 CI 独验。先前文档把 8 条旧会话标成 12 passed，那次转录作废。

### 红灯

```bash
.venv/bin/python -m pytest tests/test_login_diagnostic.py::test_accept_encoding_follows_httpx_decoders_and_omits_unsupported_br --tb=short -q
```

进程退出码 1。

```
/workspace/.venv/lib/python3.12/site-packages/pytest_asyncio/plugin.py:300: PytestDeprecationWarning: The configuration option "asyncio_default_fixture_loop_scope" is unset.
The event loop scope for asynchronous fixtures will default to the "fixture" caching scope. Future versions of pytest-asyncio will default the loop scope for asynchronous fixtures to "function" scope. Set the default fixture loop scope explicitly in order to avoid unexpected behavior in the future. Valid fixture loop scopes are: "function", "class", "module", "package", "session"

  warnings.warn(PytestDeprecationWarning(_DEFAULT_FIXTURE_LOOP_SCOPE_UNSET))
F                                                                        [100%]
=================================== FAILURES ===================================
_____ test_accept_encoding_follows_httpx_decoders_and_omits_unsupported_br _____
tests/test_login_diagnostic.py:456: in test_accept_encoding_follows_httpx_decoders_and_omits_unsupported_br
    assert "Accept-Encoding" not in BROWSER_HEADERS
E   AssertionError: assert 'Accept-Encoding' not in {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0....xml,application/xml;q=0.9,*/*;q=0.8', 'Accept-Language': 'en-US,en;q=0.9', 'Accept-Encoding': 'gzip, deflate, br', ...}
=========================== short test summary info ============================
FAILED tests/test_login_diagnostic.py::test_accept_encoding_follows_httpx_decoders_and_omits_unsupported_br
1 failed in 0.15s
```

### 绿灯

```bash
.venv/bin/python -m pytest tests/test_login_diagnostic.py tests/test_auth_download_regression.py tests/test_weekly_check.py tests/test_archive.py tests/test_state.py tests/test_scraper.py tests/test_health.py -v --tb=line
```

进程退出码 0。这不是周检函数返回 1，也不是诊断进程退出码 0。

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
collecting ... collected 81 items

tests/test_login_diagnostic.py::test_path_and_query_secrets_stay_out_of_diagnostic PASSED [  1%]
tests/test_login_diagnostic.py::test_transport_errors_do_not_leak_and_logging_is_restored PASSED [  2%]
tests/test_login_diagnostic.py::test_diagnostic_runner_without_config_prints_only_allowlisted_error PASSED [  3%]
tests/test_login_diagnostic.py::test_yaml_failure_stdout_is_allowlisted_and_stderr_has_no_traceback PASSED [  4%]
tests/test_login_diagnostic.py::test_runner_loads_script_src_not_pythonpath_dirty_module PASSED [  6%]
tests/test_login_diagnostic.py::test_runner_does_not_create_state_or_pdf PASSED [  7%]
tests/test_login_diagnostic.py::test_close_failure_does_not_print_traceback PASSED [  8%]
tests/test_login_diagnostic.py::test_observed_stage_is_post_only_after_exact_form_submit PASSED [  9%]
tests/test_login_diagnostic.py::test_action_classes_do_not_submit_unless_exact_relative PASSED [ 11%]
tests/test_login_diagnostic.py::test_br_without_decoder_does_not_post PASSED [ 12%]
tests/test_login_diagnostic.py::test_accept_encoding_follows_httpx_decoders_and_omits_unsupported_br PASSED [ 13%]
tests/test_login_diagnostic.py::test_challenge_marker_does_not_post_credentials PASSED [ 14%]
tests/test_auth_download_regression.py::test_detail_page_skips_patient_link_listed_before_professional PASSED [ 16%]
tests/test_auth_download_regression.py::test_detail_page_returns_none_when_only_patient_guide_is_listed PASSED [ 17%]
tests/test_auth_download_regression.py::test_detail_page_fallback_skips_patient_and_blocks_filenames PASSED [ 18%]
tests/test_auth_download_regression.py::test_download_and_archive_rejects_html_patient_wrong_title_or_version[auth/login_wall.html-https://www.nccn.org/professionals/physician_gls/pdf/gastric.pdf] PASSED [ 19%]
tests/test_auth_download_regression.py::test_download_and_archive_rejects_html_patient_wrong_title_or_version[pdf/patient_stomach.pdf-https://www.nccn.org/patients/guidelines/content/PDF/stomach-patient.pdf] PASSED [ 20%]
tests/test_auth_download_regression.py::test_download_and_archive_rejects_html_patient_wrong_title_or_version[pdf/professional_breast_v2_2026.pdf-https://www.nccn.org/professionals/physician_gls/pdf/gastric.pdf] PASSED [ 22%]
tests/test_auth_download_regression.py::test_download_and_archive_rejects_html_patient_wrong_title_or_version[pdf/professional_gastric_v1_2025.pdf-https://www.nccn.org/professionals/physician_gls/pdf/gastric.pdf] PASSED [ 23%]
tests/test_auth_download_regression.py::test_existing_login_html_named_as_pdf_is_not_archived_completion PASSED [ 24%]
tests/test_auth_download_regression.py::test_non_pdf_occupant_can_be_replaced_by_matching_professional_pdf PASSED [ 25%]
tests/test_auth_download_regression.py::test_compressed_professional_cover_with_patient_crosslink_is_archived PASSED [ 27%]
tests/test_auth_download_regression.py::test_existing_invalid_pdf_is_blocked_and_not_replaced[pdf/professional_breast_v2_2026.pdf-None] PASSED [ 28%]
tests/test_auth_download_regression.py::test_existing_invalid_pdf_is_blocked_and_not_replaced[pdf/professional_gastric_v1_2025.pdf-None] PASSED [ 29%]
tests/test_auth_download_regression.py::test_existing_invalid_pdf_is_blocked_and_not_replaced[-%PDF-1.4\n%truncated\n] PASSED [ 30%]
tests/test_auth_download_regression.py::test_legacy_valid_professional_pdf_stays_completed_and_unchanged PASSED [ 32%]
tests/test_auth_download_regression.py::test_check_updates_reports_blocked_existing_pdf_without_replacement PASSED [ 33%]
tests/test_auth_download_regression.py::test_login_diagnostic_returns_only_safe_fields PASSED [ 34%]
tests/test_auth_download_regression.py::test_check_updates_retries_when_recorded_version_has_no_pdf PASSED [ 35%]
tests/test_auth_download_regression.py::test_check_updates_retries_after_download_failure PASSED [ 37%]
tests/test_weekly_check.py::test_wrapper_path_retries_recorded_version_when_valid_pdf_is_missing PASSED [ 38%]
tests/test_weekly_check.py::test_first_baseline_returns_zero_without_download PASSED [ 39%]
tests/test_weekly_check.py::test_dry_run_with_version_change_does_not_download PASSED [ 40%]
tests/test_weekly_check.py::test_blocked_existing_pdf_is_not_replaced_and_exits_error PASSED [ 41%]
tests/test_weekly_check.py::test_scrape_failure_returns_2 PASSED         [ 43%]
tests/test_weekly_check.py::test_shim_preserves_redacted_paths_and_original_hash PASSED [ 44%]
tests/test_weekly_check.py::test_candidate_keeps_tls_verification_enabled PASSED [ 45%]
tests/test_archive.py::test_get_archived_versions_empty PASSED           [ 46%]
tests/test_archive.py::test_get_archived_versions_with_meta PASSED       [ 48%]
tests/test_archive.py::test_get_archived_versions_multiple PASSED        [ 49%]
tests/test_archive.py::test_get_archived_versions_pdf_only_no_meta PASSED [ 50%]
tests/test_state.py::test_first_run_returns_no_changes PASSED            [ 51%]
tests/test_state.py::test_detects_version_change PASSED                  [ 53%]
tests/test_state.py::test_no_changes_returns_empty PASSED                [ 54%]
tests/test_state.py::test_watch_list_filters_results PASSED              [ 55%]
tests/test_state.py::test_watch_list_case_insensitive PASSED             [ 56%]
tests/test_state.py::test_new_guideline_added_later PASSED               [ 58%]
tests/test_state.py::test_state_persists_to_disk PASSED                  [ 59%]
tests/test_scraper.py::test_parse_category_page_extracts_all_items PASSED [ 60%]
tests/test_scraper.py::test_parse_category_page_extracts_versions PASSED [ 61%]
tests/test_scraper.py::test_parse_category_page_builds_detail_urls PASSED [ 62%]
tests/test_scraper.py::test_parse_category_page_sets_category PASSED     [ 64%]
tests/test_scraper.py::test_parse_category_page_both_columns PASSED      [ 65%]
tests/test_scraper.py::test_parse_category_page_empty_raises PASSED      [ 66%]
tests/test_scraper.py::test_parse_recently_published_extracts_all_guidelines PASSED [ 67%]
tests/test_scraper.py::test_parse_recently_published_extracts_versions PASSED [ 69%]
tests/test_scraper.py::test_parse_recently_published_tracks_categories PASSED [ 70%]
tests/test_scraper.py::test_parse_empty_html_raises_scrape_error PASSED  [ 71%]
tests/test_scraper.py::test_parse_detail_page_extracts_main_pdf PASSED   [ 72%]
tests/test_scraper.py::test_parse_detail_page_skips_blocks_and_patient PASSED [ 74%]
tests/test_scraper.py::test_parse_detail_page_no_pdf PASSED              [ 75%]
tests/test_scraper.py::test_slugify_basic PASSED                         [ 76%]
tests/test_scraper.py::test_slugify_colon PASSED                         [ 77%]
tests/test_scraper.py::test_slugify_slash PASSED                         [ 79%]
tests/test_scraper.py::test_slugify_parentheses PASSED                   [ 80%]
tests/test_scraper.py::test_slugify_special_chars PASSED                 [ 81%]
tests/test_scraper.py::test_slugify_all_92_guidelines_unique PASSED      [ 82%]
tests/test_scraper.py::test_format_pdf_filename_basic PASSED             [ 83%]
tests/test_scraper.py::test_format_pdf_filename_multi_word PASSED        [ 85%]
tests/test_scraper.py::test_format_pdf_filename_colon PASSED             [ 86%]
tests/test_scraper.py::test_format_pdf_filename_slash PASSED             [ 87%]
tests/test_scraper.py::test_format_pdf_filename_hyphen PASSED            [ 88%]
tests/test_scraper.py::test_format_pdf_filename_parentheses PASSED       [ 90%]
tests/test_health.py::test_starts_healthy PASSED                         [ 91%]
tests/test_health.py::test_stays_healthy_on_success PASSED               [ 92%]
tests/test_health.py::test_single_failure_no_alert PASSED                [ 93%]
tests/test_health.py::test_threshold_triggers_alert PASSED               [ 95%]
tests/test_health.py::test_alert_only_fires_once PASSED                  [ 96%]
tests/test_health.py::test_success_resets_failure_counter PASSED         [ 97%]
tests/test_health.py::test_status_summary_healthy PASSED                 [ 98%]
tests/test_health.py::test_status_summary_unhealthy PASSED               [100%]

============================== 81 passed in 0.93s ==============================
```
