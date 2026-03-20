# TODOS

## Enhancement: NCCN 指南索引缓存
- **Priority**: Medium
- **Status**: Planned (post-MVP)
- **What**: 爬取 NCCN 4 个 category 页面生成完整指南列表，用户可从列表中选择要监控的瘤种
- **Why**: 避免用户手动输入瘤种名称时拼写错误导致监控失败
- **Reuse**: NCCN_guidelines_MCP 的 `nccn_get_index.py` 已实现类似功能
- **Depends on**: 无，可独立实现
- **Added**: 2026-03-20 by /plan-eng-review

## Vision: 多指南体系支持（ESMO、CSCO、ASCO）
- **Priority**: Low (v2+)
- **Status**: Planned (post-MVP validation)
- **What**: 扩展监控范围到 ESMO、CSCO、ASCO 等其他肿瘤临床指南体系
- **Why**: 不同地区医生关注不同指南体系（如中国医生关注 CSCO），扩大工具覆盖面
- **Risk**: 每个指南体系网站结构不同，需单独开发爬虫
- **Depends on**: MVP 在 NCCN 上验证模式成功后
- **Added**: 2026-03-20 by /plan-eng-review
