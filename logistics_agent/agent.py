import json
import re
from typing import Any

from google.adk.agents import Agent

from .mock_logistics_api import MockLogisticsApi
from .schemas import validate_create_forecast_payload


_api = MockLogisticsApi()


DEFAULT_CHANNEL_ID = "HK_TNT"
DEFAULT_PACKAGE_TYPE_CODE = "O"
DEFAULT_GOODS_TYPE_CODE = "WPX"
DEFAULT_DECLARE_CURRENCY = "USD"


def _tool_call(func, *, tool_name: str, **kwargs) -> dict:
    try:
        result = func(**kwargs)
        return _ok(raw=result)
    except Exception as e:
        return _err(f"failed to call tool {tool_name}", reason=str(e))


def _ok(**data) -> dict:
    return {"status": "success", "data": data, "error": None}


def _err(message: str, **details) -> dict:
    return {"status": "error", "data": None, "error": {"message": message, **details}}


def _normalize_text(s: str) -> str:
    return " ".join(s.strip().lower().split())


def _to_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        s = _normalize_text(v)
        return s in {"1", "true", "yes", "y", "on", "enable", "enabled", "是"}
    return False


def _pick_by_code_or_default(options: list[dict], code, *, label: str) -> dict:
    if code is None or code == "":
        if not options:
            raise ValueError(f"No options available for {label}")
        return options[0]
    for opt in options:
        if str(opt.get("code")) == str(code):
            return opt
    raise ValueError(f"Invalid {label} code: {code}")


def _pick_by_name_or_default(
    options: list[dict],
    name: str | None,
    *,
    label: str,
    name_keys: tuple[str, ...] = ("name", "cnname", "enname", "productname"),
) -> dict:
    if name is None or name.strip() == "":
        if not options:
            raise ValueError(f"No options available for {label}")
        return options[0]
    needle = _normalize_text(name)

    exact_matches: list[dict] = []
    contains_matches: list[dict] = []
    seen_exact: set[int] = set()
    seen_contains: set[int] = set()
    for opt in options:
        for k in name_keys:
            v = opt.get(k)
            if not isinstance(v, str):
                continue
            hay = _normalize_text(v)
            if hay == needle:
                oid = id(opt)
                if oid not in seen_exact:
                    exact_matches.append(opt)
                    seen_exact.add(oid)
            elif needle in hay:
                oid = id(opt)
                if oid not in seen_contains:
                    contains_matches.append(opt)
                    seen_contains.add(oid)

    if len(exact_matches) == 1:
        return exact_matches[0]
    if len(exact_matches) > 1:
        raise ValueError(
            f"Ambiguous {label} name: {name}. Candidates: {[m.get('name') or m.get('cnname') or m.get('enname') for m in exact_matches]}"
        )
    if len(contains_matches) == 1:
        return contains_matches[0]
    if len(contains_matches) > 1:
        raise ValueError(
            f"Ambiguous {label} name: {name}. Candidates: {[m.get('name') or m.get('cnname') or m.get('enname') for m in contains_matches]}"
        )

    raise ValueError(f"Invalid {label} name: {name}")


def get_insurance_types() -> dict:
    return _tool_call(_api.insurance, tool_name="get_insurance_types")


def get_currencies() -> dict:
    return _tool_call(_api.currency, tool_name="get_currencies")


def get_declare_types() -> dict:
    return _tool_call(_api.declaretype, tool_name="get_declare_types")


def get_customs_types() -> dict:
    return _tool_call(_api.customstype, tool_name="get_customs_types")


def get_terms_of_sale() -> dict:
    return _tool_call(_api.termsofsalecode, tool_name="get_terms_of_sale")


def get_export_reasons() -> dict:
    return _tool_call(_api.exportreasoncode, tool_name="get_export_reasons")


def get_product_types() -> dict:
    return _tool_call(_api.get_product_type, tool_name="get_product_types")


def build_create_forecast_payload(
    customernumber1: str,
    consignee_countrycode: str,
    consigneename: str,
    consigneeaddress1: str,
    consigneecity: str,
    consigneezipcode: str,
    consigneeprovince: str,
    channelid: str = DEFAULT_CHANNEL_ID,
    number: int = 1,
    forecastweight: float = 1.0,
    isinsurance: int = 0,
    insurancevalue: float | None = None,
    insurancetypepkid: int | None = None,
    insurancecurrency: str | None = None,
    declaretypepkid: int | None = None,
    producttypepkid: int | None = None,
) -> dict:
    """Build a complete createForecast request payload and auto-fill dependent fields."""
    try:
        if not customernumber1:
            raise ValueError("customernumber1 is required")
        if not channelid:
            raise ValueError("channelid is required")
        if not consignee_countrycode:
            raise ValueError("countrycode is required")
        if not consigneename:
            raise ValueError("consigneename is required")
        if not consigneeaddress1:
            raise ValueError("consigneeaddress1 is required")
        if not consigneecity:
            raise ValueError("consigneecity is required")
        if not consigneezipcode:
            raise ValueError("consigneezipcode is required")
        if not consigneeprovince:
            raise ValueError("consigneeprovince is required")

        insurance_options = _api.insurance().get("data", [])
        currency_options = _api.currency().get("data", [])
        declare_options = _api.declaretype().get("data", [])
        product_options = _api.get_product_type().get("data", [])

        selected_declare = _pick_by_code_or_default(
            declare_options, declaretypepkid, label="declaretypepkid"
        )
        selected_product = _pick_by_code_or_default(
            product_options, producttypepkid, label="producttypepkid"
        )

        order: dict = {
            "channelid": channelid,
            "customernumber1": customernumber1,
            "customernumber2": "",
            "number": number,
            "isbattery": "0",
            "isinsurance": str(isinsurance),
            "forecastweight": str(forecastweight),
            "packagetypecode": DEFAULT_PACKAGE_TYPE_CODE,
            "goodstypecode": DEFAULT_GOODS_TYPE_CODE,
            "countrycode": consignee_countrycode,
            "consigneename": consigneename,
            "consigneecorpname": consigneename,
            "consigneeaddress1": consigneeaddress1,
            "consigneeaddress2": "",
            "consigneeaddress3": "",
            "consigneecity": consigneecity,
            "consigneezipcode": consigneezipcode,
            "consigneeprovince": consigneeprovince,
            "consigneetel": "",
            "consigneemobile": "",
            "consigneehousenumber": "",
            "consigneetaxnumber": "",
            "consigneeemail": "",
            "declaretypepkid": selected_declare.get("code"),
            "producttypepkid": selected_product.get("code"),
        }

        if int(isinsurance) == 1:
            if insurancevalue is None:
                raise ValueError("insurancevalue is required when isinsurance=1")
            selected_ins = _pick_by_code_or_default(
                insurance_options, insurancetypepkid, label="insurancetypepkid"
            )
            selected_cur = _pick_by_code_or_default(
                currency_options, insurancecurrency, label="insurancecurrency"
            )
            order.update(
                {
                    "insurancevalue": str(insurancevalue),
                    "insurancetypepkid": selected_ins.get("code"),
                    "insurancecurrency": selected_cur.get("code"),
                }
            )

        payload = {
            "authorization": {"code": _api.customer_code, "token": _api.token},
            "datas": [
                {
                    "order": order,
                    "volumes": [
                        {
                            "customerchildnumber": f"{customernumber1}-CH1",
                            "prenum": str(number),
                            "prewidth": "1",
                            "prelength": "1",
                            "preheight": "1",
                            "prerweight": str(forecastweight),
                        }
                    ],
                    "items": [
                        {
                            "skucode": "MOCK-SKU-001",
                            "cnname": "物品",
                            "enname": "item",
                            "hscode": "",
                            "quantity": "1",
                            "quantityunit": "PCS",
                            "price": "1.00",
                            "declarecurrency": DEFAULT_DECLARE_CURRENCY,
                            "weight": "0.1",
                            "origin": "CN",
                            "model": "",
                            "note": "",
                            "material": "",
                            "brand": "",
                            "usage": "",
                        }
                    ],
                }
            ],
            "meta": {"endpoint": "/api/order/createForecast"},
        }

        validation_errors = validate_create_forecast_payload(payload)
        if validation_errors:
            return _err("payload validation failed", validation_errors=validation_errors)

        return _ok(payload=payload)
    except Exception as e:
        return _err("failed to build createForecast payload", reason=str(e))


def create_forecast_order_with_preferences(
    *,
    origin_city: str,
    destination_city: str,
    customernumber1: str,
    consignee_countrycode: str,
    consigneename: str,
    consigneeaddress1: str,
    consigneecity: str,
    consigneezipcode: str,
    consigneeprovince: str,
    insurance_enabled: bool = False,
    insurance_value: float | None = None,
    insurance_type_name: str | None = None,
    insurance_currency_code: str | None = None,
    declare_type_name: str | None = None,
    product_type_name: str | None = None,
    channelid: str = "HK_TNT",
    number: int = 1,
    forecastweight: float = 1.0,
) -> dict:
    """Auto map user-friendly selections to codes and submit a mocked createForecast order.

    - insurance_type_name: matches Insurance.data[].name
    - insurance_currency_code: matches Currency.data[].code
    - declare_type_name: matches DeclareType.data[].name
    - product_type_name: matches ProductType.data[].cnname/enname/productname
    """

    try:
        insurance_options = _api.insurance().get("data", [])
        currency_options = _api.currency().get("data", [])
        declare_options = _api.declaretype().get("data", [])
        product_options = _api.get_product_type().get("data", [])

        declare_selected = _pick_by_name_or_default(
            declare_options, declare_type_name, label="declaretype"
        )
        product_selected = _pick_by_name_or_default(
            product_options, product_type_name, label="producttype"
        )

        isinsurance = 1 if insurance_enabled else 0
        ins_code = None
        cur_code = None

        if isinsurance == 1:
            if insurance_value is None:
                raise ValueError("insurance_value is required when insurance_enabled=True")
            ins_selected = _pick_by_name_or_default(
                insurance_options,
                insurance_type_name,
                label="insurance",
                name_keys=("name",),
            )
            cur_selected = _pick_by_code_or_default(
                currency_options,
                insurance_currency_code,
                label="insurancecurrency",
            )
            ins_code = ins_selected.get("code")
            cur_code = cur_selected.get("code")

        built = build_create_forecast_payload(
            customernumber1=customernumber1,
            consignee_countrycode=consignee_countrycode,
            consigneename=consigneename,
            consigneeaddress1=consigneeaddress1,
            consigneecity=consigneecity,
            consigneezipcode=consigneezipcode,
            consigneeprovince=consigneeprovince,
            channelid=channelid,
            number=number,
            forecastweight=forecastweight,
            isinsurance=isinsurance,
            insurancevalue=insurance_value,
            insurancetypepkid=ins_code,
            insurancecurrency=cur_code,
            declaretypepkid=declare_selected.get("code"),
            producttypepkid=product_selected.get("code"),
        )

        if built.get("status") != "success":
            return built

        request_payload = built["data"]["payload"]

        result = _api.create_forecast_order(
            origin_city=origin_city,
            destination_city=destination_city,
            request_payload=request_payload,
        )

        return _ok(request_payload=request_payload, result=result)
    except Exception as e:
        return _err("failed to create forecast order", reason=str(e))


def submit_forecast_order(order: Any) -> dict:
    """Single-entry wrapper for forecast order creation.

    The input is a structured object (dict) that maps closely to
    create_forecast_order_with_preferences parameters.
    """

    try:
        if isinstance(order, str):
            try:
                decoded: Any = order
                for _ in range(2):
                    if not isinstance(decoded, str):
                        break
                    decoded = json.loads(decoded)
                order = decoded
            except Exception as e:
                return _err("order must be valid JSON", reason=str(e))
        if not isinstance(order, dict):
            return _err("order must be an object or JSON string")

        required_keys = [
            "origin_city",
            "destination_city",
            "customernumber1",
            "consignee_countrycode",
            "consigneename",
            "consigneeaddress1",
            "consigneecity",
            "consigneezipcode",
            "consigneeprovince",
        ]
        missing = [k for k in required_keys if not order.get(k)]
        if missing:
            return _err("missing required fields", missing_fields=missing)

        payload = dict(order)
        payload.setdefault("channelid", DEFAULT_CHANNEL_ID)
        payload.setdefault("forecastweight", 1.0)
        payload.setdefault("number", 1)

        if "insurance_enabled" in payload:
            payload["insurance_enabled"] = _to_bool(payload.get("insurance_enabled"))
        if "insurance_value" in payload and payload.get("insurance_value") is not None:
            payload["insurance_value"] = float(payload["insurance_value"])
        if payload.get("forecastweight") is not None:
            payload["forecastweight"] = float(payload["forecastweight"])
        if payload.get("number") is not None:
            payload["number"] = int(payload["number"])

        return create_forecast_order_with_preferences(**payload)
    except Exception as e:
        return _err("failed to submit forecast order", reason=str(e))


def submit_forecast_order_json(order_json: str) -> dict:
    """Submit forecast order from a JSON string.

    This tool is designed for terminal/chat usage where pasted JSON is often
    not reliably converted into a dict argument by the LLM.
    """

    if isinstance(order_json, str) and _normalize_text(order_json) in {"{}", "{ }"}:
        return _err(
            "order_json is empty",
            hint="Pass the full JSON object string (do not truncate or replace it with {}).",
        )
    return submit_forecast_order(order_json)


def submit_forecast_order_from_text(text: str) -> dict:
    """Submit a forecast order from natural language text.

    This is a terminal-friendly tool that avoids LLM-driven slot-filling loops by
    extracting fields using simple patterns and then calling
    create_forecast_order_with_preferences.
    """

    try:
        if not isinstance(text, str) or text.strip() == "":
            return _err("text is required")

        t = text.strip()

        def _find(patterns: list[str]) -> str | None:
            for p in patterns:
                m = re.search(p, t, flags=re.IGNORECASE | re.MULTILINE)
                if m:
                    return m.group(1).strip()
            return None

        # origin/destination
        origin_city = _find([
            r"从\s*([^\s，,；;\n]+)\s*到\s*([^\s，,；;\n]+)",
        ])
        destination_city = None
        if origin_city:
            # pattern above captures two groups
            m = re.search(r"从\s*([^\s，,；;\n]+)\s*到\s*([^\s，,；;\n]+)", t)
            if m:
                origin_city = m.group(1).strip()
                destination_city = m.group(2).strip()

        customernumber1 = _find([
            r"customernumber1\s*[:：=]\s*([^\s，,；;\n]+)",
            r"客户参考号\s*[:：]\s*([^\s，,；;\n]+)",
        ])

        consignee_countrycode = _find([
            r"收件国家\s*[:：]\s*([A-Za-z]{2,3})",
            r"country\s*[:：=]\s*([A-Za-z]{2,3})",
        ])
        if consignee_countrycode:
            consignee_countrycode = consignee_countrycode.upper()

        consigneename = _find([
            r"收件人\s*[:：]\s*([^\n，,；;]+)",
            r"consigneename\s*[:：=]\s*([^\n，,；;]+)",
        ])
        consigneeaddress1 = _find([
            r"收件地址\s*[:：]\s*([^\n，,；;]+)",
            r"地址\s*[:：]\s*([^\n，,；;]+)",
            r"consigneeaddress1\s*[:：=]\s*([^\n，,；;]+)",
        ])
        consigneecity = _find([
            r"城市\s*[:：]\s*([^\n，,；;]+)",
            r"consigneecity\s*[:：=]\s*([^\n，,；;]+)",
        ])
        consigneezipcode = _find([
            r"邮编\s*[:：]\s*([^\s，,；;\n]+)",
            r"ZIP\s*[:：=]\s*([^\s，,；;\n]+)",
            r"consigneezipcode\s*[:：=]\s*([^\s，,；;\n]+)",
        ])
        consigneeprovince = _find([
            r"省州\s*[:：]\s*([^\s，,；;\n]+)",
            r"州\s*[:：]\s*([^\s，,；;\n]+)",
            r"consigneeprovince\s*[:：=]\s*([^\s，,；;\n]+)",
        ])

        insurance_enabled = _to_bool(
            _find([r"投保\s*[:：]\s*([^\s，,；;\n]+)", r"insurance\s*[:：=]\s*(.+)"]) or ""
        )
        insurance_value = None
        insurance_value_raw = _find([
            r"保额\s*[:：]\s*([0-9]+(?:\.[0-9]+)?)",
            r"insurance_value\s*[:：=]\s*([0-9]+(?:\.[0-9]+)?)",
        ])
        if insurance_value_raw is not None:
            try:
                insurance_value = float(insurance_value_raw)
            except Exception:
                insurance_value = None

        insurance_type_name = _find([
            r"险种\s*[:：]\s*([^\n，,；;]+)",
            r"insurance_type_name\s*[:：=]\s*([^\n，,；;]+)",
        ])
        insurance_currency_code = _find([
            r"币别\s*[:：]\s*([A-Za-z]{3})",
            r"insurance_currency_code\s*[:：=]\s*([A-Za-z]{3})",
        ])
        if insurance_currency_code:
            insurance_currency_code = insurance_currency_code.upper()

        product_type_name = _find([
            r"物品类别\s*[:：]\s*([^\n，,；;]+)",
            r"product_type_name\s*[:：=]\s*([^\n，,；;]+)",
        ])
        declare_type_name = _find([
            r"报关类型\s*[:：]\s*([^\n，,；;]+)",
            r"declare_type_name\s*[:：=]\s*([^\n，,；;]+)",
        ])

        # optional overrides
        channelid = _find([r"channelid\s*[:：=]\s*([^\s，,；;\n]+)"]) or DEFAULT_CHANNEL_ID
        forecastweight_raw = _find([r"forecastweight\s*[:：=]\s*([0-9]+(?:\.[0-9]+)?)", r"预报重量\s*[:：]\s*([0-9]+(?:\.[0-9]+)?)"])
        number_raw = _find([r"number\s*[:：=]\s*([0-9]+)", r"件数\s*[:：]\s*([0-9]+)"])

        missing = []
        if not origin_city:
            missing.append("origin_city")
        if not destination_city:
            missing.append("destination_city")
        if not customernumber1:
            missing.append("customernumber1")
        if not consignee_countrycode:
            missing.append("consignee_countrycode")
        if not consigneename:
            missing.append("consigneename")
        if not consigneeaddress1:
            missing.append("consigneeaddress1")
        if not consigneecity:
            missing.append("consigneecity")
        if not consigneezipcode:
            missing.append("consigneezipcode")
        if not consigneeprovince:
            missing.append("consigneeprovince")

        if missing:
            return _err(
                "missing required fields from text",
                missing_fields=missing,
                received_excerpt=t[:500],
            )

        forecastweight = 1.0
        if forecastweight_raw:
            forecastweight = float(forecastweight_raw)
        number = 1
        if number_raw:
            number = int(number_raw)

        return create_forecast_order_with_preferences(
            origin_city=origin_city,
            destination_city=destination_city,
            customernumber1=customernumber1,
            consignee_countrycode=consignee_countrycode,
            consigneename=consigneename,
            consigneeaddress1=consigneeaddress1,
            consigneecity=consigneecity,
            consigneezipcode=consigneezipcode,
            consigneeprovince=consigneeprovince,
            insurance_enabled=insurance_enabled,
            insurance_value=insurance_value,
            insurance_type_name=insurance_type_name,
            insurance_currency_code=insurance_currency_code,
            declare_type_name=declare_type_name,
            product_type_name=product_type_name,
            channelid=channelid,
            number=number,
            forecastweight=forecastweight,
        )
    except Exception as e:
        return _err("failed to submit forecast order from text", reason=str(e))


def query_order_status(order_no: str) -> dict:
    """查询物流状态（按文档 Track 接口结构 mock 返回）。"""
    normalized = order_no.strip()
    if normalized.startswith("#"):
        normalized = normalized[1:]
    return _tool_call(_api.track, tool_name="query_order_status", waybillnumber=normalized)


def create_shipment(origin: str, destination: str) -> dict:
    """创建新货运单（按文档 Create Order 接口结构 mock 返回）。"""
    return _tool_call(
        _api.create_forecast_order,
        tool_name="create_shipment",
        origin_city=origin,
        destination_city=destination,
    )


root_agent = Agent(
    name="logistics_agent",
    model="gemini-2.0-flash",
    description="An agent that can query logistics tracking and create shipments via a mocked logistics API.",
    instruction=(
        "You are a logistics assistant. "
        "Before creating an order, you can fetch lookup values using get_insurance_types, get_currencies, get_declare_types, get_customs_types, get_terms_of_sale, get_export_reasons, and get_product_types. "
        "You can also build a complete createForecast payload using build_create_forecast_payload. "
        "All tools return a unified structure: {status, data, error}. The original mocked API response, if any, is available under data.raw. "
        "When creating an order, if the user does not specify channelid/forecastweight/number, use defaults (channelid=HK_TNT, forecastweight=1.0, number=1) and proceed; only ask for missing fields that are truly required (consignee fields and customernumber1). "
        "For order creation, prefer submit_forecast_order_json when the user provides JSON; it is the most reliable way to pass structured input. "
        "When calling submit_forecast_order_json, you MUST pass the user's JSON VERBATIM as the order_json argument (do not rewrite, truncate, or replace it with {}). "
        "When the user provides natural language order details, prefer submit_forecast_order_from_text and you MUST pass the user's message VERBATIM as the text argument (do not summarize, translate, truncate, or drop lines). "
        "Never claim an order was created unless an order-creation tool returned status=success. "
        "Do not call order-creation tools more than once per user request unless the user explicitly asks to retry. "
        "If the user asks for raw JSON or says 'do not summarize', output ONLY the tool JSON as-is (no extra text, no markdown fences, no additional keys), including when status=error. "
        "Use query_order_status to query tracking/status for an order number. "
        "Use create_shipment to create a new shipment. "
        "Return the tool output as-is."
    ),
    tools=[
        get_insurance_types,
        get_currencies,
        get_declare_types,
        get_customs_types,
        get_terms_of_sale,
        get_export_reasons,
        get_product_types,
        build_create_forecast_payload,
        create_forecast_order_with_preferences,
        submit_forecast_order,
        submit_forecast_order_json,
        submit_forecast_order_from_text,
        query_order_status,
        create_shipment,
    ],
)
