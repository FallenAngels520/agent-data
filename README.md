# Agent-ready Data CLI

将 URL 或 PDF 转换为带来源、证据定位、硬性质量门槛和可解释评分的 Agent-ready 数据包。

## 安装

需要 Python 3.10+ 和 `uv`：

```powershell
uv sync --extra dev
```

## 配置

CLI 会自动读取当前工作目录的 `.env`，显式系统环境变量优先。复制模板：

```powershell
Copy-Item .env.example .env
```

`.env` 已加入 `.gitignore`，不得提交真实密钥。

必填：

```powershell
$env:LLM_API_KEY = "..."
$env:LLM_MODEL = "..."
```

常用可选配置：

```powershell
$env:LLM_BASE_URL = "https://api.openai.com/v1"
$env:LLM_TIMEOUT_SECONDS = "120"
$env:MINERU_BASE_URL = "http://192.168.0.213:8000"
$env:MINERU_TIMEOUT_SECONDS = "600"
$env:PDF_PARSER = "mineru"
$env:URL_PARSER = "crawl4ai"
$env:CRAWL4AI_BASE_URL = "http://192.168.0.213:11235"
$env:CRAWL4AI_API_TOKEN = ""
$env:CRAWL4AI_TIMEOUT_SECONDS = "300"
$env:CRAWL4AI_POLL_INTERVAL_SECONDS = "1"
$env:ALLOW_PRIVATE_NETWORKS = "false"
```

默认禁止 URL 访问环回、链路本地和内网地址。MinerU 与 Crawl4AI 服务地址不经过 URL Source Resolver，因此仍可配置为内网服务。

## 使用

PDF：

```powershell
uv run agent-data process .\document.pdf --output .\output
```

URL：

```powershell
uv run agent-data process https://example.com/article --output .\output
```

带任务上下文：

```powershell
uv run agent-data process .\document.pdf `
  --task-context "提取与企业增长相关的事实" `
  --start-page 0 `
  --end-page 20
```

退出码：

| 代码 | 含义 |
|---:|---|
| 0 | Agent-ready |
| 2 | 被质量 Gate 拒绝 |
| 3 | 输入或配置错误 |
| 4 | 采集或解析失败 |
| 5 | LLM 失败 |
| 6 | 导出或内部失败 |

## 输出

```text
output/<document-id>/
├── raw/
├── parsed/
│   ├── document.md
│   └── content-blocks.json
├── agent-ready.json
├── agent-ready.md
├── quality-report.json
└── run.json
```

质量 Gate 未通过时不生成 `agent-ready.json` 和 `agent-ready.md`，但保留原始/解析内容、质量报告和运行记录。技术失败至少生成 `quality-report.json` 与 `run.json`，其路径通过 CLI 错误的 `details.output` 返回。

同一内容具有稳定文档 ID。重复执行不会覆盖已有结果，而是创建带数字后缀的新运行目录。

## MinerU 契约

PDF 适配器调用：

```text
POST {MINERU_BASE_URL}/file_parse
```

强制请求 `return_md=true` 和 `return_content_list=true`。适配器同时接受字符串化和已解码的 `content_list`，并将 `page_idx`、`bbox` 和内容块转换为内部统一模型。

同时请求 `return_middle_json=true`。MinerU 2.1.x 的 `content_list` 不包含 bbox，适配器会通过 `middle_json` 按页、块类型和文本补全位置；无法补全 bbox 的 PDF evidence 不通过质量 Gate。

## Crawl4AI 契约

URL 适配器默认调用本地或内网 Crawl4AI Docker API：

```text
POST {CRAWL4AI_BASE_URL}/crawl
GET {CRAWL4AI_BASE_URL}/task/{task_id}
```

若配置 `CRAWL4AI_API_TOKEN`，请求会携带 `Authorization: Bearer <token>`。适配器读取完成任务中的 `result.markdown`，也兼容对象形式的 `markdown.raw_markdown` 或 `markdown.fit_markdown`，并转换为内部 `content_blocks` 供证据定位和质量 Gate 使用。需要回退到纯 Python 网页解析时，可设置：

```powershell
$env:URL_PARSER = "trafilatura"
```

DeepSeek 官方 OpenAI-compatible 配置示例：

```powershell
$env:LLM_BASE_URL = "https://api.deepseek.com"
$env:LLM_MODEL = "deepseek-v4-flash"
```

## Agent Harness 边界

`ProcessDocument` 是 V0.1 的轻量 Harness。CLI 只负责装配和展示结果。后续 API/MCP 可以直接复用该用例。

- Harness：步骤编排、有限重试、运行事件和结果打包。
- LLM：提出 claim、quote 和候选 block ID。
- 确定性代码：Schema、哈希、证据匹配、页码/bbox、Gate 和评分公式。

## 开发验证

默认测试完全离线：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
.\.venv\Scripts\agent-data.exe --help
```

真实 MinerU 与 LLM 验证需要对应服务可访问和环境变量有效。默认测试不依赖这些外部状态。
