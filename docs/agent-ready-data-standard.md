# Agent-ready 数据标准

版本：`0.1.0`
状态：Draft
适用范围：Agent Data Quality Layer V0.1 及后续扩展

## 1. 目的

本标准定义什么是一条可供 AI Agent 直接使用的合格数据，以及数据从采集、解析、清洗、抽取、证据验证到发布必须满足的要求。

本标准面向网页、PDF、RSS、Sitemap、GitHub README 和技术文档等外部内容。V0.1 的强制范围是 URL 与 PDF。

本标准不负责评价 Agent 的推理能力，也不把“抓取成功”视为“数据合格”。只有来源可追溯、内容可验证、结构可解析、质量可解释且用途明确的数据，才能标记为 Agent-ready。

## 2. 核心定义

### 2.1 Agent-ready

一条数据仅在同时满足以下条件时为 Agent-ready：

```text
Agent-ready =
  Schema 校验通过
  AND 所有硬性准入门槛通过
  AND 无 Critical 质量问题
  AND 达到目标使用场景的最低评分要求
```

总分不能覆盖硬性失败。例如，缺少来源或 claim 没有可定位 evidence 时，即使其他评分很高，也不能发布到高质量层。

### 2.2 数据粒度

V0.1 的顶层粒度为“一条来源文档的一个处理版本”。

- 同一 URL 内容发生变化，应产生新版本，而不是静默覆盖。
- 同一 PDF 文件内容哈希相同，应识别为相同原始文档。
- 合并多个来源形成的 Topic 数据包不属于 V0.1 顶层粒度，留待 V0.2。
- 每个 claim 和 evidence 都有独立 ID，并归属于一个文档版本。

### 2.3 固有质量与任务适用性

质量分为两类：

1. 固有质量：来源、完整性、证据、结构等相对稳定的属性。
2. 任务适用性：相关性、时效要求、可执行性等依赖具体 Agent 任务的属性。

`relevance` 和 `actionability` 必须针对明确的 `task_context` 计算。没有任务上下文时，这两个分数应为 `null`，不得伪造通用分数。

## 3. 规范数据模型

以下为逻辑数据契约。实现时应转换为正式 JSON Schema，并固定 `schema_version`。

```json
{
  "id": "doc_001",
  "schema_version": "0.1.0",
  "status": "ready",
  "source": {
    "url": "https://example.com/article",
    "canonical_url": "https://example.com/article",
    "domain": "example.com",
    "source_type": "web",
    "title": "Example title",
    "author": "Example author",
    "publisher": "Example publisher",
    "published_at": "2026-06-01T08:00:00Z",
    "updated_at": null,
    "collected_at": "2026-06-22T08:00:00Z",
    "language": "zh-CN",
    "access_rights": "public",
    "license": null
  },
  "content": {
    "raw_content_ref": "object://bucket/raw/doc_001",
    "raw_content_hash": "sha256:...",
    "clean_content": "...",
    "clean_content_hash": "sha256:...",
    "content_format": "markdown",
    "is_complete": true,
    "truncation_reason": null
  },
  "knowledge": {
    "summary": "...",
    "key_points": ["..."],
    "claims": [
      {
        "id": "claim_001",
        "text": "...",
        "claim_type": "fact",
        "confidence": 0.92,
        "evidence_ids": ["evidence_001"],
        "verification_status": "verified"
      }
    ],
    "evidence": [
      {
        "id": "evidence_001",
        "quote": "...",
        "source_url": "https://example.com/article",
        "location": {
          "page": null,
          "section": "Results",
          "start_offset": 1024,
          "end_offset": 1180
        },
        "content_hash": "sha256:...",
        "verification_status": "verified"
      }
    ],
    "entities": [],
    "topics": [],
    "tags": [],
    "risks": [],
    "timeline": []
  },
  "lineage": {
    "document_version": 1,
    "pipeline_version": "0.1.0",
    "processed_at": "2026-06-22T08:01:00Z",
    "extractor": {
      "type": "llm",
      "provider": "example-provider",
      "model": "example-model",
      "prompt_version": "extract-v1"
    }
  },
  "quality": {
    "gate_status": "passed",
    "quality_level": "A",
    "intrinsic_score": 0.86,
    "task_score": null,
    "dimensions": {
      "source_trust": { "score": 0.8, "confidence": 0.8, "reasons": [] },
      "freshness": { "score": 0.9, "confidence": 0.9, "reasons": [] },
      "completeness": { "score": 0.9, "confidence": 0.9, "reasons": [] },
      "evidence_quality": { "score": 0.85, "confidence": 0.9, "reasons": [] },
      "structure_quality": { "score": 0.9, "confidence": 1.0, "reasons": [] },
      "relevance": null,
      "actionability": null
    },
    "checks": [],
    "issues": []
  },
  "usage": {
    "recommended_uses": ["retrieval", "summarization"],
    "prohibited_uses": [],
    "caveats": []
  },
  "export_formats": ["json", "markdown"]
}
```

## 4. 字段要求

### 4.1 必填字段

以下字段对所有已发布数据强制必填：

- `id`
- `schema_version`
- `status`
- `source.url` 或可解析的内部来源标识
- `source.source_type`
- `source.collected_at`
- `content.raw_content_ref`
- `content.raw_content_hash`
- `content.clean_content`
- `content.clean_content_hash`
- `content.content_format`
- `lineage.document_version`
- `lineage.pipeline_version`
- `lineage.processed_at`
- `quality.gate_status`
- `quality.quality_level`
- `quality.dimensions`
- `quality.checks`
- `quality.issues`

`published_at`、`author` 和 `license` 可以为空，但必须记录对应质量影响，不得用猜测值填充。

### 4.2 时间和分数

- 时间统一使用 ISO 8601，并保留时区；内部标准时区为 UTC。
- 所有分数范围为 `[0, 1]`。
- 分数必须同时记录评分方法、理由和置信度。
- 无法可靠计算的分数使用 `null`，不能使用 `0` 代替未知。

### 4.3 原文和清洗内容

- 原始内容必须保存为不可变对象，结构化数据只保存引用和哈希。
- 清洗不得改变原文事实含义。
- 代码块、表格、标题层级和引用关系应尽量保留。
- 如内容被截断，必须设置 `is_complete = false` 并记录原因。
- 清洗前后都必须计算内容哈希。

## 5. 硬性准入门槛

以下检查任意一项失败，`gate_status` 必须为 `failed`，数据不得标记为 `ready`：

| Gate | 通过条件 | 失败代码 |
|---|---|---|
| Schema | 数据符合当前 JSON Schema | `SCHEMA_INVALID` |
| Provenance | 来源可定位，采集时间存在 | `SOURCE_UNTRACEABLE` |
| Raw retention | 原始内容引用有效且哈希存在 | `RAW_CONTENT_MISSING` |
| Parse | 清洗正文非空且达到最小有效长度 | `CONTENT_UNUSABLE` |
| Integrity | 内容哈希校验通过 | `HASH_MISMATCH` |
| Claim grounding | 所有已发布事实型 claim 至少绑定一个 evidence | `CLAIM_UNGROUNDED` |
| Evidence location | evidence 能定位到当前版本原文 | `EVIDENCE_UNLOCATABLE` |
| Evidence fidelity | evidence 引文与原文匹配 | `EVIDENCE_MISMATCH` |
| Critical issues | 不存在未解决的 Critical 问题 | `CRITICAL_QUALITY_ISSUE` |
| Rights | 不违反明确的访问或使用限制 | `RIGHTS_RESTRICTED` |

V0.1 默认最小有效长度为 200 个 Unicode 字符。对于短公告、API 文档片段等明确短内容，可以通过来源类型规则覆盖，但必须记录覆盖原因。

## 6. Claim-Evidence 标准

### 6.1 Claim 类型

建议支持：

- `fact`：可由来源直接验证的事实陈述。
- `opinion`：来源作者的观点。
- `prediction`：来源中的预测或推测。
- `instruction`：来源给出的步骤或建议。
- `derived`：由多个证据推导的结论。

`fact` 必须有 evidence。其他类型也应有 evidence，但系统必须保留其类型，避免将观点或预测包装成事实。

### 6.2 Evidence 要求

合格 evidence 必须：

- 引自已保存的原始内容或可验证附件；
- 包含可回溯位置；
- 与 claim 语义一致；
- 不通过脱离上下文的截断改变原意；
- 绑定对应文档版本和内容哈希。

网页优先使用字符偏移、DOM 路径或章节定位；PDF 优先使用页码、块 ID 和字符偏移。只有页码而没有引文时，不视为充分定位。

### 6.3 验证状态

```text
unverified -> verified
           -> rejected
           -> needs_review
```

- `verified`：位置存在，文本匹配，语义支持 claim。
- `rejected`：证据不存在、冲突或不支持 claim。
- `needs_review`：自动验证无法可靠判断。

只有 `verified` 的事实型 claim 可以进入高质量发布层。

## 7. 质量评分

### 7.1 评分原则

质量评分用于排序、选择和风险说明，不替代硬性门槛。每个维度必须输出：

```json
{
  "score": 0.85,
  "confidence": 0.9,
  "method": "rules_v1",
  "reasons": ["发布时间明确", "正文完整"],
  "failed_checks": []
}
```

优先使用确定性规则。LLM 适合判断语义相关性、证据支持程度和可执行性，但其结果必须记录模型及提示词版本。

### 7.2 固有质量维度

| 维度 | 核心问题 | 主要信号 |
|---|---|---|
| `source_trust` | 来源是否可识别、稳定且具有相应权威性 | 官方性、作者、发布者、来源历史、HTTPS、可追溯性 |
| `freshness` | 内容对其主题是否仍然及时 | 发布时间、更新时间、采集时间、主题时效窗口 |
| `completeness` | 内容是否完整、无关键缺页或截断 | 正文长度、页数、章节覆盖、解析失败率 |
| `evidence_quality` | claim 是否有充分且可验证的证据 | 覆盖率、定位率、匹配率、上下文充分性 |
| `structure_quality` | 数据是否稳定符合契约并可被机器消费 | Schema、字段类型、枚举、层级、重复和解析一致性 |

固有质量总分：

```text
intrinsic_score =
  0.20 * source_trust
  + 0.15 * freshness
  + 0.20 * completeness
  + 0.30 * evidence_quality
  + 0.15 * structure_quality
```

权重是 V0.1 默认值。调整权重必须提升评分规则版本，且不能重写历史评分而不保留旧版本。

### 7.3 任务适用性维度

| 维度 | 核心问题 |
|---|---|
| `relevance` | 内容是否直接支持当前任务 |
| `actionability` | 内容是否足以让 Agent 执行下一步操作 |

任务评分只在提供 `task_context` 时计算：

```text
task_score =
  0.70 * relevance
  + 0.30 * actionability
```

任务评分不能改变数据的固有质量，只影响检索排序和推荐用途。

### 7.4 质量等级

质量等级仅对已通过全部 Gate 的数据计算：

| 等级 | intrinsic_score | 含义 |
|---|---:|---|
| A | `>= 0.85` | 高可信，可优先用于 Agent 检索和摘要 |
| B | `>= 0.70` | 可用，但应携带 caveats |
| C | `>= 0.55` | 受限使用，不应用作唯一决策依据 |
| Rejected | Gate 失败或 `< 0.55` | 不进入 Agent-ready 层 |

不同场景可以提高阈值，但不得降低硬性门槛。涉及医疗、法律、金融和安全决策时，本标准只能作为数据质量基础，不能替代领域审核。

## 8. 质量问题模型

每个问题必须包含：

```json
{
  "code": "CLAIM_UNGROUNDED",
  "severity": "critical",
  "confidence": 0.98,
  "message": "事实型 claim 未绑定 evidence",
  "affected_paths": ["knowledge.claims[2]"],
  "evidence": [],
  "likely_cause": "抽取器未返回证据",
  "remediation": "重新抽取或移除该 claim",
  "detected_at": "2026-06-22T08:01:00Z"
}
```

严重性定义：

- `critical`：破坏来源、内容完整性或事实可验证性，阻止发布。
- `high`：显著影响可信使用，通常需要人工复核或限制用途。
- `medium`：局部质量下降，需要说明或监控。
- `low`：不影响当前用途的格式或边缘问题。

## 9. 生命周期与状态机

```text
collected
  -> parsed
  -> cleaned
  -> extracted
  -> validating
  -> ready

任意处理状态 -> failed
validating -> needs_review
ready -> superseded
```

状态要求：

- `ready`：Gate 全部通过且质量等级为 A、B 或 C。
- `needs_review`：不存在确定的 Critical 失败，但自动验证无法完成。
- `failed`：处理失败或 Gate 失败。
- `superseded`：存在同一来源的新版本；旧版本继续可追溯，但默认不返回。
- 状态转换必须记录时间、原因和执行组件。

## 10. 数据质量检查清单

### 10.1 通用检查

- 必填字段完整性和类型有效性；
- ID、内容哈希和版本唯一性；
- URL 规范化与重复来源识别；
- 时间字段合法性与未来时间检测；
- 原始内容引用可用性；
- 清洗前后内容保真度；
- 重复段落、导航、广告和页脚残留；
- claim-evidence 覆盖率、定位率和匹配率；
- 分类枚举合法性；
- 处理器版本和评分方法完整性。

### 10.2 网页检查

- canonical URL 是否正确；
- 页面是否为软 404、登录页、验证码页或错误页；
- 正文与导航模板比例是否合理；
- 动态内容是否采集完整；
- 页面更新时间是否可信；
- DOM 位置是否能在当前内容版本中重放。

### 10.3 PDF 检查

- 文件是否完整、可打开；
- 页数是否与解析结果一致；
- 是否为扫描件并需要 OCR；
- OCR 置信度是否达到阈值；
- 表格、脚注、双栏和页眉页脚是否被正确处理；
- evidence 的页码和块位置是否有效。

## 11. 推荐用途与限制用途

系统必须显式输出用途，而不是让 Agent 仅根据总分猜测。

建议用途枚举：

- `retrieval`
- `summarization`
- `question_answering`
- `research_support`
- `entity_extraction`
- `timeline_extraction`
- `decision_support`

常见限制：

- 内容过旧，不用于当前状态判断；
- 仅为单一来源，不用于交叉验证结论；
- 来源为观点文章，不作为事实依据；
- OCR 或解析质量有限；
- 缺少许可信息，不允许再发布原文；
- 质量等级 C，不作为自动决策的唯一输入。

## 12. V0.1 验收标准

V0.1 必须通过以下可验证场景：

1. 输入一个公开网页，生成符合 Schema 的数据包。
2. 输入一个文本型 PDF，保留页码并生成可定位 evidence。
3. 相同内容重复输入时，通过内容哈希识别重复文档。
4. 页面只有导航或错误信息时，拒绝发布并返回 `CONTENT_UNUSABLE`。
5. 抽取器生成无 evidence 的事实 claim 时，拒绝该 claim；如仍存在未处理事实 claim，则整个数据包不能进入 `ready`。
6. evidence 引文无法在原文中匹配时，返回 `EVIDENCE_MISMATCH`。
7. 内容被截断时，记录截断原因并降低完整性；关键内容不完整时拒绝发布。
8. 没有任务上下文时，`relevance`、`actionability` 和 `task_score` 为 `null`。
9. 每项分数都能返回方法、理由和置信度。
10. 每个数据包可以导出 JSON 和 Markdown，且导出内容保留来源与 evidence 引用。
11. 数据更新时创建新版本，旧版本标记为 `superseded`，不得静默覆盖。
12. 所有失败均返回稳定错误代码和可执行修复建议。

## 13. 合格与不合格示例

### 13.1 合格示例

```text
来源：公开 PDF，有文件哈希和采集时间
内容：全部页面解析成功，正文完整
Claim：12 条事实型 claim，全部绑定可定位到页码和引文的 evidence
质量：Gate 全部通过，intrinsic_score = 0.88，等级 A
结果：status = ready
```

### 13.2 不合格示例：高分但无证据

```text
来源可信、内容新鲜、摘要清晰
但 3 条事实型 claim 未绑定 evidence
结果：CLAIM_UNGROUNDED，status = failed
```

不能因为平均质量分较高而发布。

### 13.3 受限示例：来源完整但较旧

```text
来源和 evidence 均可验证
文档发布于五年前，主题具有较强时效性
结果：Gate 通过，等级 C
用途：可用于历史研究，不用于当前状态判断
```

## 14. 自动化与人工复核边界

适合自动化：

- Schema、类型、必填字段和枚举校验；
- 内容哈希、重复检测和版本识别；
- URL、时间、页码和字符偏移检查；
- evidence 文本精确或归一化匹配；
- claim-evidence 覆盖率；
- 解析长度、页数和截断检测；
- 稳定错误代码和质量等级计算。

需要谨慎或人工复核：

- 来源权威性的最终判断；
- claim 是否被 evidence 充分支持；
- 引文是否脱离上下文；
- 多来源冲突；
- 高风险领域的可用性；
- 版权、许可和合理使用边界。

## 15. 扩展规范路线

以下能力不阻塞 V0.1，但后续版本必须纳入：

### 15.1 V0.2：多来源与 Topic 数据包

- Topic 查询上下文与动态 relevance；
- 多来源 claim 合并和去重；
- 证据一致性与来源冲突；
- 来源多样性和交叉验证覆盖率；
- Topic 数据包级别的版本和有效期。

### 15.2 V0.3：服务化与质量监控

- API Key、配额、Webhook 和 MCP；
- 数据新鲜度 SLA；
- 解析成功率和 evidence 失败率趋势；
- 来源、Schema 和分布漂移；
- Pipeline 升级前后的质量回归；
- 数据删除、重处理和审计日志。

### 15.3 后续：多模态与治理

- 图片、音频、视频和表格证据定位；
- 多语言内容一致性；
- 敏感信息、恶意提示和内容安全；
- 版权、许可、访问控制和保留策略；
- 人工审核队列、申诉和质量标注；
- 不同 Agent 场景的质量策略模板。

## 16. 版本演进原则

- Schema 使用语义化版本。
- 删除字段、改变含义或收紧必填要求属于破坏性变更。
- 新增可选字段属于向后兼容变更。
- Pipeline、评分规则和提示词分别版本化。
- 历史记录保留原评分和原处理版本。
- 重处理产生新文档版本，不覆盖审计证据。

## 17. 实施优先级

V0.1 按以下顺序实现：

1. 固定 JSON Schema、状态和错误代码。
2. 保存原始内容、哈希和处理血缘。
3. 实现 URL/PDF 解析与清洗完整性检查。
4. 实现 claim-evidence 数据结构和定位。
5. 实现确定性 Gate 校验。
6. 实现可解释的分维度评分。
7. 实现 JSON/Markdown 导出。
8. 建立上述十二项验收场景的自动化测试。

本标准的首要成功指标不是采集数量，而是：发布到 `ready` 状态的数据能够被复查、重放、解释和安全降级。
