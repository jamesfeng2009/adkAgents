import json
import hashlib
import logging
import re
from typing import Any

from google.adk.agents import Agent

from .mock_logistics_api import MockLogisticsApi
from .schemas import validate_create_forecast_payload


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


logging.getLogger().info("logistics_agent.agent loaded from %s", __file__)


_api = MockLogisticsApi()


_IDEMPOTENT_CACHE: dict[str, dict] = {}


_ORDER_DRAFT: dict[str, Any] = {}


_LAST_ORDER: dict[str, Any] = {}


DEFAULT_CHANNEL_ID = "HK_TNT"
DEFAULT_PACKAGE_TYPE_CODE = "O"
DEFAULT_GOODS_TYPE_CODE = "WPX"
DEFAULT_DECLARE_CURRENCY = "USD"


def _tool_call(func, *, tool_name: str, **kwargs) -> dict:
    try:
        logging.getLogger().info("TOOL_CALL %s kwargs=%s", tool_name, kwargs)
        result = func(**kwargs)
        logging.getLogger().info("TOOL_RESULT %s type=%s", tool_name, type(result).__name__)
        return _ok(raw=result)
    except Exception as e:
        logging.getLogger().exception("TOOL_ERROR %s", tool_name)
        return _err(f"failed to call tool {tool_name}", reason=str(e))


def _ok(**data) -> dict:
    return {"status": "success", "data": data, "error": None}


def _err(message: str, **details) -> dict:
    return {"status": "error", "data": None, "error": {"message": message, **details}}


def _normalize_text(s: str) -> str:
    return " ".join(s.strip().lower().split())


def _normalize_currency_code(s: str | None) -> str | None:
    if s is None:
        return None
    t = s.strip()
    if t == "":
        return None
    norm = _normalize_text(t)
    # Common Chinese names
    if norm in {"美元"}:
        return "USD"
    if norm in {"人民币", "人名币", "rmb"}:
        return "CNY"
    if norm in {"港币", "港元"}:
        return "HKG"
    # Common ISO codes
    if norm in {"usd", "cny", "hkg"}:
        return norm.upper()
    return t.upper() if re.fullmatch(r"[A-Za-z]{3}", t) else t


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


def _save_last_order_from_response(resp: dict) -> None:
    """Best-effort capture of the last successful order identifiers."""

    try:
        if not isinstance(resp, dict) or resp.get("status") != "success":
            return

        data = resp.get("data")
        if not isinstance(data, dict):
            return

        last: dict[str, Any] = {}

        # create_forecast_order_with_preferences path
        result = data.get("result")
        if isinstance(result, dict):
            api_data = result.get("data")
            if isinstance(api_data, list) and api_data:
                first = api_data[0]
                if isinstance(first, dict):
                    for k in ("systemnumber", "waybillnumber", "customernumber", "msg", "code"):
                        if first.get(k) is not None:
                            last[k] = first.get(k)

        # other mock/compat outputs
        raw = data.get("raw")
        if isinstance(raw, dict):
            for k in ("orderNo", "message"):
                if raw.get(k) is not None:
                    last[k] = raw.get(k)

        # store request id if present
        if data.get("request_id") is not None:
            last["request_id"] = data.get("request_id")

        if last:
            _LAST_ORDER.clear()
            _LAST_ORDER.update(last)
    except Exception:
        # Never block main flow due to bookkeeping
        return


def _extract_order_identifiers_from_result(result: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not isinstance(result, dict):
        return out
    data = result.get("data")
    if not isinstance(data, list) or not data:
        return out
    first = data[0]
    if not isinstance(first, dict):
        return out

    systemnumber = first.get("systemnumber")
    waybillnumber = first.get("waybillnumber")
    if systemnumber is not None:
        out["order_id"] = systemnumber
    if waybillnumber is not None:
        out["tracking_id"] = waybillnumber

    childs = first.get("childs")
    if isinstance(childs, list) and childs:
        tracknumbers: list[str] = []
        for c in childs:
            if not isinstance(c, dict):
                continue
            tn = c.get("tracknumber")
            if isinstance(tn, str) and tn.strip():
                tracknumbers.append(tn.strip())
        if tracknumbers:
            out["child_tracking_ids"] = tracknumbers
    return out


def _extract_partial_order_fields(text: str) -> dict[str, Any]:
    t = text.strip()

    def _find(patterns: list[str]) -> str | None:
        for p in patterns:
            m = re.search(p, t, flags=re.IGNORECASE | re.MULTILINE)
            if m:
                return m.group(1).strip()
        return None

    out: dict[str, Any] = {}

    m = re.search(r"从\s*([^\s，,；;\n]+)\s*到\s*([^\s，,；;\n]+)", t)
    if m:
        out["origin_city"] = m.group(1).strip()
        out["destination_city"] = m.group(2).strip()

    customernumber1 = _find([
        r"customernumber1\s*[:：=]\s*([^\s，,；;\n]+)",
        r"客户参考号\s*[:：]\s*([^\s，,；;\n]+)",
    ])
    if customernumber1:
        out["customernumber1"] = customernumber1

    consignee_countrycode = _find([
        r"收件国家\s*[:：=]\s*([A-Za-z]{2,3})",
        r"consignee_countrycode\s*[:：=]\s*([A-Za-z]{2,3})",
        r"country\s*[:：=]\s*([A-Za-z]{2,3})",
    ])
    if consignee_countrycode:
        out["consignee_countrycode"] = consignee_countrycode.upper()

    consigneename = _find([
        r"收件人\s*[:：=]\s*([^\n，,；;]+)",
        r"consigneename\s*[:：=]\s*([^\n，,；;]+)",
    ])
    if consigneename:
        out["consigneename"] = consigneename

    consigneeaddress1 = _find([
        r"收件地址\s*[:：=]\s*([^\n，,；;]+)",
        r"地址\s*[:：=]\s*([^\n，,；;]+)",
        r"consigneeaddress1\s*[:：=]\s*([^\n，,；;]+)",
    ])
    if consigneeaddress1:
        out["consigneeaddress1"] = consigneeaddress1

    consigneecity = _find([
        r"城市\s*[:：=]\s*([^\n，,；;]+)",
        r"consigneecity\s*[:：=]\s*([^\n，,；;]+)",
    ])
    if consigneecity:
        out["consigneecity"] = consigneecity

    consigneezipcode = _find([
        r"邮编\s*[:：=]\s*([^\s，,；;\n]+)",
        r"ZIP\s*[:：=]\s*([^\s，,；;\n]+)",
        r"consigneezipcode\s*[:：=]\s*([^\s，,；;\n]+)",
    ])
    if consigneezipcode:
        out["consigneezipcode"] = consigneezipcode

    consigneeprovince = _find([
        r"省州\s*[:：=]\s*([^\s，,；;\n]+)",
        r"州\s*[:：=]\s*([^\s，,；;\n]+)",
        r"consigneeprovince\s*[:：=]\s*([^\s，,；;\n]+)",
    ])
    if consigneeprovince:
        out["consigneeprovince"] = consigneeprovince

    channelid = _find([r"channelid\s*[:：=]\s*([^\s，,；;\n]+)"])
    if channelid:
        out["channelid"] = channelid

    forecastweight_raw = _find([
        r"forecastweight\s*[:：=]\s*([0-9]+(?:\.[0-9]+)?)",
        r"预报重量\s*[:：=]\s*([0-9]+(?:\.[0-9]+)?)",
    ])
    if forecastweight_raw:
        out["forecastweight"] = float(forecastweight_raw)

    number_raw = _find([r"number\s*[:：=]\s*([0-9]+)", r"件数\s*[:：=]\s*([0-9]+)"])
    if number_raw:
        out["number"] = int(number_raw)

    insurance_enabled_raw = _find([r"投保\s*[:：=]\s*([^\s，,；;\n]+)"])
    if insurance_enabled_raw is not None:
        out["insurance_enabled"] = _to_bool(insurance_enabled_raw)

    insurance_value_raw = _find([
        r"保额\s*[:：=]\s*([0-9]+(?:\.[0-9]+)?)",
        r"insurance_value\s*[:：=]\s*([0-9]+(?:\.[0-9]+)?)",
    ])
    if insurance_value_raw:
        out["insurance_value"] = float(insurance_value_raw)

    insurance_type_name = _find([
        r"险种\s*[:：=]\s*([^\n，,；;]+)",
        r"insurance_type_name\s*[:：=]\s*([^\n，,；;]+)",
    ])
    if insurance_type_name:
        out["insurance_type_name"] = insurance_type_name

    insurance_currency_code = _find([
        r"币别\s*[:：=]\s*([A-Za-z]{3})",
        r"insurance_currency_code\s*[:：=]\s*([A-Za-z]{3})",
    ])
    if insurance_currency_code:
        out["insurance_currency_code"] = _normalize_currency_code(insurance_currency_code)
    else:
        # Accept Chinese names for currency as well (e.g. 币别=美元/人民币/港币)
        insurance_currency_cn = _find([
            r"币别\s*[:：=]\s*([^\n，,；;]+)",
        ])
        if insurance_currency_cn:
            out["insurance_currency_code"] = _normalize_currency_code(insurance_currency_cn)

    product_type_name = _find([
        r"物品类别\s*[:：=]\s*([^\n，,；;]+)",
        r"product_type_name\s*[:：=]\s*([^\n，,；;]+)",
    ])
    if product_type_name:
        out["product_type_name"] = product_type_name

    declare_type_name = _find([
        r"报关类型\s*[:：=]\s*([^\n，,；;]+)",
        r"declare_type_name\s*[:：=]\s*([^\n，,；;]+)",
    ])
    if declare_type_name:
        canon = declare_type_name.strip()
        canon_norm = _normalize_text(canon)
        # Map common natural-language phrases to canonical dictionary names.
        if "不需要报关" in canon_norm or canon_norm in {"不需报关", "无需报关", "免报关"}:
            canon = "不需报关"
        elif "需要报关" in canon_norm or "要报关" in canon_norm or "报关" == canon_norm:
            # Default to a common customs mode when user only says they need customs.
            canon = "买单报关"
        out["declare_type_name"] = canon

    return out


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


def get_waybillnumbers(customernumber: Any) -> dict:
    """Get waybillnumber by customernumber list.

    Accepts either:
    - a Python list of strings
    - or a JSON string like: {"customernumber": ["T...", ...]}
    - or a JSON array string like: ["T...", ...]
    """

    try:
        nums: list[str] | None = None
        if isinstance(customernumber, list):
            nums = [str(x) for x in customernumber if str(x).strip()]
        elif isinstance(customernumber, str):
            s = customernumber.strip()
            if s:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    nums = [str(x) for x in parsed if str(x).strip()]
                elif isinstance(parsed, dict):
                    cn = parsed.get("customernumber")
                    if isinstance(cn, list):
                        nums = [str(x) for x in cn if str(x).strip()]
        if not nums:
            return _err(
                "customernumber is required",
                hint='Pass a list like ["T620200611-1001"] or JSON like {"customernumber":["T..."]}',
            )

        return _tool_call(_api.waybillnumber, tool_name="get_waybillnumbers", customernumber=nums)
    except Exception as e:
        return _err("failed to get waybillnumbers", reason=str(e))


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
            cur_input = _normalize_currency_code(insurance_currency_code)
            try:
                cur_selected = _pick_by_code_or_default(
                    currency_options,
                    cur_input,
                    label="insurancecurrency",
                )
            except Exception:
                # Allow matching by Chinese/English name for convenience
                cur_selected = _pick_by_name_or_default(
                    currency_options,
                    insurance_currency_code,
                    label="insurancecurrency",
                    name_keys=("cnname", "enname", "code"),
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

        extras = _extract_order_identifiers_from_result(result)
        resp = _ok(request_payload=request_payload, result=result, **extras)
        _save_last_order_from_response(resp)
        return resp
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

        resp = create_forecast_order_with_preferences(**payload)
        _save_last_order_from_response(resp)
        return resp
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
    resp = submit_forecast_order(order_json)
    _save_last_order_from_response(resp)
    return resp


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
        extracted = _extract_partial_order_fields(t)
        origin_city = extracted.get("origin_city")
        destination_city = extracted.get("destination_city")
        customernumber1 = extracted.get("customernumber1")
        consignee_countrycode = extracted.get("consignee_countrycode")
        consigneename = extracted.get("consigneename")
        consigneeaddress1 = extracted.get("consigneeaddress1")
        consigneecity = extracted.get("consigneecity")
        consigneezipcode = extracted.get("consigneezipcode")
        consigneeprovince = extracted.get("consigneeprovince")
        channelid = extracted.get("channelid") or DEFAULT_CHANNEL_ID
        forecastweight = float(extracted.get("forecastweight") or 1.0)
        number = int(extracted.get("number") or 1)
        insurance_enabled = bool(extracted.get("insurance_enabled") or False)
        insurance_value = extracted.get("insurance_value")
        insurance_type_name = extracted.get("insurance_type_name")
        insurance_currency_code = extracted.get("insurance_currency_code")
        product_type_name = extracted.get("product_type_name")
        declare_type_name = extracted.get("declare_type_name")

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

        canonical = {
            "origin_city": origin_city,
            "destination_city": destination_city,
            "customernumber1": customernumber1,
            "consignee_countrycode": consignee_countrycode,
            "consigneename": consigneename,
            "consigneeaddress1": consigneeaddress1,
            "consigneecity": consigneecity,
            "consigneezipcode": consigneezipcode,
            "consigneeprovince": consigneeprovince,
            "insurance_enabled": insurance_enabled,
            "insurance_value": insurance_value,
            "insurance_type_name": insurance_type_name,
            "insurance_currency_code": insurance_currency_code,
            "product_type_name": product_type_name,
            "declare_type_name": declare_type_name,
            "channelid": channelid,
            "forecastweight": forecastweight,
            "number": number,
        }
        request_id = hashlib.sha256(
            json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]

        cached = _IDEMPOTENT_CACHE.get(request_id)
        if cached is not None:
            # Return the first successful result without re-submitting.
            cached2 = json.loads(json.dumps(cached, ensure_ascii=False))
            if isinstance(cached2, dict) and isinstance(cached2.get("data"), dict):
                cached2["data"]["request_id"] = request_id
                cached2["data"]["idempotent_replay"] = True
            return cached2

        resp = create_forecast_order_with_preferences(
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
        if isinstance(resp, dict) and resp.get("status") == "success" and isinstance(resp.get("data"), dict):
            resp["data"]["request_id"] = request_id
            resp["data"]["idempotent_replay"] = False
            _IDEMPOTENT_CACHE[request_id] = resp
            _save_last_order_from_response(resp)
        return resp
    except Exception as e:
        return _err("failed to submit forecast order from text", reason=str(e))


def update_forecast_order_draft(text: str, *, reset: bool = False, auto_submit: bool = False) -> dict:
    try:
        if reset:
            _ORDER_DRAFT.clear()

        if not isinstance(text, str) or text.strip() == "":
            return _err("text is required")

        extracted = _extract_partial_order_fields(text)
        for k, v in extracted.items():
            if v is None:
                continue
            _ORDER_DRAFT[k] = v

        draft = dict(_ORDER_DRAFT)
        draft.setdefault("channelid", DEFAULT_CHANNEL_ID)
        draft.setdefault("forecastweight", 1.0)
        draft.setdefault("number", 1)

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
        missing = [k for k in required_keys if not draft.get(k)]
        if missing:
            return _ok(draft=draft, missing_fields=missing, ready=False)

        if auto_submit:
            resp = submit_forecast_order(draft)
            if resp.get("status") == "success":
                _ORDER_DRAFT.clear()
            return resp

        return _ok(draft=draft, missing_fields=[], ready=True)
    except Exception as e:
        return _err("failed to update forecast order draft", reason=str(e))


def submit_forecast_order_draft() -> dict:
    try:
        if not _ORDER_DRAFT:
            if _LAST_ORDER:
                return _ok(last_order=_LAST_ORDER, hint="No active draft. Use query_last_order_status to query the most recent order.")
            return _err("no active draft", hint="Call update_forecast_order_draft first")
        draft = dict(_ORDER_DRAFT)
        draft.setdefault("channelid", DEFAULT_CHANNEL_ID)
        draft.setdefault("forecastweight", 1.0)
        draft.setdefault("number", 1)

        resp = submit_forecast_order(draft)
        if resp.get("status") == "success":
            _ORDER_DRAFT.clear()
            _save_last_order_from_response(resp)
        return resp
    except Exception as e:
        return _err("failed to submit forecast order draft", reason=str(e))


def get_last_order_reference() -> dict:
    if not _LAST_ORDER:
        return _err("no last order", hint="Create an order first")
    return _ok(last_order=_LAST_ORDER)


def query_last_order_status() -> dict:
    """Query tracking/status for the most recent order when user doesn't have an order number."""

    if not _LAST_ORDER:
        return _err("no last order", hint="Create an order first")
    waybill = _LAST_ORDER.get("waybillnumber")
    if not waybill:
        return _err("last order has no waybillnumber", last_order=_LAST_ORDER)
    return query_order_status(str(waybill))


def debug_runtime_info() -> dict:
    try:
        logging.getLogger().info("TOOL_CALL debug_runtime_info")
        return _ok(
            agent_file=__file__,
            mock_api_file=getattr(_api.__class__, "__module__", None),
            insurance_raw=_api.insurance(),
        )
    except Exception as e:
        logging.getLogger().exception("TOOL_ERROR debug_runtime_info")
        return _err("failed to collect runtime info", reason=str(e))


def query_order_status(order_no: str) -> dict:
    """查询物流状态（按文档 Track 接口结构 mock 返回）。"""
    normalized = order_no.strip()
    if normalized.startswith("#"):
        normalized = normalized[1:]
    # The mocked track API expects a waybillnumber.
    # Users may paste a systemnumber (e.g. SYSxxxx). If it matches the last order,
    # map it to the last waybillnumber for convenience.
    if normalized.startswith("SYS") and _LAST_ORDER:
        last_system = _LAST_ORDER.get("systemnumber")
        last_waybill = _LAST_ORDER.get("waybillnumber")
        if last_system and str(last_system) == normalized and last_waybill:
            normalized = str(last_waybill)

    resp = _tool_call(_api.track, tool_name="query_order_status", waybillnumber=normalized)
    try:
        raw = resp.get("data", {}).get("raw") if isinstance(resp, dict) else None
        if isinstance(raw, dict):
            data = raw.get("data")
            if isinstance(data, list) and data:
                first = data[0]
                if isinstance(first, dict) and first.get("errormsg"):
                    return _err(
                        "invalid order number",
                        input=order_no,
                        hint="track expects waybillnumber; if you only have systemnumber, call get_last_order_reference or query_last_order_status",
                        raw=raw,
                    )
    except Exception:
        pass
    return resp


def create_shipment(origin: str, destination: str) -> dict:
    """创建新货运单（按文档 Create Order 接口结构 mock 返回）。"""
    result = _api.create_forecast_order(
        origin_city=origin,
        destination_city=destination,
    )
    
    # 提取订单标识符，保持与其他函数一致的格式
    extras = _extract_order_identifiers_from_result(result)
    resp = _ok(raw=result, **extras)
    _save_last_order_from_response(resp)
    return resp


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
        "If the user explicitly asks to call a specific tool (e.g. contains '请调用 <tool_name>' or 'call <tool_name>'), you MUST call that exact tool once. "
        "When returning tool output, output the returned dict as plain JSON text ONLY (no prose, no markdown, no ```json fences, no extra wrapper keys). "
        "For step-by-step input, use update_forecast_order_draft to accumulate fields and ask for missing_fields from its JSON result; when ready, call submit_forecast_order_draft (or update_forecast_order_draft with auto_submit=true). "
        "If the user doesn't have an order number, use get_last_order_reference to fetch the latest identifiers, or query_last_order_status to query tracking for the latest order. "
        "If waybillnumber is empty in the createForecast result, call get_waybillnumbers with customernumber to retrieve waybillnumber. "
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
        get_waybillnumbers,
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
        update_forecast_order_draft,
        submit_forecast_order_draft,
        get_last_order_reference,
        query_last_order_status,
        debug_runtime_info,
        query_order_status,
        create_shipment,
    ],
)
