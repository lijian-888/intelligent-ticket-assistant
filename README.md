# 投诉举报工单智能处理

本项目是一个面向管理部门投诉、举报工单的智能处理 Demo。系统通过 FastAPI 提供接口，通过 LangGraph 编排工单处理流程，并结合本地或自有模型服务、embedding 模型、reranker 模型、PostgreSQL + pgvector 法律知识库，实现工单结构化、投诉举报识别、核心字段校验、退单建议、属地承办单位建议、情绪分析、职业索赔风险识别、法律条款检索和智能流转模拟。

当前项目主要用于公开演示和技术介绍，目的是模拟投诉举报工单系统如何接入智能体能力。Demo 阶段不会真实调用任何政务或业务系统接口，流转、退单、写回补充任务均为模拟动作。

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

## 界面预览

以下截图均为脱敏后的公开 Demo 数据。

### 工单工作台

<p>
  <img src="images/工单管理系统.png" alt="工单管理系统工作台" width="100%">
</p>

### 智能流转结果

<table>
  <tr>
    <td width="50%">
      <img src="images/智能流转结果展示.png" alt="智能流转结果展示" width="100%">
    </td>
    <td width="50%">
      <img src="images/智能流转结果展示(补充).png" alt="智能流转结果补充展示" width="100%">
    </td>
  </tr>
</table>

### 知识库与补充任务

<p>
  <img src="images/知识库切片预览.png" alt="法律知识库切片预览" width="100%">
</p>

<p>
  <img src="images/补充信息任务表.png" alt="补充信息任务表" width="100%">
</p>

## 关键接口

1. 智能联络中心-自动补充工单信息：智能联络中心是阿里云整合语音通信能力、语言大模型能力为企业打造的高效联络中心系统，助力企业通过语音通话快捷高效地联络用户。系统可定时扫描补充工单数据库，识别需要补充核心字段的工单，通过自动外呼向提交人询问工单详情，再将采集到的补充内容作为结构化结果写回工单系统，实现补充工单的信息补全。公开仓库不包含真实外呼号码、录音、话术配置、阿里云访问密钥或业务系统写回接口。<https://help.aliyun.com/zh/aiccs/product-overview/what-is-artificial-intelligence-cloud-call-service?spm=a2c4g.11186623.help-menu-126730.d_0_0_0.75e9166aytmX8K>
2. 腾讯地图智能地址解析：可根据工单中提交的地址调用腾讯位置服务智能地址解析 API，获取标准化省、市、区县以及乡镇/街道信息，再结合属地路由规则判断工单应流转到对应的市场监管承办单位。公开 Demo 目前仅使用泛化规则模拟该过程，不包含腾讯地图 Key 或真实调用结果。<https://lbs.qq.com/service/webService/webServiceGuide/address/SmartGeocoder>

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

## 真实能力接入总览

要把本 Demo 跑成一个可接入真实模型和真实法律知识库的智能体，需要准备四类能力：

1. PostgreSQL + pgvector：保存法规文档切片和向量。
2. embedding 模型服务：把法规条文和工单内容转成向量，本项目默认使用 `bge-m3`。
3. reranker 模型服务：对向量召回的候选条文重排，本项目默认使用 `bge-reranker-v2-m3`。
4. OpenAI-compatible LLM 服务：执行投诉/举报识别、核心字段推断、情绪分析、职业索赔风险识别、退单预检和整体复核。

项目所有真实服务配置都写在项目根目录的 `.env` 文件中。不要把真实 `.env` 提交到 GitHub。

### 1. 进入项目目录

以下命令均在 Windows PowerShell 中运行：

```powershell
cd D:\IDEA-Project\intelligent-ticket-assistant
```

### 2. 创建 Python 环境并安装依赖

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

如果已经存在 `.venv`，只需要执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 3. 启动 PostgreSQL + pgvector

推荐使用 Docker，因为 pgvector 扩展已经打包在镜像中。

在任意 PowerShell 窗口运行：

```powershell
docker volume create ticket_pgvector_data

docker run --name ticket-pgvector `
  -e POSTGRES_USER=ticket `
  -e POSTGRES_PASSWORD=ticket_password_please_change `
  -e POSTGRES_DB=ticket_kb `
  -p 5432:5432 `
  -v ticket_pgvector_data:/var/lib/postgresql/data `
  -d pgvector/pgvector:pg16
```

初始化 pgvector 扩展：

```powershell
docker exec -it ticket-pgvector psql -U ticket -d ticket_kb -c "CREATE EXTENSION IF NOT EXISTS vector;"
docker exec -it ticket-pgvector psql -U ticket -d ticket_kb -c "\dx vector"
```

如果你已经有 PostgreSQL，并且已经安装 pgvector 扩展，也可以手动创建数据库：

```powershell
psql -U postgres -c "CREATE DATABASE ticket_kb;"
psql -U postgres -d ticket_kb -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

本项目首次连接知识库时会自动创建以下表：

- `legal_documents`：法规文档元数据。
- `legal_chunks`：法规切片、embedding 向量、来源文件、条号、章节等。

### 4. 配置模型和知识库连接

复制配置模板：

```powershell
Copy-Item .env.example .env
notepad .env
```

在 `.env` 中填写真实服务地址、模型名和数据库连接。示例：

```env
# OpenAI-compatible LLM。可以填写到 /v1，也可以填写服务根地址，代码会自动拼接 /v1/chat/completions。
LLM_BASE_URL=http://127.0.0.1:8010/v1
LLM_API_KEY=replace-with-your-real-key
LLM_MODEL=your-chat-model
LLM_TIMEOUT_SECONDS=60
LLM_CLASSIFY_TIMEOUT_SECONDS=45
LLM_FIELD_INFER_TIMEOUT_SECONDS=45
LLM_REVIEW_TIMEOUT_SECONDS=120
LLM_CONFIDENCE_THRESHOLD=0.75
LLM_ENABLE_REVIEW=true

# OpenAI-compatible embeddings。代码调用 /v1/embeddings。
EMBEDDING_BASE_URL=http://127.0.0.1:8011/v1
EMBEDDING_API_KEY=replace-with-your-real-key-or-empty
EMBEDDING_MODEL=bge-m3
EMBEDDING_TIMEOUT_SECONDS=30

# reranker。代码优先调用 /v1/rerank，也兼容 /rerank。
RERANKER_BASE_URL=http://127.0.0.1:8012/v1
RERANKER_API_KEY=replace-with-your-real-key-or-empty
RERANKER_MODEL=bge-reranker-v2-m3
RERANKER_TIMEOUT_SECONDS=30

# PostgreSQL + pgvector 法律知识库。
LEGAL_KB_BACKEND=postgres
LEGAL_DATABASE_URL=postgresql://ticket:ticket_password_please_change@127.0.0.1:5432/ticket_kb
LEGAL_IMPORT_BATCH_SIZE=16
LEGAL_VECTOR_TOP_K=10
LEGAL_DISPLAY_TOP_K=3
LEGAL_MIN_RELEVANCE_SCORE=0.55
LEGAL_ENABLE_RERANKER=true
LEGAL_PREWARM_ON_STARTUP=true

# 自动化动作阈值。
AUTO_SUPPLEMENT_CONFIDENCE_THRESHOLD=0.80
AUTO_TRANSFER_CONFIDENCE_THRESHOLD=0.85
```

模型接口要求：

- LLM 服务需要兼容 OpenAI `POST /v1/chat/completions`，并支持 JSON 输出。
- embedding 服务需要兼容 OpenAI `POST /v1/embeddings`，返回 `data[index].embedding`。
- reranker 服务需要支持 `POST /v1/rerank` 或 `POST /rerank`，入参为 `model`、`query`、`documents`、`top_n`。

如果没有配置 `LLM_BASE_URL` 或 `LLM_API_KEY`，系统会使用规则兜底，情绪分析、职业索赔风险、字段推断等 LLM 能力会降级。  
如果没有配置 `EMBEDDING_BASE_URL`，系统会使用本地确定性向量兜底，只适合 Demo，不适合真实检索。真实知识库必须配置 embedding 服务后再导入。

### 5. 准备法规文件

把法规、规章、规范性文件放入项目根目录的 `legalDocx/`：

```text
legalDocx/
  中华人民共和国消费者权益保护法.docx
  中华人民共和国食品安全法.docx
  ...
```

支持文件类型：

- `.docx`
- `.doc`
- `.pdf`

注意：

- `.pdf` 只支持可复制文本型 PDF，不做 OCR。
- `.doc` 需要安装 LibreOffice 用于转换为 `.docx`。
- 如果 LibreOffice 没有加入系统 PATH，需要在 `.env` 中配置：

```env
LIBREOFFICE_PATH=C:\Program Files\LibreOffice\program\soffice.exe
```

### 6. 预览法规切片

先启动服务：

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

打开浏览器查看切片预览：

```text
http://127.0.0.1:8000/demo/legal-kb.html
```

也可以直接调用接口：

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/legal-kb/preview?path=legalDocx&limit=20" -Method Get
```

切片规则：

- 普通法律、条例、办法优先按“第几条”切分。
- 决定类文件优先按“一、二、三、”切分。
- 无法识别条文结构时按段落兜底切分。

### 7. 导入法规到 PostgreSQL + pgvector

确认 `.env` 已配置：

- `LEGAL_DATABASE_URL`
- `EMBEDDING_BASE_URL`
- `EMBEDDING_MODEL`

在项目根目录运行：

```powershell
.\.venv\Scripts\python.exe scripts\import_legal_docs.py --path legalDocx --rebuild
```

导入脚本会执行：

1. 读取 `legalDocx/` 下的 `.docx`、`.doc`、`.pdf`。
2. 解析法规名称、章节、条号和正文。
3. 按条文或段落切片。
4. 调用 `EMBEDDING_BASE_URL` 的 `/v1/embeddings` 生成向量。
5. 写入 PostgreSQL 的 `legal_documents` 和 `legal_chunks` 表。

成功后会输出类似：

```json
{
  "document_count": 9,
  "chunk_count": 1154,
  "embedding_model": "bge-m3",
  "embedding_dimension": 1024,
  "rebuild": true
}
```

如果更换了 embedding 模型或向量维度，建议重新执行：

```powershell
.\.venv\Scripts\python.exe scripts\import_legal_docs.py --path legalDocx --rebuild
```

原因是查询时会按 `embedding_dimension` 过滤，导入向量和查询向量维度必须一致。

### 8. 验证知识库和模型配置

启动服务：

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

检查 LLM 配置：

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/llm/config" -Method Get
Invoke-RestMethod -Uri "http://127.0.0.1:8000/llm/health" -Method Get
```

检查 embedding 配置：

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/embedding/config" -Method Get
```

检查知识库导入状态：

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/legal-kb/status" -Method Get
```

检查完整检索配置：

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/retrieval/config" -Method Get
```

查看已入库切片：

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/legal-kb/chunks?limit=10" -Method Get
```

如果返回中看到：

- `legal_kb.configured=true`
- `chunk_count > 0`
- `embedding.configured=true`
- `embedding.last_embedding_source=remote`

说明真实知识库和 embedding 服务已经接通。

LLM 会参与以下节点：

- `classify_case_nature`：判断投诉、举报、无法判断。
- `infer_missing_fields`：推断缺失核心字段。
- `analyze_emotion`：情绪等级和调解建议。
- `assess_professional_claimant`：职业索赔/职业打假风险预警。
- `precheck_acceptance`：受理预检和退单建议。
- `review_overall_result`：整体复核，受 `LLM_ENABLE_REVIEW` 控制。

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

配置 `LEGAL_DATABASE_URL` 后，系统优先使用 PostgreSQL + pgvector 真实知识库。未配置真实知识库时，才会回退到项目内置的 Demo 法律条文。

真实知识库检索方式是：

```text
工单内容
  -> bge-m3 生成 query 向量
  -> PostgreSQL pgvector 和法律条文向量计算相似度
  -> 召回前 LEGAL_VECTOR_TOP_K 条
  -> bge-reranker-v2-m3 重排
  -> 按 LEGAL_MIN_RELEVANCE_SCORE 过滤
  -> 返回最多 LEGAL_DISPLAY_TOP_K 条
```


## 配置项速查

完整配置流程见上文“真实能力接入总览”。常用配置文件位于项目根目录：

```text
.env.example  配置模板，可提交
.env          本地真实配置，不要提交
```

核心配置项：

```text
LLM_BASE_URL                  OpenAI-compatible LLM 服务地址
LLM_API_KEY                   LLM 访问密钥
LLM_MODEL                     LLM 模型名称
EMBEDDING_BASE_URL            OpenAI-compatible embedding 服务地址
EMBEDDING_MODEL               embedding 模型名称，默认 bge-m3
RERANKER_BASE_URL             reranker 服务地址
RERANKER_MODEL                reranker 模型名称，默认 bge-reranker-v2-m3
LEGAL_DATABASE_URL            PostgreSQL + pgvector 连接串
LEGAL_VECTOR_TOP_K            向量召回候选条数
LEGAL_DISPLAY_TOP_K           最终展示法律条文数量
LEGAL_MIN_RELEVANCE_SCORE     法律条文相关性过滤阈值
LEGAL_ENABLE_RERANKER         是否启用 reranker
```


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

### 方式：PyCharm 启动

运行：

```text
main.py
```

默认端口：

```text
http://127.0.0.1:8000
```


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

接口文档：（启动成功后访问-前端展示页面）

```text
http://127.0.0.1:8000/docs
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
GET  /legal-kb/preview
GET  /legal-kb/chunks
POST /legal-kb/import
POST /process-all
```

示例：

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/tickets" -Method Get
```

处理单条工单：

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/tickets/DEMO-TICKET-013/process" -Method Post
```

查看处理过程：

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/tickets/DEMO-TICKET-013/process/steps" -Method Post
```

## 知识库命令速查

完整 PostgreSQL + pgvector 安装、`.env` 配置、法规导入和检索验证流程见上文“真实能力接入总览”。

预览法规文件切片，不写入数据库：

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/legal-kb/preview?path=legalDocx&limit=20" -Method Get
```

导入法规文件到 PostgreSQL + pgvector：

```powershell
.\.venv\Scripts\python.exe scripts\import_legal_docs.py --path legalDocx --rebuild
```

查看知识库状态和切片：

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/legal-kb/status" -Method Get
Invoke-RestMethod -Uri "http://127.0.0.1:8000/legal-kb/chunks?limit=10" -Method Get
Invoke-RestMethod -Uri "http://127.0.0.1:8000/legal-kb/chunks?source_file=食品安全" -Method Get
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

