#!/usr/bin/env python3
"""
简单的测试脚本，验证物流Agent的核心功能
"""

import json
from logistics_agent.mock_logistics_api import MockLogisticsApi
from logistics_agent.agent import (
    create_forecast_order_with_preferences,
    query_order_status,
    get_waybillnumbers,
    submit_forecast_order_from_text
)

def test_mock_apis():
    """测试Mock API接口"""
    print("=== 测试Mock API接口 ===")
    
    api = MockLogisticsApi()
    
    # 测试字典接口
    print("1. 测试投保类型接口:")
    insurance_result = api.insurance()
    print(json.dumps(insurance_result, ensure_ascii=False, indent=2))
    
    print("\n2. 测试币别接口:")
    currency_result = api.currency()
    print(json.dumps(currency_result, ensure_ascii=False, indent=2))
    
    print("\n3. 测试物品类别接口:")
    product_result = api.get_product_type()
    print(json.dumps(product_result, ensure_ascii=False, indent=2))

def test_create_order():
    """测试创建订单功能"""
    print("\n=== 测试创建订单功能 ===")
    
    # 测试使用偏好设置创建订单
    result = create_forecast_order_with_preferences(
        origin_city="深圳",
        destination_city="洛杉矶", 
        customernumber1="T620200611-1001",
        consignee_countrycode="US",
        consigneename="John Smith",
        consigneeaddress1="123 Main St",
        consigneecity="Los Angeles",
        consigneezipcode="90001",
        consigneeprovince="CA",
        insurance_enabled=True,
        insurance_value=100.0,
        insurance_type_name="货物运输险",
        insurance_currency_code="USD",
        declare_type_name="不需报关",
        product_type_name="普货"
    )
    
    print("创建订单结果:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
    return result

def test_natural_language_order():
    """测试自然语言创建订单"""
    print("\n=== 测试自然语言创建订单 ===")
    
    text = """从深圳到洛杉矶；customernumber1=T620200611-1002；收件国家=US；收件人=Jane Doe；
    收件地址=456 Oak Ave；城市=Los Angeles；邮编=90002；省州=CA；投保=是；保额=150；
    险种=货物运输险；币别=USD；物品类别=普货；报关类型=不需报关"""
    
    result = submit_forecast_order_from_text(text)
    print("自然语言订单创建结果:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
    return result

def test_query_status():
    """测试查询订单状态"""
    print("\n=== 测试查询订单状态 ===")
    
    # 测试查询演示订单 #12345
    result = query_order_status("12345")
    print("查询订单 #12345 状态:")
    print(json.dumps(result, ensure_ascii=False, indent=2))

def test_get_waybillnumber():
    """测试获取单号功能"""
    print("\n=== 测试获取单号功能 ===")
    
    result = get_waybillnumbers(["T620200611-1001", "T620200611-1002"])
    print("获取单号结果:")
    print(json.dumps(result, ensure_ascii=False, indent=2))

def main():
    """运行所有测试"""
    print("物流Agent功能测试")
    print("=" * 50)
    
    try:
        # 测试Mock API
        test_mock_apis()
        
        # 测试创建订单
        order_result = test_create_order()
        
        # 测试自然语言订单
        nl_result = test_natural_language_order()
        
        # 测试查询状态
        test_query_status()
        
        # 测试获取单号
        test_get_waybillnumber()
        
        print("\n" + "=" * 50)
        print("✅ 所有测试完成！")
        
        # 提取关键信息
        if order_result.get("status") == "success":
            data = order_result.get("data", {})
            result = data.get("result", {})
            if result.get("data"):
                first_order = result["data"][0]
                print(f"\n📋 订单信息:")
                print(f"   系统单号: {first_order.get('systemnumber')}")
                print(f"   运单号: {first_order.get('waybillnumber')}")
                print(f"   客户参考号: {first_order.get('customernumber')}")
        
    except Exception as e:
        print(f"\n❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()