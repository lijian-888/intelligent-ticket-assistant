# 市场监管投诉举报工单智能处理 Demo

本项目是一个面向市场监督管理部门投诉、举报工单的智能处理 Demo。系统通过 FastAPI 提供接口，通过 LangGraph 编排工单处理流程，并结合本地或自有模型服务、embedding 模型、reranker 模型、PostgreSQL + pgvector 法律知识库，实现工单结构化、投诉举报识别、核心字段校验、退单建议、属地承办单位建议、情绪分析、职业索赔风险识别、法律条款检索和智能流转模拟。

当前项目主要用于公开演示和技术介绍，目的是模拟市场监管投诉举报工单系统如何接入智能体能力。Demo 阶段不会真实调用任何政务或业务系统接口，流转、退单、写回补充任务均为模拟动作。

## 主要能力

- 展示模拟工单列表和工单详情。
- 点击“智能流转”后执行完整工单处理流程。
- 判断工单性质：投诉、举报、无法判断。
- 校验核心字段是否完整。
- 对缺失核心字段的工单生成补充任务。
- 判断是否属于市场监管职责范围。
- 支持全国范围内投诉举报工单的演示处理。
- 根据省、市、区县等公开区划信息给出泛化承办单位建议。
- 分析投诉人情绪等级。
- 识别疑似职业索赔/职业打假风险，仅作工作人员预警，不改变普通工单处理流程。
- 对不应受理或不属于本单位处理的工单给出退单建议。
- 退单必须人工确认，不自动退单。
- 对高置信度、非退单场景，可模拟自动流转或自动加入补充任务表。
- 检索法律法规知识库，返回相关法律条款参考。
- 提供处理过程接口，可查看每个 LangGraph 节点的中间结果。

## 未展示内容

以下能力属于后续真实接入方向，当前公开 Demo 未包含真实账号、密钥、接口调用或外部服务依赖：

1. 阿里云电话 API 自动补充工单信息：系统可定时扫描补充工单数据库，识别需要补充核心字段的工单，通过自动外呼向提交人询问工单详情，再将采集到的补充内容作为结构化结果写回工单系统，实现补充工单的信息补全。公开仓库不包含真实外呼号码、录音、话术配置、阿里云访问密钥或业务系统写回接口。
2. 腾讯地图智能地址解析：可根据工单中提交的地址调用腾讯位置服务智能地址解析 API（官方文档：https://lbs.qq.com/service/webService/webServiceGuide/address/SmartGeocoder），获取标准化省、市、区县以及乡镇/街道信息，再结合属地路由规则判断工单应流转到对应的市场监管承办单位。公开 Demo 目前仅使用泛化规则模拟该过程，不包含腾讯地图 Key 或真实调用结果。

## 技术栈

- Python 3.12
- FastAPI
- Uvicorn
- LangGraph
- Pydantic v2
- SQLite，存储 Demo 补充任务
- PostgreSQL + pgvector，存储真实法律知识库向量
- bge-m3，用作 embedding 模型
- bge-reranker-v2-m3，用作 reranker 模型
- OpenAI-compatible LLM API，用作工单分类、退单预检、字段推断、情绪分析、职业索赔风险识别和整体复核

## 项目结构

```text
pythonProject/
  app/
    api.py                  FastAPI 接口和静态页面挂载
    graph.py                LangGraph 工作流编排
    nodes.py                工单处理节点实现
    models.py               Pydantic 数据模型
    mock_data.py            模拟工单数据
    llm_client.py           大模型调用客户端
    llm_schemas.py          LLM 输出 schema 校验模型
    embedding_client.py     embedding 调用客户端
    reranker_client.py      reranker 调用客户端
    legal_kb.py             法律条款检索入口
    legal_pg_kb.py          PostgreSQL + pgvector 法律知识库
    legal_docx_parser.py    docx/doc/pdf 法规文档解析和切片
    smart_transfer.py       智能流转自动化策略
    supplement.py           补充任务生成逻辑
    actions.py              模拟流转、退单、写回动作
    db.py                   SQLite Demo 数据库
    rules.py                静态规则配置
  web/
    index.html              工单列表页面
    detail.html             工单详情页面
    supplement-tasks.html   补充任务页面
    legal-kb.html           法律知识库查看页面
  legalDocx/                法律法规文档目录
  scripts/
    import_legal_docs.py    导入法律知识库脚本
    clean_legal_filenames.py 清洗法规文件名脚本
  tests/
    test_api.py             接口和核心逻辑测试
  data/
    demo.db                 SQLite Demo 数据库
  main.py                   本地启动入口
  requirements.txt          Python 依赖
  .env.example              配置模板
```

## 当前处理流程

完整处理链路如下：

```text
获取工单
  -> 结构化工单
  -> LLM 判断投诉/举报
  -> 法律条款向量检索
  -> 职业索赔风险识别
  -> 投诉/举报受理预检
  -> 如果已明确建议退单，跳过补全流程
  -> LLM 推断缺失核心字段
  -> 必填字段完整性校验
  -> 职责范围判断
  -> 推荐属地承办单位
  -> 情绪分析
  -> LLM 复核整体处理建议
  -> 决定动作：流转 / 补充信息 / 建议退单
  -> 返回最终结果或过程明细
```

其中 `retrieve_legal_references`、`assess_professional_claimant`、`precheck_acceptance` 这几个节点在 `structure_ticket` 后并行执行，减少整体处理耗时。

## 智能流转策略

接口：

```text
POST /tickets/{ticket_no}/smart-transfer
```

系统会先执行完整处理流程，再根据置信度决定是否自动模拟执行动作。

当前规则：

- 建议退单：必须人工确认，系统不自动退单。
- 待补充：置信度达到阈值时，自动写入补充核心字段任务表。
- 待流转：置信度达到阈值时，自动模拟调用流转接口。
- 置信度不足：只返回推荐动作，由工作人员人工确认。

阈值配置：

```env
AUTO_SUPPLEMENT_CONFIDENCE_THRESHOLD=0.80
AUTO_TRANSFER_CONFIDENCE_THRESHOLD=0.85
```

## 法律知识库检索

当前版本已经回退关键词召回，法律检索方式是：

```text
工单内容
  -> bge-m3 生成 query 向量
  -> PostgreSQL pgvector 和法律条文向量计算相似度
  -> 召回前 LEGAL_VECTOR_TOP_K 条
  -> bge-reranker-v2-m3 重排
  -> 按 LEGAL_MIN_RELEVANCE_SCORE 过滤
  -> 返回最多 LEGAL_DISPLAY_TOP_K 条
```

向量分数计算：

```sql
1 - (embedding <=> query_vector) AS vector_score
```

其中 `<=>` 是 pgvector 的 cosine distance。

重排分数来自 reranker 接口返回值。代码会读取：

```text
relevance_score / score / similarity
```

如果返回分数不在 0 到 1 之间，会用 sigmoid 归一化。

## 配置说明

复制配置模板：

```powershell
Copy-Item .env.example .env
```

常用配置：

```env
LLM_BASE_URL=
LLM_API_KEY=replace-with-your-api-key
LLM_MODEL=kimi-k2.6
LLM_TIMEOUT_SECONDS=60
LLM_CLASSIFY_TIMEOUT_SECONDS=45
LLM_FIELD_INFER_TIMEOUT_SECONDS=45
LLM_REVIEW_TIMEOUT_SECONDS=120
LLM_CONFIDENCE_THRESHOLD=0.75
LLM_ENABLE_REVIEW=false

EMBEDDING_BASE_URL=
EMBEDDING_API_KEY=
EMBEDDING_MODEL=bge-m3
EMBEDDING_TIMEOUT_SECONDS=30

RERANKER_BASE_URL=
RERANKER_API_KEY=
RERANKER_MODEL=bge-reranker-v2-m3
RERANKER_TIMEOUT_SECONDS=30

LEGAL_KB_BACKEND=auto
LEGAL_DATABASE_URL=
LEGAL_VECTOR_TOP_K=10
LEGAL_DISPLAY_TOP_K=3
LEGAL_MIN_RELEVANCE_SCORE=0.55
LEGAL_ENABLE_RERANKER=true
LEGAL_PREWARM_ON_STARTUP=true
```

注意：

- `.env` 不应提交到 Git。
- `LLM_BASE_URL`、`EMBEDDING_BASE_URL`、`RERANKER_BASE_URL` 均按 OpenAI-compatible 风格配置。
- 如果 `EMBEDDING_BASE_URL` 不是以 `/v1` 结尾，代码会自动请求 `/v1/embeddings`。
- 如果 `RERANKER_BASE_URL` 不是以 `/v1` 结尾，代码会先尝试 `/v1/rerank`，再尝试 `/rerank`。

## 安装依赖

建议使用项目虚拟环境：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

如果没有虚拟环境，可以先创建：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 启动项目

### 方式一：PyCharm 启动

运行：

```text
main.py
```

默认端口：

```text
http://127.0.0.1:8000
```

### 方式二：命令行启动 8020 端口

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8020
```

访问：

```text
http://127.0.0.1:8020/demo/
```

### 杀掉旧的 8020 进程

如果页面没有刷新出最新 mock 工单，通常是旧进程还在。可以执行：

```powershell
$listeners = Get-NetTCPConnection -LocalPort 8020 -State Listen -ErrorAction SilentlyContinue
foreach ($conn in $listeners) {
  Stop-Process -Id $conn.OwningProcess -Force
}
```

然后重新启动服务。

## 前端页面

```text
/demo/                       工单列表
/demo/detail.html            工单详情
/demo/supplement-tasks.html  补充任务列表
/demo/legal-kb.html          法律知识库片段查看
```

工单列表支持：

- 查看工单基本信息
- 智能流转
- 展示投诉/举报/无法判断
- 展示职业索赔风险
- 根据处理结果展示后续动作

## 常用接口

接口文档：

```text
http://127.0.0.1:8020/docs
```

主要接口：

```text
GET  /                         接口首页
GET  /tickets                  获取模拟工单列表
GET  /tickets/{ticket_no}      获取单条工单详情
POST /tickets/{ticket_no}/process
POST /tickets/{ticket_no}/smart-transfer
POST /tickets/{ticket_no}/process/steps
POST /tickets/{ticket_no}/supplement-task
GET  /supplement-tasks
GET  /db/status
GET  /llm/config
GET  /llm/health
GET  /embedding/config
GET  /retrieval/config
GET  /legal-kb/status
GET  /legal-kb/chunks
POST /legal-kb/import
POST /process-all
```

示例：

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8020/tickets" -Method Get
```

处理单条工单：

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8020/tickets/DEMO-TICKET-013/process" -Method Post
```

查看处理过程：

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8020/tickets/DEMO-TICKET-013/process/steps" -Method Post
```

## 法律知识库导入

法规文件放在：

```text
legalDocx/
```

支持：

- `.docx`
- `.doc`
- `.pdf`

当前 PDF 不做 OCR，适用于可复制文本型 PDF。

导入前需要配置：

```env
LEGAL_DATABASE_URL=<PostgreSQL 连接串>
EMBEDDING_BASE_URL=<模型服务地址>/v1
EMBEDDING_MODEL=bge-m3
```

导入命令：

```powershell
.\.venv\Scripts\python.exe scripts\import_legal_docs.py --path legalDocx --rebuild
```

说明：

- `--rebuild` 会先清空已有法律文档和切片，再重新导入。
- 导入时会解析法规文件、切分条文、调用 embedding 服务生成向量，并写入 PostgreSQL + pgvector。
- 后续检索时不会重复向量化所有法律条文，只会对当前工单内容生成 query 向量。
- 普通法律、条例、办法类文件优先按“第几条”切分；决定类文件和 `国令第777号` 优先按“一、二、三、”切分；仍无法识别结构时按段落兜底切分。

查看知识库状态：

```text
GET /legal-kb/status
```

查看切片：

```text
GET /legal-kb/chunks
```

按来源文件搜索切片：

```text
GET /legal-kb/chunks?source_file=食品安全
```

## 测试

运行全部测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

当前测试覆盖：

- 工单列表接口
- 单工单处理
- 智能流转
- 退单必须人工确认
- 补充任务生成
- LLM schema 校验回退
- 法律知识库解析
- embedding 和 reranker 响应解析
- 文件名清洗脚本

## 当前模拟工单

当前 `app/mock_data.py` 中包含 13 条模拟工单，覆盖：

- 普通消费投诉
- 食品安全举报
- 餐饮退款纠纷
- 非市场监管职责工单
- 职业索赔风险样例
- 核心字段缺失样例
- 无法判断投诉/举报样例
- 全国不同地区样例
- 无明确被举报对象但应补充信息样例
- 物业收费职责边界样例
- 企业长期未开业或连续停业举报
- 托管中心无证经营和食品经营许可举报
- 企业登记提交虚假住所材料举报

## 版本管理和回退

本项目使用 Git 管理版本，并使用中文 tag 方便演示回退。

查看历史：

```powershell
git log --oneline --decorate
```

推荐回退方式：

```powershell
git revert 提交ID
```

这会生成一个新的撤销提交，保留历史，适合日常演示和协作。

不建议随意使用：

```powershell
git reset --hard 提交ID
```

它会直接重置当前分支，可能丢掉后续提交。

如果只想基于旧版本开一个测试分支：

```powershell
git checkout -b 回退测试分支 v0.1.23_新增托管中心无证餐饮举报案例
```

PyCharm 中推荐：

```text
Git Log -> 右键某个提交 -> Revert Commit
```

## 公开发布注意事项

本仓库面向 GitHub 公开展示时，应按演示项目处理：

- 不提交真实 API Key、真实模型地址、数据库连接串或业务系统接口地址。
- `.env` 只在本地或部署环境维护，仓库仅保留 `.env.example` 占位配置。
- mock 工单必须使用虚构编号、虚构联系人、虚构地址和泛化组织名称。
- Demo 页面和接口只做模拟流转、模拟退单、模拟写回，不连接任何真实政务或业务系统。
- 法律条款检索结果只作为办理参考，不构成法律意见或行政决定依据。
- LLM 输出必须保留 schema 校验、置信度阈值和审计信息。
- 退单动作必须人工确认，不应完全自动化。
- 自动流转前要记录模型输出、置信度、prompt 版本、处理时间和最终动作。
- 接入真实系统前，应重新设计身份认证、权限控制、日志留存、数据脱敏和失败重试机制。
- 法律知识库应建立来源、版本、审核和更新机制，避免使用来源不明或授权不清的文件。

## 后续建议

- 为 PostgreSQL 向量字段增加 HNSW 或 IVFFLAT 索引，提升大量法规切片下的检索性能。
- 完善法规知识库的版本管理和增量导入。
- 优化 PDF 条文重组和异常切片清洗。
- 对 reranker 分数做更明确的展示解释，避免工作人员误解为概率。
- 将 LLM prompt 版本和 audit_id 持久化，满足审计要求。
- 接入真实工单系统前，先设计接口字段映射和失败重试机制。
