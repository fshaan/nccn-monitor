# 登录页结构观察（只读候选）

云端没有访问公开登录页，没有 POST，没有读配置，没有加载凭据，也没有实例化带凭据的下载器。生产 `login()` 和 `diagnose_login()` 都没有改。`src/nccn_monitor/downloader.py` 的 blob 仍是 `b9536715c285d19958d5908956905a97346971e8`。

这是取证候选，不是放行。任何 `structure_class` 的 `post_admitted` 都是 false。`static-reference`、`unknown`、`none-visible` 和 `challenge-structure` 都不允许 POST。结构分层不改变既有诊断的停止规则：整页子串仍是 `captcha-marker` 时，`diagnose_login()` 继续在 GET 后停下。

09:55 那次响应没有保留，不能用这次代码回头改写当时的 `captcha-marker`。生产仓 `.venv` 能找到 brotli，隔离解释器不能。那次 `br` 不是生产认证根因。

## 输出里有什么

只输出枚举、布尔和有界计数。不输出 HTML、属性、URL、字段名或字段值。

| 字段 | 允许值 |
| --- | --- |
| `structure_class` | `static-reference`、`challenge-structure`、`unknown`、`none-visible`、`not-decoded` |
| `substring_marker_class` | `captcha-marker`、`interstitial-marker`、`none`、`not-decoded`。这是整页子串，不是结构证明 |
| `static_text_role` | `comment`、`footer`、`prose`、`error`、`mixed`、`absent` |
| `unknown_reason` | `script-only`、`empty-container`、`script-and-empty`、`dynamic-comment`、`insufficient`、`absent` |
| 五个计数字段 | `zero`、`one`、`several`、`not-decoded` |
| `post_admitted` | 恒为 false |
| `observed_stage` | `get` 或 `not-reached`。没有 `post` |
| `status_class` | `ok`、`redirect`、`client-error`、`server-error`、`other`、`not-reached` |

`static-reference` 只来自注释、页脚、`<small>`、`<p>` 或错误区里的文句，并且页面上没有供应商脚本、空的动态容器、绑定登录表单的控件或挑战 iframe。只有脚本，或只有空容器，必须是 `unknown`，不能写成静态引用，也不能写成 `none-visible`。

登录表单里的控件或 iframe，以及表单外带这些标记的 iframe / 容器，是 `challenge-structure`。空的 `cf-challenge` 容器仍是 `unknown`。只有 “Just a moment” 这类整页文句、没有对应结构时，子串可以是 `interstitial-marker`，结构类是 `unknown`。

这些都不是「服务端不会要求挑战」的证明。无标记的外部 iframe、不含这些词的脚本、以及提交之后才出现的校验，这一次 GET 的 HTML 看不到。`none-visible` 只表示这份 HTML 里没有上述信号。

## 三份固定 blob

隔离目录只放这三份。不要放 `downloader.py`，不要整仓 checkout，不要覆盖 `~/.hermes/scripts/nccn_weekly_check.py`。

| 隔离路径 | git blob |
| --- | --- |
| `$ISOLATE/scripts/observe_login_structure.py` | `76410b0f631f243c220afaa23216cbe0d1b2b026` |
| `$ISOLATE/src/nccn_monitor/__init__.py` | `da9ae4c80b8b962cb8564294c6cf3f9fe20c4225` |
| `$ISOLATE/src/nccn_monitor/login_structure.py` | `1c209632d9de9a2faae43c35ed3cd53163b4b660` |

核对时不要发网络请求，也不要调用收集函数：

```bash
git hash-object "$ISOLATE/scripts/observe_login_structure.py"
git hash-object "$ISOLATE/src/nccn_monitor/__init__.py"
git hash-object "$ISOLATE/src/nccn_monitor/login_structure.py"
```

## 精确命令

脚本没有参数。60 秒总限由已有的 `timeout` 包在外面。客户端单次超时也是 60 秒，不跟随重定向，所以一次进程最多一个 GET。编码交给 httpx 默认协商，不写 `Accept-Encoding`。TLS 保持开启。请求头与已审的 `BROWSER_HEADERS` 相同。

评审确认上面三枚 blob 之前，不要执行。

```bash
timeout 60 env -u PYTHONPATH PYTHONPATH="$ISOLATE/src" "$PYTHON" "$ISOLATE/scripts/observe_login_structure.py"
```

进程退出码 0 只表示打出了一行白名单 JSON。不是登录成功，不是允许 POST，也不是归档了一份 PDF。退出码 2 是这一次 GET 或本地准备失败。周检函数返回 1 才表示归档了 PDF。pytest 退出码 0 只表示测试运行器结束。

如果响应是 30x，结果只描述这一跳，不再请求下一跳。那是把请求次数钉在 1，不是绕过。结构证据因此可能不完整。

## 红灯

红灯把整页子串直接猜成 `challenge-structure`，计数保持为零。这段猜测没有留在提交里。pytest 进程退出码 1。36 failed，15 passed。下面是断言差和失败名单。重复的差都是同一类：静态文句或 `unknown` 被猜成了 `challenge-structure`，或者控件计数仍是 `zero`。

```bash
.venv/bin/python -m pytest tests/test_login_structure.py --tb=line -q
```

```
E   AssertionError: assert 'challenge-structure' == 'static-reference'
      
      - static-reference
      + challenge-structure
/workspace/tests/test_login_structure.py:100: AssertionError: assert 'challenge-structure' == 'static-reference'
```

```
FAILED tests/test_login_structure.py::test_static_regions_are_references_not_challenge_structure[html0-comment]
FAILED tests/test_login_structure.py::test_static_regions_are_references_not_challenge_structure[html1-footer]
FAILED tests/test_login_structure.py::test_static_regions_are_references_not_challenge_structure[html2-footer]
FAILED tests/test_login_structure.py::test_static_regions_are_references_not_challenge_structure[html3-prose]
FAILED tests/test_login_structure.py::test_static_regions_are_references_not_challenge_structure[html4-error]
FAILED tests/test_login_structure.py::test_comment_and_paragraph_together_are_mixed_static_reference
FAILED tests/test_login_structure.py::test_bound_form_control_is_challenge_structure_and_does_not_admit_post[hidden]
FAILED tests/test_login_structure.py::test_bound_form_control_is_challenge_structure_and_does_not_admit_post[textarea]
FAILED tests/test_login_structure.py::test_bound_form_control_is_challenge_structure_and_does_not_admit_post[button]
FAILED tests/test_login_structure.py::test_bound_form_control_is_challenge_structure_and_does_not_admit_post[select]
FAILED tests/test_login_structure.py::test_bound_form_control_is_challenge_structure_and_does_not_admit_post[iframe]
FAILED tests/test_login_structure.py::test_two_form_controls_count_as_several
FAILED tests/test_login_structure.py::test_form_iframe_without_marker_is_still_challenge_structure
FAILED tests/test_login_structure.py::test_outside_frame_and_hooked_container_are_challenge_structure
FAILED tests/test_login_structure.py::test_captcha_input_outside_exact_form_is_unknown
FAILED tests/test_login_structure.py::test_script_empty_container_and_unclear_markup_are_unknown[script-src]
FAILED tests/test_login_structure.py::test_script_empty_container_and_unclear_markup_are_unknown[inline-script]
FAILED tests/test_login_structure.py::test_script_empty_container_and_unclear_markup_are_unknown[empty]
FAILED tests/test_login_structure.py::test_script_empty_container_and_unclear_markup_are_unknown[empty-in-form]
FAILED tests/test_login_structure.py::test_script_empty_container_and_unclear_markup_are_unknown[dynamic-comment]
FAILED tests/test_login_structure.py::test_script_empty_container_and_unclear_markup_are_unknown[title]
FAILED tests/test_login_structure.py::test_script_empty_container_and_unclear_markup_are_unknown[meta]
FAILED tests/test_login_structure.py::test_script_empty_container_and_unclear_markup_are_unknown[noscript]
FAILED tests/test_login_structure.py::test_script_and_empty_container_report_both
FAILED tests/test_login_structure.py::test_script_or_empty_container_prevents_static_reference
FAILED tests/test_login_structure.py::test_plain_script_plus_footer_stays_static_reference
FAILED tests/test_login_structure.py::test_hooked_container_with_only_prose_is_unknown
FAILED tests/test_login_structure.py::test_real_control_wins_over_a_vendor_script
FAILED tests/test_login_structure.py::test_interstitial_text_without_structure_is_unknown
FAILED tests/test_login_structure.py::test_interstitial_text_plus_captcha_prose_stays_unknown
FAILED tests/test_login_structure.py::test_empty_interstitial_container_is_unknown_not_a_frame
FAILED tests/test_login_structure.py::test_interstitial_frame_is_challenge_structure
FAILED tests/test_login_structure.py::test_view_scrubs_status_host_path_and_media_parameters
FAILED tests/test_login_structure.py::test_gzip_body_is_classified_without_returning_text
FAILED tests/test_login_structure.py::test_runner_ignores_config_env_and_argv
FAILED tests/test_login_structure.py::test_static_prose_stays_stopped_in_diagnose_login
36 failed, 15 passed in 0.40s
```

## 绿灯

当前分类器。pytest 进程退出码 0。51 passed。这不是观察进程退出码 0，也不是周检返回 1。本仓库没有 GitHub Actions，这不是第三方独验。

```bash
.venv/bin/python -m pytest tests/test_login_structure.py -v --tb=line
```

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
collecting ... collected 51 items

tests/test_login_structure.py::test_static_regions_are_references_not_challenge_structure[html0-comment] PASSED [  1%]
tests/test_login_structure.py::test_static_regions_are_references_not_challenge_structure[html1-footer] PASSED [  3%]
tests/test_login_structure.py::test_static_regions_are_references_not_challenge_structure[html2-footer] PASSED [  5%]
tests/test_login_structure.py::test_static_regions_are_references_not_challenge_structure[html3-prose] PASSED [  7%]
tests/test_login_structure.py::test_static_regions_are_references_not_challenge_structure[html4-error] PASSED [  9%]
tests/test_login_structure.py::test_comment_and_paragraph_together_are_mixed_static_reference PASSED [ 11%]
tests/test_login_structure.py::test_bound_form_control_is_challenge_structure_and_does_not_admit_post[hidden] PASSED [ 13%]
tests/test_login_structure.py::test_bound_form_control_is_challenge_structure_and_does_not_admit_post[textarea] PASSED [ 15%]
tests/test_login_structure.py::test_bound_form_control_is_challenge_structure_and_does_not_admit_post[button] PASSED [ 17%]
tests/test_login_structure.py::test_bound_form_control_is_challenge_structure_and_does_not_admit_post[select] PASSED [ 19%]
tests/test_login_structure.py::test_bound_form_control_is_challenge_structure_and_does_not_admit_post[iframe] PASSED [ 21%]
tests/test_login_structure.py::test_two_form_controls_count_as_several PASSED [ 23%]
tests/test_login_structure.py::test_form_iframe_without_marker_is_still_challenge_structure PASSED [ 25%]
tests/test_login_structure.py::test_outside_frame_and_hooked_container_are_challenge_structure PASSED [ 27%]
tests/test_login_structure.py::test_unmarked_external_iframe_is_not_a_challenge_structure PASSED [ 29%]
tests/test_login_structure.py::test_captcha_input_outside_exact_form_is_unknown PASSED [ 31%]
tests/test_login_structure.py::test_script_empty_container_and_unclear_markup_are_unknown[script-src] PASSED [ 33%]
tests/test_login_structure.py::test_script_empty_container_and_unclear_markup_are_unknown[inline-script] PASSED [ 35%]
tests/test_login_structure.py::test_script_empty_container_and_unclear_markup_are_unknown[empty] PASSED [ 37%]
tests/test_login_structure.py::test_script_empty_container_and_unclear_markup_are_unknown[empty-in-form] PASSED [ 39%]
tests/test_login_structure.py::test_script_empty_container_and_unclear_markup_are_unknown[dynamic-comment] PASSED [ 41%]
tests/test_login_structure.py::test_script_empty_container_and_unclear_markup_are_unknown[title] PASSED [ 43%]
tests/test_login_structure.py::test_script_empty_container_and_unclear_markup_are_unknown[meta] PASSED [ 45%]
tests/test_login_structure.py::test_script_empty_container_and_unclear_markup_are_unknown[noscript] PASSED [ 47%]
tests/test_login_structure.py::test_script_and_empty_container_report_both PASSED [ 49%]
tests/test_login_structure.py::test_script_or_empty_container_prevents_static_reference PASSED [ 50%]
tests/test_login_structure.py::test_plain_script_plus_footer_stays_static_reference PASSED [ 52%]
tests/test_login_structure.py::test_hooked_container_with_only_prose_is_unknown PASSED [ 54%]
tests/test_login_structure.py::test_real_control_wins_over_a_vendor_script PASSED [ 56%]
tests/test_login_structure.py::test_plain_form_is_none_visible_and_does_not_admit_post PASSED [ 58%]
tests/test_login_structure.py::test_interstitial_text_without_structure_is_unknown PASSED [ 60%]
tests/test_login_structure.py::test_interstitial_text_plus_captcha_prose_stays_unknown PASSED [ 62%]
tests/test_login_structure.py::test_empty_interstitial_container_is_unknown_not_a_frame PASSED [ 64%]
tests/test_login_structure.py::test_interstitial_frame_is_challenge_structure PASSED [ 66%]
tests/test_login_structure.py::test_view_scrubs_status_host_path_and_media_parameters PASSED [ 68%]
tests/test_login_structure.py::test_client_error_status_is_an_enum PASSED [ 70%]
tests/test_login_structure.py::test_br_body_is_not_decoded_or_admitted PASSED [ 72%]
tests/test_login_structure.py::test_gzip_body_is_classified_without_returning_text PASSED [ 74%]
tests/test_login_structure.py::test_classifier_failure_does_not_leak_and_stays_get PASSED [ 76%]
tests/test_login_structure.py::test_allowlist_helpers_match_the_reviewed_downloader PASSED [ 78%]
tests/test_login_structure.py::test_client_uses_reviewed_headers_default_encoding_and_one_hop PASSED [ 80%]
tests/test_login_structure.py::test_collect_issues_one_get_and_does_not_follow PASSED [ 82%]
tests/test_login_structure.py::test_get_failure_and_close_failure_do_not_leak PASSED [ 84%]
tests/test_login_structure.py::test_runner_source_has_no_credential_or_post_path PASSED [ 86%]
tests/test_login_structure.py::test_runner_ignores_config_env_and_argv PASSED [ 88%]
tests/test_login_structure.py::test_runner_forces_closed_output PASSED   [ 90%]
tests/test_login_structure.py::test_runner_request_failure_has_no_traceback PASSED [ 92%]
tests/test_login_structure.py::test_runner_pins_import_without_a_network_call PASSED [ 94%]
tests/test_login_structure.py::test_production_login_does_not_call_the_observer PASSED [ 96%]
tests/test_login_structure.py::test_static_prose_stays_stopped_in_diagnose_login PASSED [ 98%]
tests/test_login_structure.py::test_observer_does_not_post_when_diagnose_login_still_would PASSED [100%]

============================== 51 passed in 0.35s ==============================
```

同一工作区再跑既有套件加这一文件，pytest 进程退出码 0，132 passed in 1.18s。先前 81 passed 的转录仍然只覆盖那时的提交，不能把 132 说成已独验。

```bash
.venv/bin/python -m pytest tests/test_login_structure.py tests/test_login_diagnostic.py tests/test_auth_download_regression.py tests/test_weekly_check.py tests/test_archive.py tests/test_state.py tests/test_scraper.py tests/test_health.py -q --tb=line
```

## 仍然阻塞

1. 这三份 blob 还没有在本机跑过。评审前不要执行上面的命令。
2. 就算以后跑了，任何分类都不给 POST。它不能代替每周下载，也不能改 `login()`。
3. 无标记的外部 iframe、不含这些词的脚本，以及提交后才出现的校验，仍看不出来。
4. 原 wrapper 还没替换。本机 `verify=False` 的脏文件不要覆盖。
5. 浏览器里再登一次不会修 httpx。不需要 Frank 重登。
