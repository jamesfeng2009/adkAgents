#!/usr/bin/env python3
"""
创建从深圳到洛杉矶的物流订单
"""

from logistics_agent.agent import submit_forecast_order_from_text, get_declare_types
import json

def main():
    """创建从深圳到洛杉矶的物流订单"""
    print("🚚 创建从深圳到洛杉矶的物流订单")
    print("=" * 60)
    
    # 首先查看可用的报关类型
    print("📋 查看可用的报关类型:")
    declare_types = get_declare_types()
    if declare_types['status'] == 'success':
        types_data = declare_types['data']['raw']['data']
        for dt in types_data:
            print(f"  - 代码: {dt['code']}, 名称: {dt['name']}, 说明: {dt.get('note', '')}")
    print()
    
    # 你的订单信息
    order_text = """从深圳到洛杉矶；
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
报关类型=需要报关"""
    
    print("📝 订单详情:")
    print(order_text)
    print("\n" + "="*40)
    
    # 提交订单
    print("🔄 正在提交订单...")
    result = submit_forecast_order_from_text(order_text)
    
    print("📋 订单提交结果:")
    print(f"状态: {result['status']}")
    
    if result['status'] == 'success':
        print("✅ 订单创建成功!")
        
        data = result.get('data', {})
        
        # 显示请求载荷中的报关信息
        request_payload = data.get('request_payload', {})
        if request_payload and 'datas' in request_payload:
            order_data = request_payload['datas'][0]['order']
            declare_type_id = order_data.get('declaretypepkid')
            print(f"📦 使用的报关类型ID: {declare_type_id}")
            
            # 匹配报关类型名称
            if declare_types['status'] == 'success':
                types_data = declare_types['data']['raw']['data']
                for dt in types_data:
                    if dt['code'] == declare_type_id:
                        print(f"📦 报关类型名称: {dt['name']}")
                        break
        
        # 显示API响应
        api_result = data.get('result', {})
        print(f"🔗 API响应码: {api_result.get('code', 'N/A')}")
        print(f"💬 API消息: {api_result.get('msg', 'N/A')}")
        
        if 'data' in api_result and api_result['data']:
            order_info = api_result['data'][0]
            print(f"📋 订单响应码: {order_info.get('code', 'N/A')}")
            print(f"💬 订单消息: {order_info.get('msg', 'N/A')}")
            
            # 订单标识信息
            customernumber = order_info.get('customernumber')
            systemnumber = order_info.get('systemnumber')
            waybillnumber = order_info.get('waybillnumber')
            
            print(f"\n📋 订单标识信息:")
            print(f"  客户单号: {customernumber}")
            print(f"  系统单号: {systemnumber}")
            print(f"  运单号: {waybillnumber}")
            
            # 检查子单号
            childs = order_info.get('childs', [])
            if childs:
                print(f"\n📦 子单信息 (共{len(childs)}个):")
                for i, child in enumerate(childs, 1):
                    print(f"  子单{i}:")
                    print(f"    客户子单号: {child.get('customernumber', 'N/A')}")
                    print(f"    系统子单号: {child.get('systemnumber', 'N/A')}")
                    print(f"    转单号: {child.get('tracknumber', 'N/A')}")
            
            # 检查是否偏远地区
            is_remote = order_info.get('isRemote', False)
            if is_remote:
                print(f"\n⚠️  注意: 目的地为偏远地区")
            
            print(f"\n🎉 订单创建完成！")
            
            # 显示完整的JSON响应（用于调试）
            print(f"\n🔍 完整响应 (JSON):")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            
    else:
        print("❌ 订单创建失败!")
        error = result.get('error', {})
        print(f"错误信息: {error.get('message', 'N/A')}")
        
        if 'missing_fields' in error:
            print(f"缺失字段: {error['missing_fields']}")
        
        if 'reason' in error:
            print(f"详细原因: {error['reason']}")
            
        # 显示完整的错误响应
        print(f"\n🔍 完整错误响应 (JSON):")
        print(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()