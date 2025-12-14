#!/usr/bin/env python3
"""
完整的订单调试测试
"""

from logistics_agent.agent import submit_forecast_order_from_text, get_waybillnumbers
import json

def test_complete_order_flow():
    """测试完整的下单流程"""
    print("🧪 完整订单下单测试")
    print("=" * 50)
    
    # 完整的订单文本
    text = """从深圳到洛杉矶；
customernumber1=T620200611-1001；
consignee_countrycode=US；
收件人=John Smith；
收件地址=123 Main St；
城市=Los Angeles；
邮编=90001；
省州=CA；
投保=是；
保额=100；
险种=货物运输险；
币别=USD；
物品类别=普货；
报关类型=不需报关"""
    
    print("📝 订单文本:")
    print(text)
    print("\n" + "="*30)
    
    # 提交订单
    result = submit_forecast_order_from_text(text)
    
    print("📋 下单结果:")
    print(f"状态: {result['status']}")
    
    if result['status'] == 'success':
        print("✅ 订单提交成功!")
        
        data = result.get('data', {})
        api_result = data.get('result', {})
        
        print(f"API响应码: {api_result.get('code', 'N/A')}")
        print(f"API消息: {api_result.get('msg', 'N/A')}")
        
        if 'data' in api_result and api_result['data']:
            order_info = api_result['data'][0]
            print(f"订单响应码: {order_info.get('code', 'N/A')}")
            print(f"订单消息: {order_info.get('msg', 'N/A')}")
            
            customernumber = order_info.get('customernumber')
            systemnumber = order_info.get('systemnumber')
            waybillnumber = order_info.get('waybillnumber')
            
            print(f"客户单号: {customernumber}")
            print(f"系统单号: {systemnumber}")
            print(f"运单号: {waybillnumber}")
            
            # 检查运单号是否为空
            if not waybillnumber:
                print("⚠️  运单号为空，尝试获取单号...")
                if customernumber:
                    waybill_result = get_waybillnumbers([customernumber])
                    print(f"获取单号结果: {waybill_result['status']}")
                    if waybill_result['status'] == 'success':
                        waybill_data = waybill_result.get('data', {}).get('raw', {}).get('data', {})
                        if 'customernumber' in waybill_data:
                            items = waybill_data['customernumber']
                            if items and len(items) > 0:
                                item = items[0]
                                print(f"最终运单号: {item.get('waybillnumber', 'N/A')}")
            
            # 检查子单号
            childs = order_info.get('childs', [])
            if childs:
                print(f"子单数量: {len(childs)}")
                for i, child in enumerate(childs, 1):
                    print(f"  子单{i}: {child.get('tracknumber', 'N/A')}")
            
            print("\n🎉 订单创建完成！")
            return True
            
    else:
        print("❌ 订单提交失败!")
        error = result.get('error', {})
        print(f"错误信息: {error.get('message', 'N/A')}")
        
        if 'missing_fields' in error:
            print(f"缺失字段: {error['missing_fields']}")
            print("\n💡 请确保包含以下必需字段:")
            required_fields = [
                "customernumber1 (客户参考号)",
                "consignee_countrycode (收件国家代码，如US)",
                "收件人",
                "收件地址", 
                "城市",
                "邮编",
                "省州"
            ]
            for field in required_fields:
                print(f"  - {field}")
        
        if 'reason' in error:
            print(f"详细原因: {error['reason']}")
        
        return False

def test_common_mistakes():
    """测试常见错误"""
    print("\n🔍 常见错误测试")
    print("=" * 50)
    
    mistakes = [
        {
            "name": "缺少收件国家代码",
            "text": "从深圳到洛杉矶；customernumber1=T001；收件人=John Smith；收件地址=123 Main St；城市=Los Angeles；邮编=90001；省州=CA"
        },
        {
            "name": "投保信息不完整", 
            "text": "从深圳到洛杉矶；customernumber1=T001；consignee_countrycode=US；收件人=John Smith；收件地址=123 Main St；城市=Los Angeles；邮编=90001；省州=CA；投保=是"
        },
        {
            "name": "使用错误的字段名",
            "text": "从深圳到洛杉矶；客户号=T001；收件国家=US；收件人=John Smith；收件地址=123 Main St；城市=Los Angeles；邮编=90001；省州=CA"
        }
    ]
    
    for mistake in mistakes:
        print(f"\n--- {mistake['name']} ---")
        result = submit_forecast_order_from_text(mistake['text'])
        print(f"结果: {result['status']}")
        if result['status'] == 'error':
            error = result.get('error', {})
            print(f"错误: {error.get('message', 'N/A')}")

if __name__ == "__main__":
    success = test_complete_order_flow()
    test_common_mistakes()
    
    print("\n" + "=" * 50)
    if success:
        print("✅ 测试完成：订单创建成功")
    else:
        print("❌ 测试完成：发现问题需要修复")
    
    print("\n💡 下单成功的关键要素:")
    print("1. 包含所有必需字段（特别是 consignee_countrycode）")
    print("2. 使用正确的字段名和格式")
    print("3. 如果启用投保，必须提供完整的投保信息")
    print("4. 使用标准的分隔符（分号；）和赋值符（=）")