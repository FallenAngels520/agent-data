# 高质量 Agent 数据设计说明

## 核心判断

高质量数据不是数据越多越好，而是数据能否让 Agent 在真实任务中做出更好的判断、更少犯错、更稳定执行。

本项目对高质量数据的定义是：可验证、可追溯、可结构化、可被 Agent 调用，并且能直接提升任务结果的数据。

## 五层质量模型

1. **任务价值**：数据必须能映射到具体任务，例如 `agent_development`、`web_agent`、`data_extraction`。没有任务上下文时，不伪造任务相关性分数。
2. **可信度**：记录来源、域名、采集时间、原始内容哈希和清洗后内容哈希。官方文档、原始仓库、论文、API 文档优先。
3. **结构化**：不能只保留大段文本，应抽取 summary、key_points、claims、entities、topics、tags、limitations 等可调用字段。
4. **可验证性**：每个事实 claim 都应绑定 quote、block_id、page/bbox 或 offset。数据平台保存的是“结论 + 证据 + 置信度”。
5. **反馈闭环**：后续 Agent 使用数据后的结果应反向影响质量，例如任务失败原因是“repo_not_maintained”，则下调 freshness 或 source trust。

## 质量画像

每个 Agent-ready 数据包应包含 `quality.quality_profile`：

```json
{
  "source_trust": {
    "score": 0.85,
    "tier": "primary",
    "category": "authoritative_source",
    "requires_cross_verification": false,
    "allowed_uses": ["fact_base", "retrieval", "agent_decision"],
    "risk_tags": [],
    "reasons": ["https_source"]
  },
  "data_type": "fact_data",
  "verification_level": "strong",
  "store_target": "agent_ready_data_store",
  "agent_ready": true,
  "policy_reasons": ["authoritative_source"],
  "freshness": {
    "score": 0.9,
    "last_checked_at": "2026-06-23T00:00:00Z",
    "published_at": "2026-06-01T00:00:00Z",
    "staleness_risk": "low"
  },
  "verifiability": {
    "score": 1.0,
    "verified_fact_claims": 3,
    "total_fact_claims": 3,
    "evidence_count": 3
  },
  "structure": {"score": 0.8, "reasons": ["claims=3"]},
  "task_relevance": {"score": 0.74},
  "noise": {"score": 0.0, "risk_tags": []}
}
```

## 来源等级与交叉验证策略

来源必须分级，不同等级决定数据能否直接作为事实依据。

| 等级 | 来源类型 | 默认策略 |
|---|---|---|
| `S` | 官网、官方文档、API 文档、GitHub 原仓库、论文原文、PDF 原件 | 可作为事实来源，但 claim 仍需 quote evidence |
| `A` | 技术博客、公司工程博客、公众号、专业媒体、论文解读 | 关键事实需要交叉验证 |
| `B` | Reddit、Hacker News、GitHub issue、论坛、用户反馈 | 作为社区反馈和痛点信号，需要聚合验证 |
| `C` | X、LinkedIn、YouTube、TikTok、小红书、抖音 | 只能作为趋势信号或线索，必须交叉验证 |
| `D` | 未知网站、聚合页、搬运号、营销号、无法判断来源等级的网页 | 只作为候选证据，必须人工或多源复核 |

当前实现先做单来源策略标注：

```json
{
  "source_trust": {
    "tier": "C",
    "category": "social_discussion",
    "requires_cross_verification": true,
    "allowed_uses": ["trend_signal", "lead_generation"],
    "risk_tags": ["high_noise", "opinion_heavy"]
  },
  "data_type": "signal_data",
  "verification_level": "medium",
  "store_target": "signal_pool",
  "agent_ready": false
}
```

真正的多来源交叉验证需要等 `discovery/`、`storage/` 和 topic package 能力具备后再实现。

## 数据类型与入库目标

单文档 pipeline 现在只负责判断数据应进入哪一层，而不是把所有采集结果都当作 Agent-ready。

| 数据类型 | 说明 | 默认入库目标 |
|---|---|---|
| `fact_data` | 来自 S 级来源、可定位证据的事实数据 | `agent_ready_data_store` |
| `evidence_data` | 可作为候选证据或二级分析材料的数据 | `verified_knowledge_base` 或 `signal_pool` |
| `signal_data` | 趋势、痛点、讨论热度、早期线索 | `signal_pool` |
| `opinion_data` | 作者观点、方法论、判断 | `signal_pool` |
| `case_data` | 案例过程、条件、成本、风险 | `verified_knowledge_base` |
| `benchmark_data` | 评测、实验、对比结果 | `verified_knowledge_base`，高风险场景需实验复核 |

当前输出会包含：

```json
{
  "verification_level": "strong|medium|light|experimental",
  "store_target": "raw_data_lake|signal_pool|verified_knowledge_base|agent_ready_data_store",
  "agent_ready": true
}
```

如果 `agent_ready=false` 但硬性 Gate 通过，文档包状态为 `needs_review`，仍会导出，供后续验证或聚合。

## 当前落地边界

V0.1 保持现有 pipeline 不变：

```text
source -> parse -> extract -> evidence -> gates -> score -> quality_profile -> export
```

质量 Gate 仍然负责硬性准入；质量画像负责解释数据为什么可信、是否新鲜、是否可验证、结构是否足够、是否有噪音风险。

## 后续扩展

后续可以增加三层：

- `discovery/`：把自然语言任务转成候选 URL/PDF 来源。
- `storage/`：把 Agent-ready 数据包入库并支持检索排序。
- `feedback/`：记录 Agent 使用结果，反向修正质量画像。

## 后续必须补充的能力

1. **可配置来源注册表**：把当前内置域名规则迁移到配置文件，例如 `config/source_tiers.yml`，支持业务方添加官方域名、社区域名、低质量域名。
2. **跨来源 claim matching**：对同一 claim 做语义归一化和来源去重，判断是否被两个独立来源支持。
3. **冲突检测**：当两个来源对同一事实给出相反结论时，标记 `cross_verification.status=conflicting`。
4. **多来源 Topic Package**：把多个单文档 Agent-ready 包聚合为主题数据包，用于“最近 Claude 博客”“AI Agent 项目趋势”这类宽泛任务。
5. **来源黑名单与隔离区**：`blocked` 来源不进入高质量层，但可进入隔离区供人工审查。
6. **反馈闭环**：Agent 使用某条数据后，如果任务失败原因与数据过期、来源噪音或证据不足有关，需要回写质量调整记录。
