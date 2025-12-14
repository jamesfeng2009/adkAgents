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
        self._orders_by_customernumber: dict[str, dict[str, Any]] = {}

    def insurance(self) -> Dict[str, Any]:
        return {
            "code": 0,
            "msg": "调用成功",
            "data": [
                {"code": 1, "name": "货物运输险", "note": "保障运输"},
                {"code": 2, "name": "意外险", "note": "意外损坏，丢失等"},
                {"code": 3, "name": "综合险", "note": "运输过程中多风险保障"},
                {"code": 4, "name": "破损险", "note": "外包装/内件破损保障"},
                {"code": 5, "name": "丢失险", "note": "包裹丢失保障"},
                {"code": 6, "name": "延误险", "note": "运输延误补偿"},
                {"code": 7, "name": "盗抢险", "note": "盗窃抢劫风险保障"},
                {"code": 8, "name": "温控险", "note": "冷链/恒温运输风险保障"},
                {"code": 9, "name": "高价值货物险", "note": "高价值货物专项保障"},
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

    def create_order(
        self,
        *,
        origin_city: str,
        destination_city: str,
        customernumber1: str | None = None,
        number: int | None = None,
        endpoint: str = "/api/order/create",
    ) -> Dict[str, Any]:
        """Mock create order response matching the API documentation."""

        # Documentation shows a numeric systemnumber.
        sys_digits = int(hashlib.sha256(f"{origin_city}|{destination_city}|{customernumber1 or ''}".encode("utf-8")).hexdigest()[:12], 16)
        systemnumber = str(10_000_000_000_000 + (sys_digits % 9_000_000_000_000))

        wb_digits = int(hashlib.sha256(systemnumber.encode("utf-8")).hexdigest()[:10], 16)
        computed_waybillnumber = f"EV{(1_000_000_000_0 + (wb_digits % 9_000_000_000_0))}CN"

        customernumber = customernumber1 or f"MOCK-{_stable_id(computed_waybillnumber)}"

        child_count = int(number or 1)
        if child_count < 1:
            child_count = 1
        if child_count > 10:
            child_count = 10

        is_remote = bool(int(hashlib.sha256(computed_waybillnumber.encode("utf-8")).hexdigest()[:2], 16) % 2)

        # Simulate: waybillnumber may be empty and needs a follow-up call to /api/order/waybillnumber.
        defer_waybill = bool(int(hashlib.sha256(customernumber.encode("utf-8")).hexdigest()[:2], 16) % 5 == 0)
        waybillnumber = "" if defer_waybill else computed_waybillnumber
        shortnumber = (computed_waybillnumber[-6:] if computed_waybillnumber else systemnumber[-6:])

        childs: list[Dict[str, Any]] = []
        for i in range(1, child_count + 1):
            child_customernumber = f"CH-{_stable_id(customernumber, str(i)).upper()}"
            childs.append(
                {
                    "customernumber": child_customernumber,
                    "systemnumber": f"{systemnumber}-{i}",
                    "tracknumber": f"1Z{_stable_id(computed_waybillnumber, str(i)).upper()}",
                }
            )

        msg = "下单成功"
        if is_remote:
            msg = f"{msg}（偏远）"

        record = {
            "customernumber": customernumber,
            "systemnumber": systemnumber,
            "waybillnumber": computed_waybillnumber,
            "shortnumber": shortnumber,
            "isRemote": is_remote,
            "childs": childs,
        }
        self._orders_by_customernumber[customernumber] = record

        return {
            "code": 0,
            "msg": "调用成功",
            "data": [
                {
                    "code": 0,
                    "msg": msg,
                    "customernumber": customernumber,
                    "systemnumber": systemnumber,
                    "waybillnumber": waybillnumber,
                    "shortnumber": shortnumber,
                    "isRemote": is_remote,
                    "childs": childs,
                    "meta": {
                        "origin_city": origin_city,
                        "destination_city": destination_city,
                        "created_at": _now_str(),
                        "endpoint": endpoint,
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
        """创建预报订单，检查必需字段"""
        
        # 检查必需字段
        required_fields = [
            "customernumber1",      # 客户参考号
            "countrycode",          # 收件国家代码 (对应consignee_countrycode)
            "consigneename",        # 收件人姓名
            "consigneeaddress1",    # 收件地址
            "consigneecity",        # 收件城市
            "consigneezipcode",     # 收件邮编
            "consigneeprovince",    # 收件省州
            "declaretypepkid",      # 报关类型ID
            "producttypepkid",      # 产品类型ID  
            "insurancevalue",       # 保险价值
            "insurancetypepkid",    # 保险类型ID
            "insurancecurrency",    # 保险币别
            "isinsurance",          # 是否投保
            "forecastweight",       # 预估重量
            "number"                # 数量
        ]
        
        missing_fields = []
        order_data = {}
        
        # 从请求中提取订单数据
        if isinstance(request_payload, dict):
            datas = request_payload.get("datas")
            if isinstance(datas, list) and datas:
                order_data = datas[0].get("order", {}) if isinstance(datas[0], dict) else {}
        
        # 检查缺失字段
        for field in required_fields:
            if field not in order_data or order_data[field] is None or order_data[field] == "":
                missing_fields.append(field)
        
        # 如果有缺失字段，返回错误响应
        if missing_fields:
            # 特殊处理countrycode字段，映射回consignee_countrycode以保持一致性
            display_fields = []
            for field in missing_fields:
                if field == "countrycode":
                    display_fields.append("consignee_countrycode")
                else:
                    display_fields.append(field)
            
            # 返回与真实API一致的错误格式
            error_msg = f"Missing required field: {display_fields[0]}" if len(display_fields) == 1 else f"Missing required fields: {', '.join(display_fields)}"
            return {
                "code": -1,
                "msg": error_msg,
                "data": []
            }
        
        # 提取字段值
        customernumber1 = order_data.get("customernumber1")
        number = order_data.get("number", 1)
        if isinstance(number, str) and number.isdigit():
            number = int(number)
        
        # 创建订单
        payload = self.create_order(
            origin_city=origin_city,
            destination_city=destination_city,
            customernumber1=customernumber1,
            number=number,
            endpoint="/api/order/createForecast",
        )
        
        if request_payload is not None:
            payload["data"][0]["meta"]["request_payload"] = request_payload
            
        return payload

    def waybillnumber(self, *, customernumber: list[str]) -> Dict[str, Any]:
        """Mock /api/order/waybillnumber.

        Request datas.customernumber: ["T...", ...]
        Response data.customernumber: list of per-item results.
        """

        items: list[dict[str, Any]] = []
        for cn in customernumber:
            if not isinstance(cn, str) or cn.strip() == "":
                continue
            key = cn.strip()
            rec = self._orders_by_customernumber.get(key)
            if rec is None:
                items.append({"code": -1, "msg": "单号系统中不存在", "customernumber": key})
                continue

            # In the doc, tracknumber is top-level for the main order as well.
            top_track = None
            childs = rec.get("childs")
            if isinstance(childs, list) and childs:
                first = childs[0]
                if isinstance(first, dict) and isinstance(first.get("tracknumber"), str):
                    top_track = first.get("tracknumber")

            items.append(
                {
                    "code": 0,
                    "msg": "获取单号成功",
                    "customernumber": rec.get("customernumber"),
                    "systemnumber": rec.get("systemnumber"),
                    "waybillnumber": rec.get("waybillnumber"),
                    "tracknumber": top_track,
                    "shortnumber": rec.get("shortnumber"),
                    "childs": rec.get("childs"),
                }
            )

        return {
            "code": 0,
            "msg": "调用成功",
            "data": {"customernumber": items},
        }

    def track(self, *, waybillnumber: str) -> Dict[str, Any]:
        """Mock track API - 查询轨迹接口"""
        if not waybillnumber or waybillnumber.strip() == "":
            return {"msg": "success", "code": 0, "data": []}

        # 特殊处理订单号 #12345 (演示用例)
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

        # 检查是否是已创建的订单
        for customernumber, record in self._orders_by_customernumber.items():
            if record.get("waybillnumber") == waybillnumber:
                # 模拟真实的轨迹信息
                return {
                    "msg": "success", 
                    "code": 0,
                    "data": [
                        {
                            "searchNumber": waybillnumber,
                            "systemnumber": record.get("systemnumber"),
                            "waybillnumber": waybillnumber,
                            "tracknumber": record.get("childs", [{}])[0].get("tracknumber", ""),
                            "countrycode": "US",
                            "orderstatus": "InTransit",
                            "orderstatusName": "运输中",
                            "trackItems": [
                                {
                                    "location": "Shenzhen, CN",
                                    "trackdate_utc8": f"{_now_str()}",
                                    "trackdate": f"{_now_str()}",
                                    "info": "已揽收",
                                    "responsecode": "OT001",
                                },
                                {
                                    "location": "Processing Center",
                                    "trackdate_utc8": f"{_now_str()}",
                                    "trackdate": f"{_now_str()}",
                                    "info": "运输中",
                                    "responsecode": "OT002",
                                },
                            ],
                            "subOrderList": record.get("childs", []),
                            "subOrderTrackItems": {},
                        }
                    ],
                }

        # 无效单号
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