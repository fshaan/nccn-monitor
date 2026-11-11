# Stage B：已证实机制的最小实现

本文件记录有条件阶段 B。认证原因仍然未知。`login()` 的成功/失败判断没有改。`detect_changes` 返回空列表仍然表示比较过的版本没有变化。没有部署、没有合并、没有读取 MBP 上未提交的 `downloader.py` / `scraper.py`，也没有读取仓外 wrapper 原文。

周检脚本 `~/.hermes/scripts/nccn_weekly_check.py` 的 AST 只导入 `fetch_all_guidelines`、`slugify`、`fetch_pdf_index`、`StateManager`、`NCCNDownloader`，不导入 `server` / `check_updates`。因此本改动里的 `check_updates` 重试不能当作每周脚本已经修好。本轮不臆造 wrapper 的控制流，也不声称周检验收已完成。

## 闸门复跑

复跑发生在实现修改之前，起点是 `aabb6d20a16037fe7f102af027293e45c4c8f631`，其 parent 为远端 `feat/mvp` `07050876277b32cdf3bdeb3a18835cc2b8103603`。这不是阶段 A 文档里的那次叙述。

命令与退出码：

```bash
.venv/bin/python -m pytest tests/test_archive.py tests/test_state.py tests/test_scraper.py tests/test_health.py -v --tb=short
# exit 0
```

```bash
.venv/bin/python -m pytest tests/test_auth_download_regression.py -v --tb=short
# exit 1
```

### 既有测试（红灯复跑时，exit 0）

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
collecting ... collected 44 items

tests/test_archive.py::test_get_archived_versions_empty PASSED           [  2%]
tests/test_archive.py::test_get_archived_versions_with_meta PASSED       [  4%]
tests/test_archive.py::test_get_archived_versions_multiple PASSED        [  6%]
tests/test_archive.py::test_get_archived_versions_pdf_only_no_meta PASSED [  9%]
tests/test_state.py::test_first_run_returns_no_changes PASSED            [ 11%]
tests/test_state.py::test_detects_version_change PASSED                  [ 13%]
tests/test_state.py::test_no_changes_returns_empty PASSED                [ 15%]
tests/test_state.py::test_watch_list_filters_results PASSED              [ 18%]
tests/test_state.py::test_watch_list_case_insensitive PASSED             [ 20%]
tests/test_state.py::test_new_guideline_added_later PASSED               [ 22%]
tests/test_state.py::test_state_persists_to_disk PASSED                  [ 25%]
tests/test_scraper.py::test_parse_category_page_extracts_all_items PASSED [ 27%]
tests/test_scraper.py::test_parse_category_page_extracts_versions PASSED [ 29%]
tests/test_scraper.py::test_parse_category_page_builds_detail_urls PASSED [ 31%]
tests/test_scraper.py::test_parse_category_page_sets_category PASSED     [ 34%]
tests/test_scraper.py::test_parse_category_page_both_columns PASSED      [ 36%]
tests/test_scraper.py::test_parse_category_page_empty_raises PASSED      [ 38%]
tests/test_scraper.py::test_parse_recently_published_extracts_all_guidelines PASSED [ 40%]
tests/test_scraper.py::test_parse_recently_published_extracts_versions PASSED [ 43%]
tests/test_scraper.py::test_parse_recently_published_tracks_categories PASSED [ 45%]
tests/test_scraper.py::test_parse_empty_html_raises_scrape_error PASSED  [ 47%]
tests/test_scraper.py::test_parse_detail_page_extracts_main_pdf PASSED   [ 50%]
tests/test_scraper.py::test_parse_detail_page_skips_blocks_and_patient PASSED [ 52%]
tests/test_scraper.py::test_parse_detail_page_no_pdf PASSED              [ 54%]
tests/test_scraper.py::test_slugify_basic PASSED                         [ 56%]
tests/test_scraper.py::test_slugify_colon PASSED                         [ 59%]
tests/test_scraper.py::test_slugify_slash PASSED                         [ 61%]
tests/test_scraper.py::test_slugify_parentheses PASSED                   [ 63%]
tests/test_scraper.py::test_slugify_special_chars PASSED                 [ 65%]
tests/test_scraper.py::test_slugify_all_92_guidelines_unique PASSED      [ 68%]
tests/test_scraper.py::test_format_pdf_filename_basic PASSED             [ 70%]
tests/test_scraper.py::test_format_pdf_filename_multi_word PASSED        [ 72%]
tests/test_scraper.py::test_format_pdf_filename_colon PASSED             [ 75%]
tests/test_scraper.py::test_format_pdf_filename_slash PASSED             [ 77%]
tests/test_scraper.py::test_format_pdf_filename_hyphen PASSED            [ 79%]
tests/test_scraper.py::test_format_pdf_filename_parentheses PASSED       [ 81%]
tests/test_health.py::test_starts_healthy PASSED                         [ 84%]
tests/test_health.py::test_stays_healthy_on_success PASSED               [ 86%]
tests/test_health.py::test_single_failure_no_alert PASSED                [ 88%]
tests/test_health.py::test_threshold_triggers_alert PASSED               [ 90%]
tests/test_health.py::test_alert_only_fires_once PASSED                  [ 93%]
tests/test_health.py::test_success_resets_failure_counter PASSED         [ 95%]
tests/test_health.py::test_status_summary_healthy PASSED                 [ 97%]
tests/test_health.py::test_status_summary_unhealthy PASSED               [100%]

============================== 44 passed in 0.18s ==============================
```

### 回归测试（红灯复跑时，11 failed，exit 1）

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
collecting ... collected 11 items

tests/test_auth_download_regression.py::test_detail_page_skips_patient_link_listed_before_professional FAILED [  9%]
tests/test_auth_download_regression.py::test_detail_page_returns_none_when_only_patient_guide_is_listed FAILED [ 18%]
tests/test_auth_download_regression.py::test_detail_page_fallback_skips_patient_and_blocks_filenames FAILED [ 27%]
tests/test_auth_download_regression.py::test_download_and_archive_rejects_html_patient_wrong_title_or_version[auth/login_wall.html-https://www.nccn.org/professionals/physician_gls/pdf/gastric.pdf] FAILED [ 36%]
tests/test_auth_download_regression.py::test_download_and_archive_rejects_html_patient_wrong_title_or_version[pdf/patient_stomach.pdf-https://www.nccn.org/patients/guidelines/content/PDF/stomach-patient.pdf] FAILED [ 45%]
tests/test_auth_download_regression.py::test_download_and_archive_rejects_html_patient_wrong_title_or_version[pdf/professional_breast_v2_2026.pdf-https://www.nccn.org/professionals/physician_gls/pdf/gastric.pdf] FAILED [ 54%]
tests/test_auth_download_regression.py::test_download_and_archive_rejects_html_patient_wrong_title_or_version[pdf/professional_gastric_v1_2025.pdf-https://www.nccn.org/professionals/physician_gls/pdf/gastric.pdf] FAILED [ 63%]
tests/test_auth_download_regression.py::test_existing_login_html_named_as_pdf_is_not_archived_completion FAILED [ 72%]
tests/test_auth_download_regression.py::test_non_pdf_occupant_can_be_replaced_by_matching_professional_pdf FAILED [ 81%]
tests/test_auth_download_regression.py::test_check_updates_retries_when_recorded_version_has_no_pdf FAILED [ 90%]
tests/test_auth_download_regression.py::test_check_updates_retries_after_download_failure FAILED [100%]

=================================== FAILURES ===================================
________ test_detail_page_skips_patient_link_listed_before_professional ________
tests/test_auth_download_regression.py:173: in test_detail_page_skips_patient_link_listed_before_professional
    assert pdf_url == PROFESSIONAL_GASTRIC_URL
E   AssertionError: assert 'https://www....h-patient.pdf' == 'https://www....f/gastric.pdf'
E     
E     - https://www.nccn.org/professionals/physician_gls/pdf/gastric.pdf
E     + https://www.nccn.org/patients/guidelines/content/PDF/stomach-patient.pdf
_______ test_detail_page_returns_none_when_only_patient_guide_is_listed ________
tests/test_auth_download_regression.py:178: in test_detail_page_returns_none_when_only_patient_guide_is_listed
    assert parse_detail_page_for_pdf(html) is None
E   assert 'https://www.nccn.org/patients/guidelines/content/PDF/stomach-patient.pdf' is None
E    +  where 'https://www.nccn.org/patients/guidelines/content/PDF/stomach-patient.pdf' = parse_detail_page_for_pdf('<!DOCTYPE html>\n<html>\n<body>\n  <p>Synthetic fixture. Not an NCCN page.</p>\n  <h4 class="GL">Guidelines</h4>\n  <ul class="pdfList">\n    <li>\n      <a href="/patients/guidelines/content/PDF/stomach-patient.pdf">NCCN Guidelines for Patients</a>\n    </li>\n  </ul>\n  <h4 class="PATs">Guidelines for Patients</h4>\n  <ul class="pdfList">\n    <li>\n      <a href="/patients/guidelines/content/PDF/stomach-patient.pdf">Stomach Cancer</a>\n    </li>\n  </ul>\n</body>\n</html>\n')
_________ test_detail_page_fallback_skips_patient_and_blocks_filenames _________
tests/test_auth_download_regression.py:183: in test_detail_page_fallback_skips_patient_and_blocks_filenames
    assert parse_detail_page_for_pdf(html) == PROFESSIONAL_GASTRIC_URL
E   AssertionError: assert 'https://www....c_patient.pdf' == 'https://www....f/gastric.pdf'
E     
E     - https://www.nccn.org/professionals/physician_gls/pdf/gastric.pdf
E     + https://www.nccn.org/professionals/physician_gls/pdf/gastric_patient.pdf
E     ?                                                             ++++++++
_ test_download_and_archive_rejects_html_patient_wrong_title_or_version[auth/login_wall.html-https://www.nccn.org/professionals/physician_gls/pdf/gastric.pdf] _
tests/test_auth_download_regression.py:237: in test_download_and_archive_rejects_html_patient_wrong_title_or_version
    assert result is None
E   AssertionError: assert PosixPath('/tmp/pytest-of-ubuntu/pytest-6/test_download_and_archive_reje0/archive/gastric-cancer/v2.2026/NCCN_GastricCancer_2026.V2_EN.pdf') is None
_ test_download_and_archive_rejects_html_patient_wrong_title_or_version[pdf/patient_stomach.pdf-https://www.nccn.org/patients/guidelines/content/PDF/stomach-patient.pdf] _
tests/test_auth_download_regression.py:237: in test_download_and_archive_rejects_html_patient_wrong_title_or_version
    assert result is None
E   AssertionError: assert PosixPath('/tmp/pytest-of-ubuntu/pytest-6/test_download_and_archive_reje1/archive/gastric-cancer/v2.2026/NCCN_GastricCancer_2026.V2_EN.pdf') is None
_ test_download_and_archive_rejects_html_patient_wrong_title_or_version[pdf/professional_breast_v2_2026.pdf-https://www.nccn.org/professionals/physician_gls/pdf/gastric.pdf] _
tests/test_auth_download_regression.py:237: in test_download_and_archive_rejects_html_patient_wrong_title_or_version
    assert result is None
E   AssertionError: assert PosixPath('/tmp/pytest-of-ubuntu/pytest-6/test_download_and_archive_reje2/archive/gastric-cancer/v2.2026/NCCN_GastricCancer_2026.V2_EN.pdf') is None
_ test_download_and_archive_rejects_html_patient_wrong_title_or_version[pdf/professional_gastric_v1_2025.pdf-https://www.nccn.org/professionals/physician_gls/pdf/gastric.pdf] _
tests/test_auth_download_regression.py:237: in test_download_and_archive_rejects_html_patient_wrong_title_or_version
    assert result is None
E   AssertionError: assert PosixPath('/tmp/pytest-of-ubuntu/pytest-6/test_download_and_archive_reje3/archive/gastric-cancer/v2.2026/NCCN_GastricCancer_2026.V2_EN.pdf') is None
_______ test_existing_login_html_named_as_pdf_is_not_archived_completion _______
tests/test_auth_download_regression.py:295: in test_existing_login_html_named_as_pdf_is_not_archived_completion
    assert first is None
E   AssertionError: assert PosixPath('/tmp/pytest-of-ubuntu/pytest-6/test_existing_login_html_named0/archive/gastric-cancer/v2.2026/NCCN_GastricCancer_2026.V2_EN.pdf') is None
______ test_non_pdf_occupant_can_be_replaced_by_matching_professional_pdf ______
tests/test_auth_download_regression.py:346: in test_non_pdf_occupant_can_be_replaced_by_matching_professional_pdf
    assert stored.startswith(b"%PDF")
E   assert False
E    +  where False = <built-in method startswith of bytes object at 0x3c2a360>(b'%PDF')
E    +    where <built-in method startswith of bytes object at 0x3c2a360> = b'<!DOCTYPE html>\n<html lang="en">\n<head><title>Fixture login wall</title></head>\n<body>\n  <h1>Log in</h1>\n  <p>Synthetic fixture for regression tests. Not an NCCN page and not a credential.</p>\n  <form action="/login/Index/" method="post">\n    <input type="hidden" name="__RequestVerificationToken" value="fixture-token" />\n    <label>Username <input type="text" name="Username" value="" /></label>\n    <label>Password <input type="password" name="Password" value="" /></label>\n    <button type="submit">Log in</button>\n  </form>\n</body>\n</html>\n'.startswith
_________ test_check_updates_retries_when_recorded_version_has_no_pdf __________
/workspace/tests/test_auth_download_regression.py:475: in test_check_updates_retries_when_recorded_version_has_no_pdf
    assert "No guideline updates detected" not in report
E   AssertionError: assert 'No guidelin...tes detected' not in 'No guidelin...035791+00:00'
E     
E     'No guideline updates detected' is contained here:
E       No guideline updates detected. Checked 3 guidelines. Last check: 2026-11-11T01:00:37.035791+00:00
E     ? +++++++++++++++++++++++++++++
______________ test_check_updates_retries_after_download_failure _______________
/workspace/tests/test_auth_download_regression.py:522: in test_check_updates_retries_after_download_failure
    assert "No guideline updates detected" not in retried
E   AssertionError: assert 'No guidelin...tes detected' not in 'No guidelin...044319+00:00'
E     
E     'No guideline updates detected' is contained here:
E       No guideline updates detected. Checked 3 guidelines. Last check: 2026-11-11T01:00:37.044319+00:00
E     ? +++++++++++++++++++++++++++++
=========================== short test summary info ============================
FAILED tests/test_auth_download_regression.py::test_detail_page_skips_patient_link_listed_before_professional
FAILED tests/test_auth_download_regression.py::test_detail_page_returns_none_when_only_patient_guide_is_listed
FAILED tests/test_auth_download_regression.py::test_detail_page_fallback_skips_patient_and_blocks_filenames
FAILED tests/test_auth_download_regression.py::test_download_and_archive_rejects_html_patient_wrong_title_or_version[auth/login_wall.html-https://www.nccn.org/professionals/physician_gls/pdf/gastric.pdf]
FAILED tests/test_auth_download_regression.py::test_download_and_archive_rejects_html_patient_wrong_title_or_version[pdf/patient_stomach.pdf-https://www.nccn.org/patients/guidelines/content/PDF/stomach-patient.pdf]
FAILED tests/test_auth_download_regression.py::test_download_and_archive_rejects_html_patient_wrong_title_or_version[pdf/professional_breast_v2_2026.pdf-https://www.nccn.org/professionals/physician_gls/pdf/gastric.pdf]
FAILED tests/test_auth_download_regression.py::test_download_and_archive_rejects_html_patient_wrong_title_or_version[pdf/professional_gastric_v1_2025.pdf-https://www.nccn.org/professionals/physician_gls/pdf/gastric.pdf]
FAILED tests/test_auth_download_regression.py::test_existing_login_html_named_as_pdf_is_not_archived_completion
FAILED tests/test_auth_download_regression.py::test_non_pdf_occupant_can_be_replaced_by_matching_professional_pdf
FAILED tests/test_auth_download_regression.py::test_check_updates_retries_when_recorded_version_has_no_pdf
FAILED tests/test_auth_download_regression.py::test_check_updates_retries_after_download_failure
============================== 11 failed in 0.24s ==============================
```

这次红灯输出里，测试 9 仍使用原始字节包含关系，并在 `startswith(b"%PDF")` 失败，因为返回的文件仍是登录页 HTML。

## 测试调整（实现之前）

测试 9 改为用 pypdf 抽出文本断言指南名和版本，保留 `%PDF` 魔数断言。删掉了「文件字节不得包含 Guidelines for Patients」。专业版封面可以出现患者系列的交叉推广，不能只因为这句话出现就拒绝。

新增 `test_compressed_professional_cover_with_patient_crosslink_is_archived` 和 fixture `tests/fixtures/pdf/professional_gastric_v2_2026_compressed.pdf`。该文件使用 FlateDecode，原始字节不含 `Gastric Cancer`、`Clinical Practice Guidelines`、`Guidelines for Patients`；抽出文本同时包含专业系列名、Gastric Cancer、`2.2026` 和患者系列交叉引用。测试不检查页面尺寸、旋转或坐标。

## 实现范围

- `parse_detail_page_for_pdf`：跳过患者 URL / 文件名，以及 `_blocks`、`_core`、`_basic`、`_enhanced`。主列表里没有专业版时返回 `None`。
- 新下载的文件必须是 `%PDF`，抽出文本含 `Clinical Practice Guidelines in Oncology`、所请求的指南名和版本。患者系列短语本身不构成拒绝。不合格正文不写入归档，也不写成功用的 `meta.json`。
- 标准文件名上已有的 HTML 不算完成，`get_archived_versions` 不列出它。随后一份匹配的专业版可以替换这个非 PDF 占用。已经以 `%PDF` 开头的文件原样返回，不改字节。
- `check_updates`：基线已经建立之后，监控列表内、状态里当前版本缺少有效 PDF 的指南会再下载一次。版本变化列表里已有的名称不重复下载。不扫描历史版本目录，也不下载监控列表之外的指南。第一次建立基线时不因为缺少归档而批量下载。
- `StateManager.initialized` 只读出已有标志，供上面的「基线之后才重试」使用。`detect_changes` 的比较和保存逻辑没有改。

空的 `watch_list` 在 `check_updates` 里原本就表示全部指南都在监控范围内。重试使用同一范围，并且只看每条指南已记录的当前版本。

## 绿灯复跑

测试 9 的断言和新用例已经在树上。回归文件因此是 12 项，不再是红灯时的 11 项。

```bash
.venv/bin/python -m pytest tests/test_archive.py tests/test_state.py tests/test_scraper.py tests/test_health.py -v --tb=short
# exit 0
```

```bash
.venv/bin/python -m pytest tests/test_auth_download_regression.py -v --tb=short
# exit 0
```

### 既有测试（实现后，exit 0）

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
collecting ... collected 44 items

tests/test_archive.py::test_get_archived_versions_empty PASSED           [  2%]
tests/test_archive.py::test_get_archived_versions_with_meta PASSED       [  4%]
tests/test_archive.py::test_get_archived_versions_multiple PASSED        [  6%]
tests/test_archive.py::test_get_archived_versions_pdf_only_no_meta PASSED [  9%]
tests/test_state.py::test_first_run_returns_no_changes PASSED            [ 11%]
tests/test_state.py::test_detects_version_change PASSED                  [ 13%]
tests/test_state.py::test_no_changes_returns_empty PASSED                [ 15%]
tests/test_state.py::test_watch_list_filters_results PASSED              [ 18%]
tests/test_state.py::test_watch_list_case_insensitive PASSED             [ 20%]
tests/test_state.py::test_new_guideline_added_later PASSED               [ 22%]
tests/test_state.py::test_state_persists_to_disk PASSED                  [ 25%]
tests/test_scraper.py::test_parse_category_page_extracts_all_items PASSED [ 27%]
tests/test_scraper.py::test_parse_category_page_extracts_versions PASSED [ 29%]
tests/test_scraper.py::test_parse_category_page_builds_detail_urls PASSED [ 31%]
tests/test_scraper.py::test_parse_category_page_sets_category PASSED     [ 34%]
tests/test_scraper.py::test_parse_category_page_both_columns PASSED      [ 36%]
tests/test_scraper.py::test_parse_category_page_empty_raises PASSED      [ 38%]
tests/test_scraper.py::test_parse_recently_published_extracts_all_guidelines PASSED [ 40%]
tests/test_scraper.py::test_parse_recently_published_extracts_versions PASSED [ 43%]
tests/test_scraper.py::test_parse_recently_published_tracks_categories PASSED [ 45%]
tests/test_scraper.py::test_parse_empty_html_raises_scrape_error PASSED  [ 47%]
tests/test_scraper.py::test_parse_detail_page_extracts_main_pdf PASSED   [ 50%]
tests/test_scraper.py::test_parse_detail_page_skips_blocks_and_patient PASSED [ 52%]
tests/test_scraper.py::test_parse_detail_page_no_pdf PASSED              [ 54%]
tests/test_scraper.py::test_slugify_basic PASSED                         [ 56%]
tests/test_scraper.py::test_slugify_colon PASSED                         [ 59%]
tests/test_scraper.py::test_slugify_slash PASSED                         [ 61%]
tests/test_scraper.py::test_slugify_parentheses PASSED                   [ 63%]
tests/test_scraper.py::test_slugify_special_chars PASSED                 [ 65%]
tests/test_scraper.py::test_slugify_all_92_guidelines_unique PASSED      [ 68%]
tests/test_scraper.py::test_format_pdf_filename_basic PASSED             [ 70%]
tests/test_scraper.py::test_format_pdf_filename_multi_word PASSED        [ 72%]
tests/test_scraper.py::test_format_pdf_filename_colon PASSED             [ 75%]
tests/test_scraper.py::test_format_pdf_filename_slash PASSED             [ 77%]
tests/test_scraper.py::test_format_pdf_filename_hyphen PASSED            [ 79%]
tests/test_scraper.py::test_format_pdf_filename_parentheses PASSED       [ 81%]
tests/test_health.py::test_starts_healthy PASSED                         [ 84%]
tests/test_health.py::test_stays_healthy_on_success PASSED               [ 86%]
tests/test_health.py::test_single_failure_no_alert PASSED                [ 88%]
tests/test_health.py::test_threshold_triggers_alert PASSED               [ 90%]
tests/test_health.py::test_alert_only_fires_once PASSED                  [ 93%]
tests/test_health.py::test_success_resets_failure_counter PASSED         [ 95%]
tests/test_health.py::test_status_summary_healthy PASSED                 [ 97%]
tests/test_health.py::test_status_summary_unhealthy PASSED               [100%]

============================== 44 passed in 0.18s ==============================
```

### 回归测试（实现后，12 passed，exit 0）

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
collecting ... collected 12 items

tests/test_auth_download_regression.py::test_detail_page_skips_patient_link_listed_before_professional PASSED [  8%]
tests/test_auth_download_regression.py::test_detail_page_returns_none_when_only_patient_guide_is_listed PASSED [ 16%]
tests/test_auth_download_regression.py::test_detail_page_fallback_skips_patient_and_blocks_filenames PASSED [ 25%]
tests/test_auth_download_regression.py::test_download_and_archive_rejects_html_patient_wrong_title_or_version[auth/login_wall.html-https://www.nccn.org/professionals/physician_gls/pdf/gastric.pdf] PASSED [ 33%]
tests/test_auth_download_regression.py::test_download_and_archive_rejects_html_patient_wrong_title_or_version[pdf/patient_stomach.pdf-https://www.nccn.org/patients/guidelines/content/PDF/stomach-patient.pdf] PASSED [ 41%]
tests/test_auth_download_regression.py::test_download_and_archive_rejects_html_patient_wrong_title_or_version[pdf/professional_breast_v2_2026.pdf-https://www.nccn.org/professionals/physician_gls/pdf/gastric.pdf] PASSED [ 50%]
tests/test_auth_download_regression.py::test_download_and_archive_rejects_html_patient_wrong_title_or_version[pdf/professional_gastric_v1_2025.pdf-https://www.nccn.org/professionals/physician_gls/pdf/gastric.pdf] PASSED [ 58%]
tests/test_auth_download_regression.py::test_existing_login_html_named_as_pdf_is_not_archived_completion PASSED [ 66%]
tests/test_auth_download_regression.py::test_non_pdf_occupant_can_be_replaced_by_matching_professional_pdf PASSED [ 75%]
tests/test_auth_download_regression.py::test_compressed_professional_cover_with_patient_crosslink_is_archived PASSED [ 83%]
tests/test_auth_download_regression.py::test_check_updates_retries_when_recorded_version_has_no_pdf PASSED [ 91%]
tests/test_auth_download_regression.py::test_check_updates_retries_after_download_failure PASSED [100%]

============================== 12 passed in 0.20s ==============================
```

## 仍未完成

- 认证原因未定。没有新的脱敏 httpx 响应。
- 仓外周检脚本未改，也未被这些测试执行。`check_updates` 的补档重试覆盖不到它，除非它自己调用 `check_updates` 或同等的缺失归档判断。下载校验在 `NCCNDownloader.download_and_archive` 上，wrapper 若调用该方法，新写入会受到校验；已经记入状态且 PDF 缺失时，wrapper 是否会再次调用下载，仍然未知。
- MBP 工作区里未提交的 `downloader.py`、`scraper.py` 和未跟踪调试脚本没有并入。
- 没有登录 NCCN，没有部署，没有合并。

请编码评审继续看这个候选。在周检脚本的脱敏控制流可读之前，不要把每周下载视为已修复。
