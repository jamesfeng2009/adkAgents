import datetime
import hashlib
from typing import Any, Dict


def _stable_id(*parts: str) -> str:
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _now_str() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class MockLogisticsApi:
    def __init__(self, customer_code: str = "KJHB", token: str = "mock-token"):
        self.customer_code = customer_code
        self.token = token

    def insurance(self) -> Dict[str, Any]:
        return {
            "code": 0,
            "msg": "调用成功",
            "data": [
                {"code": 1, "name": "货物运输险", "note": "保障运输"},
                {"code": 2, "name": "意外险", "note": "意外损坏，丢失等"},
            ],
        }

    def currency(self) -> Dict[str, Any]:
        return {
            "code": 0,
            "msg": "调用成功",
            "data": [
                {"code": "CNY", "cnname": "人民币", "enname": "CNY"},
                {"code": "HKG", "cnname": "港币", "enname": "HKG"},
                {"code": "USD", "cnname": "美元", "enname": "USD"},
            ],
        }

    def declaretype(self) -> Dict[str, Any]:
        return {
            "code": 0,
            "msg": "调用成功",
            "data": [
                {"code": 1, "name": "不需报关", "note": "不需要进行报关"},
                {"code": 2, "name": "买单报关", "note": ""},
                {"code": 3, "name": "贸易报关", "note": ""},
            ],
        }

    def customstype(self) -> Dict[str, Any]:
        return {
            "code": 0,
            "msg": "调用成功",
            "data": [
                {"code": 1, "name": "包税", "note": "包税"},
                {"code": 2, "name": "不包税", "note": ""},
                {"code": 3, "name": "合并清关", "note": ""},
            ],
        }

    def termsofsalecode(self) -> Dict[str, Any]:
        return {
            "msg": "调用成功",
            "code": 0,
            "data": [
                {"code": "GIF", "name": "GIF"},
                {"code": "FCA", "name": "Free Carrier"},
                {"code": "CFR", "name": "Cost and Freight"},
                {"code": "CIF", "name": "Cost Insurance and Freight"},
                {"code": "EXW", "name": "Ex Works"},
                {"code": "CIP", "name": "Carriage and Insurance Paid"},
                {"code": "CPT", "name": "Carriage Paid To"},
                {"code": "DAF", "name": "Delivered at Frontier"},
                {"code": "DDP", "name": "Delivery Duty Paid"},
                {"code": "DDU", "name": "Delivery Duty Unpaid"},
                {"code": "DEQ", "name": "Delivered Ex Quay"},
                {"code": "DES", "name": "Delivered Ex Ship"},
                {"code": "FAS", "name": "Free Alongside Ship"},
                {"code": "FOB", "name": "Free On Board"},
                {"code": "DAP", "name": "Delivered At Place"},
                {"code": "DAT", "name": "Delivered At Terminal"},
            ],
        }

    def exportreasoncode(self) -> Dict[str, Any]:
        return {
            "msg": "调用成功",
            "code": 0,
            "data": [
                {"code": "sample", "name": "sample"},
                {"code": "sale", "name": "sale"},
            ],
        }

    def get_product_type(self) -> Dict[str, Any]:
        return {
            "msg": "success",
            "code": 0,
            "data": [
                {
                    "code": 1,
                    "cnname": "普货",
                    "batteryflag": 0,
                    "productname": "普货",
                    "isinputbattery": 0,
                    "batterydesc": "",
                    "enname": "General goods",
                },
                {
                    "code": 2,
                    "cnname": "内置电池产品",
                    "batteryflag": 1,
                    "productname": "手机,电子表,笔记本",
                    "isinputbattery": 1,
                    "batterydesc": "有内置电池",
                    "enname": "electrify",
                },
            ],
        }

    def create_order(self, *, origin_city: str, destination_city: str) -> Dict[str, Any]:
        systemnumber = f"SYS{_stable_id(origin_city, destination_city)}"
        waybillnumber = f"EV{_stable_id(systemnumber).upper()}CN"
        customernumber = f"MOCK-{_stable_id(waybillnumber)}"

        return {
            "code": 0,
            "msg": "调用成功",
            "data": [
                {
                    "code": 0,
                    "msg": "下单成功",
                    "customernumber": customernumber,
                    "systemnumber": systemnumber,
                    "waybillnumber": waybillnumber,
                    "isRemote": False,
                    "childs": [
                        {
                            "customernumber": f"{customernumber}-1",
                            "systemnumber": f"{systemnumber}-1",
                            "tracknumber": f"1Z{_stable_id(waybillnumber, '1').upper()}",
                        }
                    ],
                    "meta": {
                        "origin_city": origin_city,
                        "destination_city": destination_city,
                        "created_at": _now_str(),
                        "endpoint": "/api/order/create",
                    },
                }
            ],
        }

    def create_forecast_order(
        self,
        *,
        origin_city: str,
        destination_city: str,
        request_payload: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        payload = self.create_order(origin_city=origin_city, destination_city=destination_city)
        payload["data"][0]["meta"]["endpoint"] = "/api/order/createForecast"
        if request_payload is not None:
            payload["data"][0]["meta"]["request_payload"] = request_payload
        return payload

    def track(self, *, waybillnumber: str) -> Dict[str, Any]:
        if not waybillnumber or waybillnumber.strip() == "":
            return {"msg": "success", "code": 0, "data": []}

        if waybillnumber in {"12345", "#12345"}:
            systemnumber = f"SYS{_stable_id('12345')}"
            tracknumber = f"1Z{_stable_id('12345', 'track').upper()}"

            return {
                "msg": "success",
                "code": 0,
                "data": [
                    {
                        "searchNumber": "12345",
                        "systemnumber": systemnumber,
                        "waybillnumber": "12345",
                        "tracknumber": tracknumber,
                        "countrycode": "US",
                        "orderstatus": "InTransit",
                        "orderstatusName": "运输中",
                        "trackItems": [
                            {
                                "location": "Shenzhen, CN",
                                "trackdate_utc8": "2025-12-10 10:00:00",
                                "trackdate": "2025-12-10 10:00:00",
                                "info": "已揽收",
                                "responsecode": "OT001",
                            },
                            {
                                "location": "Hong Kong, CN",
                                "trackdate_utc8": "2025-12-11 01:20:00",
                                "trackdate": "2025-12-11 01:20:00",
                                "info": "离港",
                                "responsecode": "OT001",
                            },
                            {
                                "location": "Los Angeles, CA, US",
                                "trackdate_utc8": "2025-12-12 09:15:00",
                                "trackdate": "2025-12-12 09:15:00",
                                "info": "抵达目的地分拨中心",
                                "responsecode": "OT001",
                            },
                        ],
                        "subOrderList": [],
                        "subOrderTrackItems": {},
                    }
                ],
            }

        return {
            "msg": "success",
            "code": 0,
            "data": [
                {
                    "waybillnumber": waybillnumber,
                    "searchNumber": waybillnumber,
                    "errormsg": "无效的单号",
                }
            ],
        }
