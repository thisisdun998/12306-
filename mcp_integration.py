#!/usr/bin/env python3
"""
12306 MCP服务集成模块
提供标准化的车站编码查询、余票查询等接口
"""

import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional

class MCP12306Service:
    """12306 MCP服务封装类"""
    
    def __init__(self):
        self.station_cache = {}
        self.load_station_data()
    
    def load_station_data(self):
        """加载车站数据到缓存"""
        try:
            with open('stations.json', 'r', encoding='utf-8') as f:
                self.station_cache = json.load(f)
            print(f"已加载 {len(self.station_cache)} 个车站数据")
        except Exception as e:
            print(f"加载车站数据失败: {e}")
            self.station_cache = {}
    
    def get_station_code(self, city_name: str) -> Optional[str]:
        """获取城市对应的车站编码"""
        # 直接查询缓存
        if city_name in self.station_cache:
            return self.station_cache[city_name]
        
        # 如果缓存中没有，尝试模糊匹配
        for station_name, code in self.station_cache.items():
            if city_name in station_name or station_name.startswith(city_name):
                return code
        
        return None
    
    def get_stations_in_city(self, city_name: str) -> List[Dict]:
        """获取城市内的所有车站"""
        result = []
        for station_name, code in self.station_cache.items():
            if city_name in station_name:
                result.append({
                    'name': station_name,
                    'code': code
                })
        return result
    
    def format_date(self, date_input: str) -> str:
        """格式化日期为 yyyy-MM-dd 格式"""
        if isinstance(date_input, str):
            # 支持相对日期
            if date_input == "今天":
                return datetime.now().strftime("%Y-%m-%d")
            elif date_input == "明天":
                return (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            elif date_input == "后天":
                return (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
            else:
                # 尝试解析各种日期格式
                try:
                    # 支持 yyyyMMdd 格式
                    if len(date_input) == 8 and date_input.isdigit():
                        return f"{date_input[:4]}-{date_input[4:6]}-{date_input[6:]}"
                    # 支持 yyyy/MM/dd 或 yyyy.MM.dd 格式
                    for separator in ['/', '.', '-']:
                        if separator in date_input:
                            parts = date_input.split(separator)
                            if len(parts) == 3:
                                year, month, day = parts
                                return f"{year}-{int(month):02d}-{int(day):02d}"
                    return date_input  # 假设已经是正确格式
                except:
                    return datetime.now().strftime("%Y-%m-%d")
        return datetime.now().strftime("%Y-%m-%d")

class OptimizedTicketBooking:
    """优化的订票流程类"""
    
    def __init__(self, booking_instance):
        self.booking = booking_instance
        self.mcp_service = MCP12306Service()
    
    def smart_query_tickets(self, from_city: str, to_city: str, date_input: str, 
                          train_types: str = "", sort_by: str = "") -> List[Dict]:
        """
        智能查询车票
        
        Args:
            from_city: 出发城市
            to_city: 到达城市  
            date_input: 日期（支持"今天"、"明天"等相对日期）
            train_types: 车次类型筛选（如"G"高铁，"D"动车等）
            sort_by: 排序方式（"time"按时间，"price"按价格等）
        """
        # 1. 智能车站编码查询
        from_code = self.mcp_service.get_station_code(from_city)
        to_code = self.mcp_service.get_station_code(to_city)
        
        if not from_code or not to_code:
            # 尝试获取城市内所有车站
            from_stations = self.mcp_service.get_stations_in_city(from_city)
            to_stations = self.mcp_service.get_stations_in_city(to_city)
            
            if not from_stations or not to_stations:
                raise ValueError(f"找不到车站信息: {from_city} -> {to_city}")
            
            # 默认使用第一个车站
            from_code = from_stations[0]['code']
            to_code = to_stations[0]['code']
            print(f"使用车站: {from_stations[0]['name']} -> {to_stations[0]['name']}")
        
        # 2. 智能日期格式化
        formatted_date = self.mcp_service.format_date(date_input)
        
        # 3. 执行查询
        print(f"查询车票: {from_city}({from_code}) -> {to_city}({to_code}), 日期: {formatted_date}")
        
        # 这里调用原始的查询方法
        trains = self.booking.query_ticket(from_city, to_city, formatted_date)
        
        if not trains:
            return []
        
        # 4. 处理筛选和排序
        filtered_trains = self._filter_and_sort_trains(trains, train_types, sort_by)
        
        return filtered_trains
    
    def _filter_and_sort_trains(self, trains: List[str], train_types: str, sort_by: str) -> List[Dict]:
        """过滤和排序车次"""
        result = []
        train_type_set = set()
        if train_types:
            for t in train_types.replace("，", ",").split(","):
                t = t.strip()
                if t:
                    train_type_set.add(t)
        
        for train_info in trains:
            # 解析车次信息
            if isinstance(train_info, str):
                if "|" in train_info:
                    parts = train_info.split('|')
                    if len(parts) >= 33:
                        train_dict = {
                            'train_no': parts[3],           # 车次
                            'start_time': parts[8],         # 出发时间
                            'arrive_time': parts[9],        # 到达时间
                            'duration': parts[10],          # 历时
                            'ze_num': parts[30] or '--',    # 二等座
                            'zy_num': parts[31] or '--',    # 一等座
                            'swz_num': parts[32] or '--',   # 商务座
                            'train_type': parts[3][0] if len(parts) > 3 else ''  # 车次类型(G/D/Z等)
                        }
                    else:
                        continue
                else:
                    # 兼容 query_ticket 返回的车次号列表
                    train_no = train_info
                    info = self.booking.ticket_info.get(train_no, {})
                    train_dict = {
                        'train_no': train_no,
                        'start_time': info.get('start_time', '--'),
                        'arrive_time': info.get('arrive_time', '--'),
                        'duration': info.get('duration', '--'),
                        'ze_num': info.get('ze_num', '--'),
                        'zy_num': info.get('zy_num', '--'),
                        'swz_num': info.get('swz_num', '--'),
                        'train_type': train_no[0] if train_no else ''
                    }
                
                # 车次类型筛选
                if train_type_set and train_dict['train_type'] not in train_type_set:
                    continue
                
                result.append(train_dict)
        
        # 排序
        if sort_by == "time":
            result.sort(key=lambda x: x['start_time'])
        elif sort_by == "duration":
            result.sort(key=lambda x: x['duration'])
        
        return result
    
    def batch_query_multiple_dates(self, from_city: str, to_city: str, 
                                 dates: List[str]) -> Dict[str, List[Dict]]:
        """批量查询多个日期的车票"""
        results = {}
        
        for date in dates:
            try:
                tickets = self.smart_query_tickets(from_city, to_city, date)
                results[date] = tickets
                print(f"日期 {date}: 找到 {len(tickets)} 趟车次")
            except Exception as e:
                print(f"查询日期 {date} 失败: {e}")
                results[date] = []
        
        return results

# 使用示例
def demo_usage():
    """演示使用方法"""
    # 假设已经有booking实例
    # booking = TicketBooking()
    # optimizer = OptimizedTicketBooking(booking)
    
    # 示例1: 智能查询
    # tickets = optimizer.smart_query_tickets("北京", "上海", "明天", "G", "time")
    
    # 示例2: 批量查询
    # dates = ["今天", "明天", "后天"]
    # batch_results = optimizer.batch_query_multiple_dates("北京", "上海", dates)
    
    print("MCP集成模块已准备就绪")

if __name__ == "__main__":
    demo_usage()
