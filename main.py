import time
import sys
import json
from curl_cffi import requests
from stations import StationManager
from test import Tiantiel12306Login  # 假设 test.py 在同一目录下

class TicketBooking(Tiantiel12306Login):
    def __init__(self):
        super().__init__()
        self.station_manager = StationManager()

    def query_ticket(self, from_station_name, to_station_name, date):
        """
        查询车票
        :param from_station_name: 出发地中文名
        :param to_station_name: 目的地中文名
        :param date: 出发日期，格式 YYYY-MM-DD
        """
        from_code = self.station_manager.get_code(from_station_name)
        to_code = self.station_manager.get_code(to_station_name)
        
        if not from_code:
            print(f"错误: 找不到车站 '{from_station_name}'")
            return
        if not to_code:
            print(f"错误: 找不到车站 '{to_station_name}'")
            return

        print(f"正在查询 {date} 从 {from_station_name}({from_code}) 到 {to_station_name}({to_code}) 的车票...")
        
        # 查票接口 URL 可能会变，如果 query 失败，尝试 queryZ 或 queryA 等
        # 也可以先访问 https://kyfw.12306.cn/otn/leftTicket/init 获取动态的查询 URL
        query_url = "https://kyfw.12306.cn/otn/leftTicket/query" 
        
        params = {
            "leftTicketDTO.train_date": date,
            "leftTicketDTO.from_station": from_code,
            "leftTicketDTO.to_station": to_code,
            "purpose_codes": "ADULT"
        }

        try:
            resp = self.session.get(query_url, params=params, headers=self.headers, impersonate="chrome120")
            
            # 这里的接口有时会返回 302 或者 html，需要处理
            if "result" not in resp.json().get("data", {}):
                 # 尝试另一个常见的接口后缀，或者直接打印 resp 查看
                 # 实际上 12306 查询接口经常变，比如 queryA, queryZ 等
                 # 这里做一个简单的容错，如果 query 失败，通常需要先访问 init 页面拿到 CLeftTicketUrl
                 print("查询接口返回数据格式可能有变，尝试解析...")
                 print(resp.text[:200])
                 return

            result_list = resp.json()["data"]["result"]
            map_data = resp.json()["data"]["map"]
            
            print(f"\n查询成功，共找到 {len(result_list)} 个车次：\n")
            print(f"{'车次':<6} {'出发':<6} {'到达':<6} {'历时':<6} {'二等座':<8} {'一等座':<8} {'商务座':<8}")
            print("-" * 60)

            for item_str in result_list:
                item = item_str.split("|")
                # 简单解析关键字段 (索引可能会随 12306 更新而变化)
                train_no = item[3]        # 车次
                start_time = item[8]      # 出发时间
                arrive_time = item[9]     # 到达时间
                duration = item[10]       # 历时
                
                # 余票状态：有/无/数字
                ze_num = item[30] if item[30] else "--" # 二等座
                zy_num = item[31] if item[31] else "--" # 一等座
                swz_num = item[32] if item[32] else "--" # 商务座
                
                # 过滤掉无法预订的车次（比如 "预订" 字段不是 Y 的）
                can_book = item[11] # "Y" 代表可以预订
                
                if can_book == "Y":
                    print(f"{train_no:<6} {start_time:<6} {arrive_time:<6} {duration:<6} {ze_num:<8} {zy_num:<8} {swz_num:<8}")
            
            print("-" * 60)

        except Exception as e:
            print(f"查询异常: {e}")

    def submit_order(self, train_no, from_station, to_station):
        """
        [TODO] 提交订单逻辑框架
        需要实现的步骤：
        1. 校验用户状态 (checkUser)
        2. 提交下单请求 (submitOrderRequest)
        3. 获取乘客信息 (getPassengerDTOs)
        4. 检查订单信息 (checkOrderInfo)
        5. 获取排队人数 (getQueueCount)
        6. 确认提交 (confirmSingleForQueue)
        """
        print(f"准备抢票: {train_no}...")
        # 这是一个复杂的流程，建议先调通查票，然后逐步实现
        pass

if __name__ == "__main__":
    bot = TicketBooking()
    
    # 先尝试登录
    if bot.run(): 
        # 登录成功后进行查票
        # 这里为了演示，写死一些参数，实际可以 input 获取
        print("\n=== 开始查票 ===")
        # 获取明天的日期
        tomorrow = time.strftime("%Y-%m-%d", time.localtime(time.time() + 86400))
        
        # 可以在这里修改出发地和目的地
        from_station = "北京"
        to_station = "上海"
        
        bot.query_ticket(from_station, to_station, tomorrow)
