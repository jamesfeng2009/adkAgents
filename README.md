# logistics_agent (Google ADK + Mock Logistics API)

## 背景与目标

本项目使用 **Google Agent Development Kit (ADK)** 构建一个智能 Agent，并基于给定 API 文档实现 **物流相关能力**。
由于没有真实 API 凭证与服务端环境，本项目采用 **Mock** 的方式模拟 API 响应，确保：

- 能在本地跑通 Agent + Tools
- Mock 响应结构与文档示例一致（便于后续对接真实服务）

## 需求拆解

核心业务需求：

- 查询订单号 `#12345` 的物流状态（轨迹查询）
- 创建从深圳到洛杉矶的新货运单（使用 `createForecast` 语义）

工程化需求：

- 代码结构清晰、可扩展
- 错误处理与边界场景覆盖
- 工具返回结构统一
- 关键 payload 引入 schema + 校验
- 对“名称/编码”选择做更贴近真实交互的匹配策略

## 方案设计与思考过程

### 1) 为什么选择单 Agent + 多 Tools（而非 Multi-Agent）

本需求的复杂度主要来自：

- 需要调用多个接口（轨迹、下单、字典查询）
- 需要在下单前根据字典接口选择/填充字段

这更像一个 **multi-tool** 场景，ADK 的 `Agent(tools=[...])` 足以完成。

只有当流程编排明显复杂（如多角色协作、多阶段审批、复杂路由、多子系统协调）时，才建议引入 multi-agent（`sub_agents`）。

### 2) 文档抓取与 Mock 策略

文档页面通过 `api/doc?api=xxx` 的方式切换不同接口。
因此 Mock 的实现策略是：

- 依据每个接口页面中的 **请求报文示例** 与 **响应报文示例**
- 将关键接口抽象为 Python 方法（如 `track/create_forecast_order/insurance/currency/...`）
- 对外暴露为 ADK tools

Mock 的目标不是模拟所有业务规则，而是：

- **结构对齐**（字段名、层级、示例风格）
- **可调试**（在 meta 中回显 request payload，便于验证）

### 3) 为什么要做“字典接口 mock + 自动映射填充”

创建订单接口存在多个字段依赖字典接口：

- `insurancetypepkid` / `insurancecurrency`
- `declaretypepkid`
- `producttypepkid`

真实场景中前端/调用方通常会：

- 先请求字典接口拿到可选项
- 用户选择后再提交下单

为了更贴近真实交互，本项目提供两种层级的能力：

- 低阶：单独 tools 返回字典接口 `raw` 响应
- 高阶：用户提供“人类可读”的选择（如“普货”“货物运输险”“USD”），Agent 自动映射到 code 并生成 payload

### 4) 统一 Tool 返回结构的原因（方向 1）

为了避免 LLM 在多工具编排时误判结构，本项目强制所有 tools 返回统一 envelope：

```json
{ "status": "success|error", "data": { ... } | null, "error": { ... } | null }
```

其中：

- 如果工具本质返回“文档 API 风格响应”，则放在 `data.raw`
- 错误统一放在 `error.message` + 补充字段（如 `validation_errors`）

这显著提升：

- agent 编排可预期性
- 前端/调用方消费一致性

### 5) Schema + 校验（方向 2）

下单 payload 字段多且层级深，用 dict 直接拼装容易出错。
因此引入 `TypedDict` + 校验函数：

- `logistics_agent/schemas.py`
  - 定义 `CreateForecastPayload` 相关结构
  - `validate_create_forecast_payload(payload)` 返回错误列表

并在 `build_create_forecast_payload` 中强制校验：

- 校验通过：返回 `status=success`
- 校验失败：返回 `status=error` + `validation_errors`

### 6) 增强 name/code 匹配策略（方向 3）

真实用户输入往往并不严格等于字典值，例如：

- “普货类” vs “普货”
- “货物运输险（推荐）” vs “货物运输险”

因此匹配策略做了增强：

- 忽略大小写与多余空格（normalize）
- 支持子串匹配（contains match）
- 若匹配不唯一，则报错并返回候选列表（避免误选）


## 项目结构

```
adkAgents/
  logistics_agent/
    __init__.py
    agent.py
    mock_logistics_api.py
    schemas.py
  requirements.txt
  README.md
```

## 主要工具（Tools）

- 字典查询：
  - `get_insurance_types`
  - `get_currencies`
  - `get_declare_types`
  - `get_customs_types`
  - `get_terms_of_sale`
  - `get_export_reasons`
  - `get_product_types`

- 业务能力：
  - `query_order_status`
  - `build_create_forecast_payload`
  - `create_forecast_order_with_preferences`
  - `submit_forecast_order`
  - `submit_forecast_order_json`
  - `submit_forecast_order_from_text`
  - `create_shipment`

## 最小可运行 Demo（推荐流程）

约定：

- 创建订单使用 `createForecast` mock（即 `create_forecast_order_with_preferences` / `submit_forecast_order_*` 内部调用的 mock）。
- 查询物流状态使用 `waybillnumber`（运单号）作为输入（即 `query_order_status(waybillnumber)`）。

### 1) 一次性创建订单（自然语言）

在 `adk run logistics_agent` 中输入：

```text
请立刻调用 submit_forecast_order_from_text，并只返回工具 JSON（不要总结）：text="从深圳到洛杉矶；customernumber1=T620200611-1001；收件国家=US；收件人=John；收件地址=123 Main St；城市=Los Angeles；邮编=90001；省州=CA；投保=是；保额=100；险种=货物运输险；币别=人民币；报关类型=需要报关；物品类别=普货"
```

成功判据：返回 JSON 中 `status=success`，并在 `data.result.data[0]` 中能看到：

- `systemnumber`：订单号（建议作为 `order_id`）
- `waybillnumber`：运单号（建议作为 `tracking_id`，用于查询状态）
- `childs[].tracknumber`：子单追踪号（如存在多件/多子单）

### 2) 查询订单状态（按运单号 waybillnumber）

将上一步返回的 `waybillnumber` 填入：

```text
请立刻调用 query_order_status("EVxxxxxxxxxxxxCN")，并只返回工具 JSON（不要总结）：
```

### 3) waybillnumber 为空时：通过获取单号接口补齐

根据接口文档，`createForecast` 返回的 `waybillnumber` 可能为空，此时需要调用 **获取单号** 接口。

在本项目中对应 tool 为：`get_waybillnumbers`。

在 `adk run logistics_agent` 中输入（customernumber 用下单时的 `customernumber1`）：

```text
请立刻调用 get_waybillnumbers，并只返回工具 JSON（不要总结）：customernumber=["T620200611-1001"]
```

成功后可在返回的 `data.raw.data.customernumber[0].waybillnumber` 获取运单号，再用 `query_order_status(waybillnumber)` 查询轨迹。

### 推荐的终端使用方式（减少模型误解/追问）

在 `adk run logistics_agent` 的交互模式中，**直接粘贴多行 JSON** 有时会被模型当作普通文本处理，导致反复追问或参数被改写。

推荐使用 `submit_forecast_order_json`，并将 JSON 作为 **单个字符串参数** 传入：

```text
请立刻调用 submit_forecast_order_json，并只返回工具 JSON（不要总结）：
"{\"origin_city\":\"深圳\",\"destination_city\":\"洛杉矶\",\"customernumber1\":\"T620200611-1001\",\"consignee_countrycode\":\"US\",\"consigneename\":\"John\",\"consigneeaddress1\":\"123 Main St\",\"consigneecity\":\"Los Angeles\",\"consigneezipcode\":\"90001\",\"consigneeprovince\":\"CA\",\"insurance_enabled\":true,\"insurance_value\":100,\"insurance_type_name\":\"货物运输险\",\"insurance_currency_code\":\"USD\",\"product_type_name\":\"普货\",\"declare_type_name\":\"不需报关\"}"
```

如果你希望 **只用自然语言**（不写 JSON），推荐使用 `submit_forecast_order_from_text`，并将内容压缩为一行 `key=value` 风格，减少模型丢字段的概率：

```text
请调用 submit_forecast_order_from_text，只调用一次，并只返回工具 JSON（不要总结）：
text="从深圳到洛杉矶；customernumber1=T620200611-1001；收件国家=US；收件人=John；收件地址=123 Main St；城市=Los Angeles；邮编=90001；省州=CA；投保=是；保额=100；险种=货物运输险；币别=USD；物品类别=普货；报关类型=不需报关"
```

### 幂等（Idempotency）：避免模型重试导致重复下单

终端交互中，LLM 可能因为自我修正/追问而 **重复调用下单工具**。为了避免重复创建订单：

- `submit_forecast_order_from_text` 会基于解析出的结构化字段生成稳定 `request_id`（hash）
- 同一个 `request_id` 在单次进程生命周期内只会真实下单一次
- 如果再次触发相同请求，会直接返回首次成功的缓存结果，并在返回里标记：
  - `data.request_id`
  - `data.idempotent_replay=true`

## 快速验证

在配置ADK之前，你可以先运行本地测试来验证核心功能：

```bash
python test_agent.py
```

这将测试所有Mock API接口和Agent工具，确保业务逻辑正确。

### 验证报关功能
```bash
# 测试报关订单创建
python create_shenzhen_to_la_order.py

# 或者运行完整的订单调试测试
python test_order_debug.py
```

这些测试将验证：
- 报关类型的智能识别和映射
- 完整订单创建流程
- 中文字段的正确处理
- 投保信息的完整性验证

## 如何运行

### 1) 安装依赖

```bash
pip install -r requirements.txt
```

### 2) 配置模型密钥（必需）

ADK 默认使用 Gemini，需要 API Key。

安全提醒：

- 不要在聊天、截图、日志中明文分享 API Key。
- 不要把 `.env` 提交到 git（建议加入 `.gitignore`）。
- 如果不小心泄露了 Key，请立刻在控制台吊销并重新生成。

创建文件：`adkAgents/logistics_agent/.env`

```
GOOGLE_GENAI_USE_VERTEXAI=FALSE
GOOGLE_API_KEY=PASTE_YOUR_ACTUAL_API_KEY_HERE
```

或者你也可以使用环境变量（不落盘）：

```bash
export GOOGLE_GENAI_USE_VERTEXAI=FALSE
export GOOGLE_API_KEY=PASTE_YOUR_ACTUAL_API_KEY_HERE
```

### 3) 运行

在 `adkAgents/` 目录执行：

- 终端：

```bash
adk run logistics_agent
```

- Dev UI：

```bash
adk web
```


### 示例1：查询订单状态
```bash
# 在ADK终端中
adk run logistics_agent

# 输入：
查询订单 #12345 的物流状态

# 或直接调用工具：
请调用 query_order_status("12345")
```

### 示例2：创建新货运单
```bash
# 自然语言方式：
请调用 submit_forecast_order_from_text，text="从深圳到洛杉矶；customernumber1=T620200611-1001；收件国家=US；收件人=John；收件地址=123 Main St；城市=Los Angeles；邮编=90001；省州=CA；投保=是；保额=100；险种=货物运输险；币别=USD；物品类别=普货；报关类型=不需报关"

# JSON方式：
请调用 submit_forecast_order_json，order_json="{\"origin_city\":\"深圳\",\"destination_city\":\"洛杉矶\",\"customernumber1\":\"T620200611-1001\",\"consignee_countrycode\":\"US\",\"consigneename\":\"John\",\"consigneeaddress1\":\"123 Main St\",\"consigneecity\":\"Los Angeles\",\"consigneezipcode\":\"90001\",\"consigneeprovince\":\"CA\",\"insurance_enabled\":true,\"insurance_value\":100,\"insurance_type_name\":\"货物运输险\",\"insurance_currency_code\":\"USD\",\"product_type_name\":\"普货\",\"declare_type_name\":\"不需报关\"}"
```

### 示例3：带报关的完整订单（实际测试验证）
```bash
# 完整的报关订单示例（已验证成功）：
请调用 submit_forecast_order_from_text，text="从深圳到洛杉矶；customernumber1=T620200611-1001；consignee_countrycode=US；收件人=John Smith；收件地址=123 Main St；城市=Los Angeles；邮编=90001；省州=CA；投保=是；保额=100；险种=货物运输险；币别=USD；物品类别=普货；报关类型=需要报关"

# 成功返回示例：
{
  "status": "success",
  "data": {
    "order_id": "14764302427194",
    "tracking_id": "EV35156841253CN", 
    "child_tracking_ids": ["1Z5F4CF3D61E37"],
    "result": {
      "code": 0,
      "msg": "调用成功",
      "data": [{
        "code": 0,
        "msg": "下单成功",
        "customernumber": "T620200611-1001",
        "systemnumber": "14764302427194",
        "waybillnumber": "EV35156841253CN"
      }]
    }
  }
}
```

## 备注

- Mock 仅用于开发与演示，完全符合API文档规范
- 后续接入真实服务时，只需替换 `MockLogisticsApi` 为真实 HTTP Client
- 保留了完整的工具层和验证逻辑，便于无缝切换
