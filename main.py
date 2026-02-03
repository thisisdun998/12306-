import time
import sys
import json
import re
from urllib.parse import unquote
from curl_cffi import requests
from stations import StationManager
from test import Tiantiel12306Login

class TicketBooking(Tiantiel12306Login):
    def __init__(self):
        super().__init__()
        self.station_manager = StationManager()
        self.ticket_info = {} # 存储车次信息 {train_no: {secret: ..., leftTicket: ..., location: ...}}

    def get_dynamic_query_url(self):
        """
        获取动态查票 URL
        """
        init_url = "https://kyfw.12306.cn/otn/leftTicket/init"
        try:
            print("正在获取动态查询接口...")
            resp = self.session.get(init_url, headers=self.headers, impersonate="chrome120")
            match = re.search(r"var CLeftTicketUrl = '([^']+)';", resp.text)
            if match:
                dynamic_part = match.group(1)
                print(f"获取动态查询接口成功: {dynamic_part}")
                return f"https://kyfw.12306.cn/otn/{dynamic_part}"
            else:
                print("未找到动态查询接口，使用默认接口")
                return "https://kyfw.12306.cn/otn/leftTicket/query"
        except Exception as e:
            print(f"获取动态 URL 失败: {e}")
            return "https://kyfw.12306.cn/otn/leftTicket/query"

    def query_ticket(self, from_station_name, to_station_name, date):
        """
        查询车票
        """
        from_code = self.station_manager.get_code(from_station_name)
        to_code = self.station_manager.get_code(to_station_name)
        
        if not from_code or not to_code:
            print(f"错误: 找不到车站")
            return None

        print(f"正在查询 {date} 从 {from_station_name}({from_code}) 到 {to_station_name}({to_code}) 的车票...")
        
        query_url = self.get_dynamic_query_url()
        
        params = {
            "leftTicketDTO.train_date": date,
            "leftTicketDTO.from_station": from_code,
            "leftTicketDTO.to_station": to_code,
            "purpose_codes": "ADULT"
        }

        try:
            resp = self.session.get(query_url, params=params, headers=self.headers, impersonate="chrome120")
            
            if "result" not in resp.json().get("data", {}):
                 print("查询接口返回数据异常，请重试")
                 return None

            result_list = resp.json()["data"]["result"]
            
            print(f"\n查询成功，共找到 {len(result_list)} 个车次：\n")
            print(f"{'车次':<6} {'出发':<6} {'到达':<6} {'历时':<6} {'二等座':<8} {'一等座':<8} {'商务座':<8}")
            print("-" * 60)

            available_trains = []

            for item_str in result_list:
                item = item_str.split("|")
                secret_str = item[0]      # 下单用的密钥
                train_no = item[3]        # 车次 (G101)
                start_time = item[8]
                arrive_time = item[9]
                duration = item[10]
                can_book = item[11]       # Y/N
                left_ticket = item[12]    # leftTicket 字段
                train_location = item[15] # train_location
                
                ze_num = item[30] if item[30] else "--" # 二等座
                zy_num = item[31] if item[31] else "--" # 一等座
                swz_num = item[32] if item[32] else "--" # 商务座
                
                # 存储更多信息供下单使用
                if secret_str:
                     self.ticket_info[train_no] = {
                         "secret": unquote(secret_str),
                         "leftTicket": left_ticket,
                         "location": train_location
                     }

                if can_book == "Y":
                    print(f"{train_no:<6} {start_time:<6} {arrive_time:<6} {duration:<6} {ze_num:<8} {zy_num:<8} {swz_num:<8}")
                    available_trains.append(train_no)
            
            print("-" * 60)
            return available_trains

        except Exception as e:
            print(f"查询异常: {e}")
            return None

    def check_user(self):
        """1. 校验用户状态"""
        url = "https://kyfw.12306.cn/otn/login/checkUser"
        data = {"_json_att": ""}
        try:
            resp = self.session.post(url, data=data, headers=self.headers, impersonate="chrome120")
            print(f"CheckUser: {resp.json()}")
            return resp.json().get("data", {}).get("flag") == True
        except Exception as e:
            print(f"CheckUser Error: {e}")
            return False

    def submit_order_request(self, secret_str, train_date, from_station_name, to_station_name):
        """2. 提交下单请求"""
        url = "https://kyfw.12306.cn/otn/leftTicket/submitOrderRequest"
        
        # 设置 Referer
        headers = self.headers.copy()
        headers["Referer"] = "https://kyfw.12306.cn/otn/leftTicket/init"
        
        data = {
            "secretStr": secret_str,
            "train_date": train_date, # 格式 2024-02-02
            "back_train_date": time.strftime("%Y-%m-%d", time.localtime()), # 返程日期(这里用当前日期占位)
            "tour_flag": "dc", # 单程
            "purpose_codes": "ADULT",
            "query_from_station_name": from_station_name,
            "query_to_station_name": to_station_name,
            "undefined": ""
        }
        try:
            resp = self.session.post(url, data=data, headers=headers, impersonate="chrome120")
            print(f"SubmitOrderRequest: {resp.json()}")
            return resp.json().get("status") == True
        except Exception as e:
            print(f"SubmitOrderRequest Error: {e}")
            return False

    def get_passengers_direct(self):
        """直接查询常用联系人，不依赖下单流程"""
        url = "https://kyfw.12306.cn/otn/passengers/query"
        data = {
            "pageIndex": "1",
            "pageSize": "100"
        }
        try:
            resp = self.session.post(url, data=data, headers=self.headers, impersonate="chrome120")
            if resp.json().get("data", {}).get("datas"):
                return resp.json()["data"]["datas"]
            return []
        except Exception as e:
            print(f"获取联系人失败: {e}")
            return []

    def get_token_and_ticket_info(self):
        """3. 获取 Token 和 关键参数 (initDc)"""
        init_dc_url = "https://kyfw.12306.cn/otn/confirmPassenger/initDc"
        data = {"_json_att": ""}
        
        # 设置 Referer
        headers = self.headers.copy()
        headers["Referer"] = "https://kyfw.12306.cn/otn/leftTicket/init"

        try:
            resp = self.session.post(init_dc_url, data=data, headers=headers, impersonate="chrome120")
            html = resp.text
            token = ""
            token_match = re.search(r"var globalRepeatSubmitToken = '([^']+)';", html)
            if token_match:
                token = token_match.group(1)
            else:
                print(f"InitDc Token 未找到。响应前500字符: {html[:500]}")
            
            ticket_info = {}
            ticket_info_match = re.search(r"var ticketInfoForPassengerForm = ({.*?});", html, re.DOTALL)
            if ticket_info_match:
                try:
                    t_info_str = ticket_info_match.group(1).replace("\n", "")
                    
                    key_match = re.search(r"'key_check_isChange':'([^']+)'", t_info_str)
                    if key_match: ticket_info['key_check_isChange'] = key_match.group(1)
                    
                    left_ticket_match = re.search(r"'leftTicketStr':'([^']+)'", t_info_str)
                    if left_ticket_match: ticket_info['leftTicketStr'] = left_ticket_match.group(1)
                        
                    location_match = re.search(r"'train_location':'([^']+)'", t_info_str)
                    if location_match: ticket_info['train_location'] = location_match.group(1)

                except Exception as e:
                    print(f"解析 ticketInfo 失败: {e}")
            else:
                print("InitDc TicketInfo 未找到。")
            
            return token, ticket_info
            
        except Exception as e:
            print(f"InitDc Error: {e}")
            return None, None


    def confirm_queue(self, train_no, passengers, token, key_check_isChange, left_ticket, train_location, seat_type="O"):
        """
        4. 确认出票
        新增参数 seat_type: 接受外部传入的席别代码 (O=二等座, M=一等座, 9=商务座)
        """
        passenger_ticket_str_list = []
        old_passenger_str_list = []

        for passenger in passengers:
            # --- 修正：这里直接使用传入的 seat_type，不再写死 "O" ---
            # passengerTicketStr: seat_type,0,ticket_type(1=adult),name,id_type,id_no,mobile,save_flag(N)
            p_str = f"{seat_type},0,1,{passenger['passenger_name']},{passenger['passenger_id_type_code']},{passenger['passenger_id_no']},{passenger['mobile_no']},N"
            passenger_ticket_str_list.append(p_str)

            # oldPassengerStr: name,id_type,id_no,passenger_type
            o_str = f"{passenger['passenger_name']},{passenger['passenger_id_type_code']},{passenger['passenger_id_no']},1_"
            old_passenger_str_list.append(o_str)

        passenger_ticket_str = "_".join(passenger_ticket_str_list)
        old_passenger_str = "".join(old_passenger_str_list)
        
        # 设置 Referer
        headers = self.headers.copy()
        headers["Referer"] = "https://kyfw.12306.cn/otn/confirmPassenger/initDc"

        # 4.1 checkOrderInfo
        check_url = "https://kyfw.12306.cn/otn/confirmPassenger/checkOrderInfo"
        check_data = {
            "cancel_flag": "2",
            "bed_level_order_num": "000000000000000000000000000000",
            "passengerTicketStr": passenger_ticket_str,
            "oldPassengerStr": old_passenger_str,
            "tour_flag": "dc",
            "randCode": "",
            "whatsSelect": "1",
            "sessionId": "",
            "sig": "",
            "scene": "nc_login",
            "_json_att": "",
            "REPEAT_SUBMIT_TOKEN": token
        }
        
        try:
            resp = self.session.post(check_url, data=check_data, headers=headers, impersonate="chrome120")
            print(f"CheckOrderInfo: {resp.json()}")
            if not resp.json().get("data", {}).get("submitStatus"):
                 print(f"校验订单失败: {resp.json().get('data', {}).get('errMsg')}")
                 return False
        except Exception as e:
            print(f"CheckOrderInfo Error: {e}")
            return False

        # 4.2 confirmSingleForQueue
        confirm_url = "https://kyfw.12306.cn/otn/confirmPassenger/confirmSingleForQueue"
        try:
            # 必须对 leftTicketStr 进行解码
            decoded_left_ticket = unquote(left_ticket)
            confirm_data = {
                "passengerTicketStr": passenger_ticket_str,
                "oldPassengerStr": old_passenger_str,
                "randCode": "",
                "purpose_codes": "00",
                "key_check_isChange": key_check_isChange,
                "leftTicketStr": decoded_left_ticket,
                "train_location": train_location,
                "choose_seats": "", 
                "seatDetailType": "000",
                "whatsSelect": "1",
                "roomType": "00",
                "dwAll": "N",
                "_json_att": "",
                "REPEAT_SUBMIT_TOKEN": token
            }
            
            resp = self.session.post(confirm_url, data=confirm_data, headers=headers, impersonate="chrome120")
            print(f"ConfirmQueue: {resp.json()}")
            return resp.json().get("data", {}).get("submitStatus") == True
        except Exception as e:
            print(f"ConfirmQueue Error: {e}")
            return False

    def execute_booking(self, from_station, to_station, date, target_train_no, selected_passengers, seat_type):
        """执行一次完整的抢票流程 (Query -> Submit -> InitDc -> Confirm)"""
        
        # 1. 查询最新 SecretStr
        print(f"\n>>> 正在获取最新票务信息 ({target_train_no})...")
        trains = self.query_ticket(from_station, to_station, date)
        if target_train_no not in self.ticket_info:
            print("刷新失败，车次可能已不可预订")
            return False
            
        info = self.ticket_info.get(target_train_no)
        fresh_secret_str = info['secret']
        left_ticket = info['leftTicket']
        train_location = info['location']

        # 2. 提交订单请求
        if not self.submit_order_request(fresh_secret_str, date, from_station, to_station):
            print("提交订单请求失败 (车次过期/无票/风控)")
            return False

        # 3. 获取 Token 和 关键参数 (initDc)
        # 这一步必须在 submit 成功后进行，以获取最新的 token 和 key_check
        token, ticket_info = self.get_token_and_ticket_info()
        if not token or not ticket_info:
            print("初始化订单页面失败 (InitDc)")
            return False
            
        # 使用 initDc 返回的最新数据更新
        if ticket_info.get('leftTicketStr'):
            left_ticket = ticket_info.get('leftTicketStr')
        if ticket_info.get('train_location'):
            train_location = ticket_info.get('train_location')
        key_check = ticket_info.get('key_check_isChange')

        # 4. 确认排队
        if self.confirm_queue(target_train_no, selected_passengers, token, key_check, left_ticket, train_location, seat_type=seat_type):
            print("\n✅ 下单请求已提交！请立即打开 12306 APP 查看未完成订单并付款！")
            return True
        else:
            print("\n❌ 下单失败")
            return False

    def run_interactive_loop(self):
        """主交互循环"""
        while True:
            # 1. 输入基本信息
            print("\n" + "="*50)
            from_station = input("请输入出发站 (例如 北京): ").strip()
            to_station = input("请输入到达站 (例如 上海): ").strip()
            date = input("请输入日期 (例如 2024-02-05): ").strip()
            
            if not (from_station and to_station and date):
                print("信息不完整，请重新输入")
                continue

            # 2. 查票
            trains = self.query_ticket(from_station, to_station, date)
            if not trains:
                retry = input("查询无结果，是否重试? (y/n): ")
                if retry.lower() == 'y': continue
                else: continue # 回到开头

            target_train_no = input("\n请输入要抢的车次 (例如 G1): ").strip()
            # 这里简单校验一下 ticket_info 是否有该车次，虽然 query_ticket 已经填充了
            if target_train_no not in self.ticket_info:
                print("无效的车次，请重新开始")
                continue
                
            # 3. 准备乘客和座位
            if not self.check_user():
                print("登录状态失效，尝试重新登录...")
                if not self.run(): # 尝试重新登录
                    print("重新登录失败，退出")
                    return

            print("正在获取联系人列表...")
            passengers = self.get_passengers_direct()
            if not passengers:
                print("未找到联系人，请检查登录状态或是否已添加联系人")
                continue
                
            print(f"\n发现 {len(passengers)} 位乘车人:")
            for idx, p in enumerate(passengers):
                print(f"{idx}: {p['passenger_name']} ({p['passenger_id_no']})")
                
            # 选择乘车人
            selected_passengers = []
            while True:
                selection = input("\n请输入乘车人序号(多选使用逗号分隔, 例如 0,1): ").strip()
                if not selection: continue
                try:
                    indices = [int(i.strip()) for i in selection.replace('，', ',').split(',')]
                    valid = True
                    temp_selected = []
                    for i in indices:
                        if 0 <= i < len(passengers):
                            temp_selected.append(passengers[i])
                        else:
                            print(f"序号 {i} 无效"); valid = False; break
                    if valid:
                        selected_passengers = temp_selected; break
                except ValueError:
                    print("输入格式错误")

            # 选择座位
            print("\n请选择座位类型:")
            print("1: 二等座 (O)")
            print("2: 一等座 (M)")
            print("3: 商务座 (9)")
            print("4: 无座 (1)")
            seat_map = {"1": "O", "2": "M", "3": "9", "4": "1"}
            seat_input = input("请输入序号 (默认1): ").strip()
            target_seat_type = seat_map.get(seat_input, "O")
            
            names = ", ".join([p['passenger_name'] for p in selected_passengers])
            
            # 4. 抢票循环
            while True:
                print(f"\n>>> 准备抢票: {target_train_no} | 乘客: {names} | 坐席: {target_seat_type}")
                
                success = self.execute_booking(from_station, to_station, date, target_train_no, selected_passengers, target_seat_type)
                
                if success:
                    print("抢票流程结束。")
                    return # 成功后退出
                
                # 失败交互
                choice = input("\n[抢票失败] r: 重试当前车次, n: 重新选车次/时间, q: 退出程序 > ").strip().lower()
                if choice == 'r':
                    time.sleep(1) # 稍作休眠避免过快
                    continue
                elif choice == 'q':
                    sys.exit(0)
                else:
                    break # 跳出内层循环，回到最外层

if __name__ == "__main__":
    ticket_booking = TicketBooking()
    
    # 扫码登录 (支持 Redis 缓存)
    if not ticket_booking.run():
        sys.exit(1)
        
    ticket_booking.run_interactive_loop()

