# Agent-ready Data CLI MVP 实现设计

版本：`0.1.0`
状态：Approved
日期：2026-06-22
依据：`design.md`、`agent-ready-data-standard.md`

## 1. 目标

实现一个单机 CLI，将 URL 或本地 PDF 转换为符合 Agent-ready 数据标准的数据包。

```text
输入 URL / PDF
→ 采集与解析
→ 统一内容块
→ LLM 结构化抽取
→ Claim-Evidence 验证
→ Quality Gates
→ 质量评分
→ JSON / Markdown / 质量报告
```

首个版本验证数据质量加工闭环，不建设平台基础设施。

## 2. MVP 范围

### 2.1 包含

- 单机 Python CLI；
- URL 输入；
- 本地 PDF 输入；
- URL 使用 `httpx + trafilatura`；
- PDF 使用 MinerU HTTP API；
- OpenAI-compatible LLM 接口；
- summary、key points、claims、entities、topics、tags 抽取；
- claim 与来源内容块绑定；
- 确定性 evidence 验证；
- 硬性质量门槛；
- 分维度质量评分；
- JSON、Markdown 和质量报告输出；
- 离线单元测试与上游契约测试。

### 2.2 不包含

- Web 前端；
- FastAPI 服务；
- PostgreSQL、MinIO、Redis、Celery 或 Qdrant；
- MCP Server；
- Topic Search 和多来源合并；
- 动态插件安装、插件扫描或插件市场；
- 多 Agent 编排；
- 生产级用户、鉴权、配额和审计平台。

## 3. 关键决策

### 3.0 长期形态：Agent Harness

项目最终形态是面向 Agent 的数据处理 Harness。CLI 只是第一个可运行入口，不是最终架构边界。

MVP 中的 `process_document` 应实现为轻量、受控的 Harness：它编排来源解析、内容抽取、证据验证、质量门槛、评分和导出，但不把确定性质量规则交给 LLM 自由决定。

```text
Agent Harness
├── Source Tool
├── Parser Tool
│   ├── MinerU
│   └── Trafilatura
├── Extractor Agent
├── Evidence Tool
├── Quality Gate Tool
├── Scoring Tool
└── Export Tool
```

长期演进时，CLI、API 和 MCP 都调用同一个 Harness 用例：

```text
CLI ─┐
API ─┼─→ Agent Data Harness → Tools → Agent-ready Data Package
MCP ─┘
```

Harness 可以负责：

- 工具选择和调用顺序；
- 长文档分块与结果汇总；
- LLM 抽取任务；
- 有边界的重试、超时和恢复；
- 运行状态、观测事件和最终打包。

Harness 不得自由决定：

- Schema 是否有效；
- 哈希和重复结果；
- evidence 是否真实存在于原文；
- 页码、bbox 和字符偏移；
- 硬性 Gate 是否通过；
- 确定性评分公式；
- 状态机和错误代码。

这些能力必须保留为可测试的确定性工具。Agent 负责推理与编排，代码负责可信边界。

### 3.1 同步单进程 CLI

MVP 使用同步流水线。每次命令处理一个文档并生成独立输出目录。长耗时步骤显示阶段状态，但不引入任务队列。

建议命令：

```powershell
agent-data process <URL或PDF路径> --output ./output
```

可选参数：

```text
--task-context TEXT
--start-page INTEGER
--end-page INTEGER
--force
--keep-raw / --no-keep-raw
--log-level LEVEL
```

`--start-page` 和 `--end-page` 仅对 PDF 有效。默认处理完整文档，不固定为前 10 页。

### 3.2 OpenAI-compatible LLM

LLM 供应商通过环境变量配置，不绑定单一厂商：

```env
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
LLM_TIMEOUT_SECONDS=120
```

实现记录 provider、model、提示词版本和响应 Schema 版本，但不记录 API Key。

### 3.3 解析器代码级可插拔

MVP 使用稳定接口和显式注册表，不实现动态插件框架。

```python
class DocumentParser(Protocol):
    def supports(self, source: SourceInput) -> bool: ...
    def parse(self, source: SourceInput) -> ParsedDocument: ...
```

首批实现：

```text
DocumentParser
├── MinerUParser       # PDF
└── TrafilaturaParser  # URL
```

配置：

```env
PDF_PARSER=mineru
URL_PARSER=trafilatura
MINERU_BASE_URL=http://192.168.0.213:8000
MINERU_TIMEOUT_SECONDS=600
```

未来替换 Docling、Firecrawl 或其他解析器时，只新增适配器并注册，不修改后续抽取、验证、评分和导出模块。

## 4. 系统架构

```text
CLI
 ↓
Source Resolver
 ↓
Parser Registry
 ├─ URL → TrafilaturaParser
 └─ PDF → MinerUParser
 ↓
Normalizer
 ↓
LLM Extractor
 ↓
Evidence Verifier
 ↓
Quality Gates
 ↓
Quality Scorer
 ↓
JSON / Markdown Exporter
```

### 4.1 CLI

职责：

- 解析参数和配置；
- 调用单文档处理用例；
- 展示处理阶段；
- 映射最终状态到退出码；
- 不包含业务规则。

CLI 只依赖 Harness 的公共用例接口，不直接依赖 MinerU、Trafilatura、LLM SDK 或导出器。这样后续增加 API/MCP 入口时不复制流程。

### 4.2 Source Resolver

职责：

- 判断输入是 URL 还是本地 PDF；
- 校验文件存在、扩展名和基础 MIME；
- URL 规范化；
- 创建来源元数据；
- 采集或读取原始字节；
- 计算 SHA-256 原始内容哈希。

输出 `SourceDocument`，包含来源类型、规范地址或文件路径、原始内容引用、哈希和采集时间。

### 4.3 Parser Registry

职责：

- 按来源类型和配置选择解析器；
- 未注册或不支持的来源返回稳定错误；
- 不泄漏具体解析器字段给下游。

### 4.4 Normalizer

将解析器输出转换为内部统一模型：

```text
ParsedDocument
├── markdown
├── content_blocks[]
├── metadata
├── parser_name
├── parser_version
└── warnings[]
```

统一内容块：

```text
ContentBlock
├── block_id
├── type
├── text
├── order
├── page              # URL 为 null
├── bbox              # URL 为 null
├── start_offset      # 可计算时填写
├── end_offset
└── source_location
```

`block_id` 在同一文档版本内稳定，由内容哈希、块顺序和位置生成。下游只依赖内部模型。

### 4.5 LLM Extractor

职责：

- 按 token 上限对内容块分组；
- 使用结构化响应 Schema 抽取知识；
- 让每条 claim 返回候选 `block_id` 和原文 quote；
- 合并分块结果；
- 对相同或高度相似 claim 去重；
- 记录模型和提示词版本。

LLM 只提出 claim 和候选 evidence，不具有最终验证权。

### 4.6 Evidence Verifier

职责：

- 验证候选 `block_id` 存在；
- 对 quote 做 Unicode、空白和标点归一化；
- 优先在候选块中精确匹配；
- 候选失败时在全文内容块中查找唯一匹配；
- 保存页码、bbox、块 ID 和字符偏移；
- 将无法匹配、歧义匹配和语义不支持分别记录。

事实型 claim 只有在 evidence 状态为 `verified` 时才可发布。

### 4.7 Quality Gates

按 `agent-ready-data-standard.md` 执行不可由分数抵消的硬门槛：

- Schema 合规；
- 来源可追溯；
- 原始内容和哈希存在；
- 解析内容可用；
- 哈希一致；
- 事实 claim 全部有 evidence；
- evidence 可定位且引文匹配；
- 无 Critical 问题；
- 无明确访问权限制。

每项 Gate 返回稳定检查代码、状态、证据和修复建议。

### 4.8 Quality Scorer

只在 Gate 结果可解释后运行。评分维度：

- source trust；
- freshness；
- completeness；
- evidence quality；
- structure quality；
- relevance，存在 task context 时；
- actionability，存在 task context 时。

确定性信号优先。需要 LLM 判断的维度必须独立记录方法和置信度。没有 task context 时，relevance、actionability 和 task score 为 `null`。

### 4.9 Exporter

职责：

- 根据内部领域模型生成 Agent-ready JSON；
- 执行最终 JSON Schema 校验；
- 生成可阅读 Markdown；
- 无论成功或失败都生成质量报告和运行元数据；
- 使用临时文件加原子替换，避免半写入结果。

## 5. MinerU 适配器契约

### 5.1 请求

默认同步调用：

```text
POST {MINERU_BASE_URL}/file_parse
Content-Type: multipart/form-data
```

默认表单参数：

```json
{
  "return_md": "true",
  "return_content_list": "true",
  "table_enable": "true",
  "formula_enable": "true",
  "backend": "pipeline",
  "parse_method": "ocr",
  "lang_list": ["ch"],
  "start_page_id": 0,
  "end_page_id": 99999
}
```

页码参数由 CLI 覆盖。文件句柄必须通过上下文管理器关闭。请求必须有连接、读取和总处理超时。

### 5.2 响应

当前官方同步响应结构：

```json
{
  "backend": "pipeline",
  "version": "3.x",
  "results": {
    "document": {
      "md_content": "...",
      "content_list": "[{...}]"
    }
  }
}
```

`content_list` 可能是 JSON 字符串，适配器必须二次解析；为兼容部署差异，也接受已经反序列化的数组。

内容块主要字段：

```text
type
text / table_body / list_items / 其他类型内容字段
page_idx
bbox
```

MinerU `page_idx` 从 0 开始。内部保存原值并对用户展示 `page = page_idx + 1`，两者不能混用。

### 5.3 PDF Evidence

MinerU 块转换后的 evidence 至少包含：

```json
{
  "block_id": "block_...",
  "page": 1,
  "page_index": 0,
  "bbox": [62, 480, 946, 904],
  "quote": "...",
  "content_hash": "sha256:..."
}
```

只有 `md_content` 而没有 `content_list` 时，可以保存解析结果用于诊断，但不能满足 PDF evidence 定位 Gate，返回 `EVIDENCE_UNLOCATABLE`。

### 5.4 版本兼容

- 记录 MinerU 服务版本和 backend；
- 将上游响应解析集中在适配器内；
- 未知响应结构返回 `PARSER_CONTRACT_MISMATCH`；
- 使用真实响应 fixture 固定已支持契约；
- 后续异步 `/tasks` API 作为新适配器或传输策略加入，不改变内部模型。

## 6. URL 解析契约

`TrafilaturaParser` 使用 `httpx` 获取网页，使用 `trafilatura` 抽取正文和元数据。

要求：

- 设置明确 User-Agent；
- 限制响应大小和重定向次数；
- 只接受允许的 HTTP/HTTPS URL；
- 检查状态码和内容类型；
- 识别软 404、登录页、验证码页和空正文；
- 保存最终 URL、响应时间、内容哈希和基础响应元数据；
- 禁止访问本机、环回、链路本地和内网地址，除非用户显式开启允许内网访问的配置。

URL evidence 使用 `block_id + quote + start_offset + end_offset`。若正文抽取无法保持 DOM 路径，V0.1 不承诺 DOM 级定位。

## 7. Claim-Evidence 数据流

```text
统一内容块
→ 分块发送给 LLM
→ LLM 返回 claim + quote + candidate_block_id
→ 候选块归一化精确匹配
→ 必要时全文唯一匹配
→ 保存来源位置
→ verified / rejected / needs_review
```

验证规则：

1. 原文 quote 不能为空。
2. 候选块必须属于当前文档版本。
3. quote 必须可在归一化块文本中匹配。
4. 全文搜索出现多个相同匹配且无法区分时，标记 `needs_review`。
5. quote 与原文不匹配时标记 `rejected`。
6. `fact` 类型 claim 未验证时不进入发布知识层。
7. 如果仍有未处理的事实 claim，整个数据包不能进入 `ready`。

长文档采用分块抽取再合并，不在 MVP 引入向量检索。

## 8. 输出目录

每次运行创建：

```text
output/<document-id>/
├── raw/
│   └── <原始文件或网页响应>
├── parsed/
│   ├── document.md
│   └── content-blocks.json
├── agent-ready.json
├── agent-ready.md
├── quality-report.json
└── run.json
```

规则：

- `quality-report.json` 和 `run.json` 无论成功失败都应生成；
- `agent-ready.*` 仅在 Gate 通过时作为正式发布结果生成；
- 原始内容默认保留；
- 输出目录不得包含 API Key 或完整认证头；
- 重复内容使用相同内容标识，但每次运行保留独立运行记录；
- `--force` 只允许重新处理，不允许静默覆盖已有审计结果。

## 9. 错误与退出码

### 9.1 错误类别

- 技术失败：输入、网络、解析器、LLM、导出或内部异常；
- 质量失败：处理完成，但数据未通过 Agent-ready Gate。

所有错误包含稳定代码、阶段、消息、是否可重试和修复建议。内部堆栈只写调试日志，不作为默认用户输出。

### 9.2 CLI 退出码

| 退出码 | 含义 |
|---:|---|
| 0 | 数据通过 Gate，状态为 ready |
| 2 | 数据被质量门槛拒绝 |
| 3 | 输入或配置无效 |
| 4 | 采集或解析失败 |
| 5 | LLM 请求或响应失败 |
| 6 | 导出或内部失败 |

### 9.3 重试

- 网络超时、HTTP 429 和部分 5xx 可以有限重试；
- Schema 不匹配、认证失败、输入无效和质量 Gate 失败不自动重试；
- LLM 重试不得改变文档版本，但必须记录尝试次数；
- MinerU 长任务使用足够长的读取超时，避免无边界等待。

## 10. 建议代码边界

```text
src/agent_data/
├── cli.py
├── config.py
├── application/
│   ├── harness.py
│   └── process_document.py
├── domain/
│   ├── models.py
│   ├── errors.py
│   ├── quality.py
│   └── schema.py
├── sources/
│   └── resolver.py
├── parsers/
│   ├── base.py
│   ├── registry.py
│   ├── mineru.py
│   └── trafilatura.py
├── extraction/
│   ├── llm_client.py
│   ├── extractor.py
│   └── prompts.py
├── evidence/
│   └── verifier.py
├── quality/
│   ├── gates.py
│   └── scorer.py
└── export/
    ├── json_exporter.py
    └── markdown_exporter.py
```

这是逻辑边界，不要求为极少量代码机械拆文件。实现时保持模块职责单一，避免预先构建抽象框架。

`application/harness.py` 定义运行上下文、步骤状态和工具端口；`process_document.py` 实现 V0.1 固定流程。MVP 不引入自治循环、动态规划器或多 Agent 框架。后续需要更强编排时，可以替换 Harness 策略，但不能绕过领域层 Gate。

## 11. 测试策略

### 11.1 单元测试

- Source Resolver 对 URL、PDF 和无效输入的判断；
- Parser Registry 选择和不支持错误；
- MinerU `content_list` 字符串及数组兼容；
- MinerU 文本、标题、表格、列表和公式块转换；
- `page_idx` 到用户页码的映射；
- block ID 稳定性；
- evidence 精确匹配、归一化匹配、唯一回退和歧义结果；
- Gate、评分、等级、状态和退出码；
- JSON Schema 和 Markdown 导出。

### 11.2 契约测试

- 保存脱敏后的真实 MinerU 成功响应 fixture；
- 保存 MinerU 错误和缺字段响应 fixture；
- 保存 OpenAI-compatible 结构化响应 fixture；
- 默认测试不得访问内网或互联网；
- 上游字段变化必须先更新适配器和 fixture。

### 11.3 端到端测试

- 本地 PDF fixture 生成 ready 数据包；
- 固定 HTML fixture 生成 ready 数据包；
- 无 evidence 的事实 claim 导致 rejected；
- evidence 引文不匹配导致 rejected；
- 重复输入产生相同原始内容哈希；
- 无 task context 时任务评分字段为 null；
- 失败时仍生成质量报告和运行元数据。

### 11.4 可选集成测试

- 真实 MinerU 服务；
- 真实 OpenAI-compatible 服务；
- 真实公开网页。

这些测试必须显式启用，并在依赖不可用时跳过，不能影响默认离线测试。

## 12. MVP 验收标准

MVP 完成需要同时满足：

1. CLI 接受一个 URL 或本地 PDF。
2. URL 经 Trafilatura、PDF 经 MinerU 解析。
3. 解析结果统一为 `ParsedDocument` 和 `ContentBlock`。
4. PDF 请求包含 `return_md=true` 和 `return_content_list=true`。
5. LLM 通过 OpenAI-compatible 配置完成结构化抽取。
6. 每个发布的事实 claim 均有确定性验证通过的 evidence。
7. PDF evidence 包含页码、page index、bbox、block ID 和 quote。
8. 所有硬性 Gate 输出明确检查结果。
9. 通过 Gate 时输出标准 JSON、Markdown、质量报告和运行元数据。
10. 质量拒绝和技术失败使用不同退出码。
11. 默认自动化测试完全离线运行。
12. Parser、LLM Client、Evidence Verifier 和 Exporter 可独立替换或测试。
13. 不记录 API Key 等秘密信息。
14. 重复内容可由 SHA-256 哈希识别。
15. 实现符合 `agent-ready-data-standard.md` 的 V0.1 契约。

## 13. 实施顺序

1. 建立 Python 包、CLI 壳和配置加载。
2. 固定领域模型、JSON Schema、错误码和测试 fixture。
3. 实现 Source Resolver、哈希和输出运行目录。
4. 实现 Parser Protocol、Registry 和 TrafilaturaParser。
5. 使用录制响应实现 MinerUParser。
6. 实现 LLM Client 和结构化抽取契约。
7. 实现 Evidence Verifier。
8. 实现 Quality Gates 和 Scorer。
9. 实现 JSON/Markdown Exporter。
10. 串联单文档处理用例和退出码。
11. 完成离线端到端测试。
12. 在服务可达时执行 MinerU 与 LLM 集成验证。

实施阶段必须采用测试驱动方式：先固定行为和失败样例，再实现满足该行为的最小代码。

## 14. 风险与约束

- 当前执行环境无法访问 `192.168.0.213:8000`，实现时先依赖官方契约和录制 fixture，最终需要在能访问该服务的环境验证。
- MinerU 不同版本可能返回不同结构，所有兼容逻辑必须限制在适配器内。
- OCR 文本可能导致 quote 字符差异；归一化规则必须保守，不能把语义不同的文本判为匹配。
- LLM 的 claim 去重和语义支持判断存在不确定性；确定性存在性验证不能替代高风险领域人工审核。
- 网页内容可能受 robots、登录、脚本渲染和反爬影响；MVP 不承诺覆盖所有网站。
- `source_trust` 不等于事实正确性，评分理由必须可见。

## 15. 成功定义

本 MVP 的成功不是“能够抓网页或调用模型”，而是：

> 对一个 URL 或 PDF，系统能产生可复查、可重放、证据可定位、失败可解释，并符合统一数据契约的 Agent-ready 数据包。

同时，CLI 流程必须能够在不重写解析器、证据验证器、质量规则和导出器的前提下，被未来 API、MCP 和 Agent Harness 运行时复用。
