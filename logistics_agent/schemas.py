from typing import Any, Dict, List, Literal, TypedDict


class Authorization(TypedDict):
    code: str
    token: str


class Order(TypedDict, total=False):
    channelid: str
    customernumber1: str
    customernumber2: str
    number: int
    isbattery: str
    isinsurance: str
    forecastweight: str
    packagetypecode: str
    goodstypecode: str
    countrycode: str
    consigneename: str
    consigneecorpname: str
    consigneeaddress1: str
    consigneeaddress2: str
    consigneeaddress3: str
    consigneecity: str
    consigneezipcode: str
    consigneeprovince: str
    consigneetel: str
    consigneemobile: str
    consigneehousenumber: str
    consigneetaxnumber: str
    consigneeemail: str
    declaretypepkid: int
    producttypepkid: int
    insurancevalue: str
    insurancetypepkid: int
    insurancecurrency: str


class Volume(TypedDict, total=False):
    customerchildnumber: str
    prenum: str
    prewidth: str
    prelength: str
    preheight: str
    prerweight: str


class Item(TypedDict, total=False):
    skucode: str
    cnname: str
    enname: str
    hscode: str
    quantity: str
    quantityunit: str
    price: str
    declarecurrency: str
    weight: str
    origin: str
    model: str
    note: str
    material: str
    brand: str
    usage: str


class CreateForecastData(TypedDict):
    order: Order
    volumes: List[Volume]
    items: List[Item]


class CreateForecastPayload(TypedDict):
    authorization: Authorization
    datas: List[CreateForecastData]


class ToolResult(TypedDict, total=False):
    status: Literal["success", "error"]
    data: Dict[str, Any]
    error: Dict[str, Any]


def validate_create_forecast_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []

    if not isinstance(payload, dict):
        return ["payload must be a dict"]

    auth = payload.get("authorization")
    if not isinstance(auth, dict):
        errors.append("authorization must be an object")
    else:
        if not auth.get("code"):
            errors.append("authorization.code is required")
        if not auth.get("token"):
            errors.append("authorization.token is required")

    datas = payload.get("datas")
    if not isinstance(datas, list) or not datas:
        errors.append("datas must be a non-empty array")
        return errors

    first = datas[0]
    if not isinstance(first, dict):
        errors.append("datas[0] must be an object")
        return errors

    order = first.get("order")
    if not isinstance(order, dict):
        errors.append("datas[0].order must be an object")
        return errors

    required_order_fields = [
        "channelid",
        "customernumber1",
        "number",
        "forecastweight",
        "countrycode",
        "consigneename",
        "consigneeaddress1",
        "consigneecity",
        "consigneezipcode",
        "consigneeprovince",
    ]
    for f in required_order_fields:
        if order.get(f) in (None, ""):
            errors.append(f"datas[0].order.{f} is required")

    volumes = first.get("volumes")
    if not isinstance(volumes, list) or not volumes:
        errors.append("datas[0].volumes must be a non-empty array")

    items = first.get("items")
    if not isinstance(items, list) or not items:
        errors.append("datas[0].items must be a non-empty array")

    return errors
