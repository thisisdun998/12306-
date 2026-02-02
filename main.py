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
            resp = self.session.post(url, data=data, headers=self.headers, impersonate="chrome120")
            print(f"SubmitOrderRequest: {resp.json()}")
            return resp.json().get("status") == True
        except Exception as e:
            print(f"SubmitOrderRequest Error: {e}")
            return False

    def get_token_and_passenger(self):
        """3. 获取 Token 和 乘客信息"""
        init_dc_url = "https://kyfw.12306.cn/otn/confirmPassenger/initDc"
        data = {"_json_att": ""}
        token = ""
        ticket_info_for_passenger_form = {}
        
        try:
            resp = self.session.post(init_dc_url, data=data, headers=self.headers, impersonate="chrome120")
            html = resp.text
            token_match = re.search(r"var globalRepeatSubmitToken = '([^']+)';", html)
            if token_match:
                token = token_match.group(1)
            
            ticket_info_match = re.search(r"var ticketInfoForPassengerForm = ({.*?});", html, re.DOTALL)
            if ticket_info_match:
                try:
                    # 使用 json 解析可能更稳健，但 JS 对象格式可能不完全符合 JSON 标准，这里还是用正则提取关键字段
                    t_info_str = ticket_info_match.group(1).replace("\n", "")
                    
                    # 提取 key_check_isChange
                    key_match = re.search(r"'key_check_isChange':'([^']+)'", t_info_str)
                    if key_match:
                        ticket_info_for_passenger_form['key_check_isChange'] = key_match.group(1)
                    
                    # 提取 leftTicketStr
                    left_ticket_match = re.search(r"'leftTicketStr':'([^']+)'", t_info_str)
                    if left_ticket_match:
                        ticket_info_for_passenger_form['leftTicketStr'] = left_ticket_match.group(1)
                        
                    # 提取 train_location
                    location_match = re.search(r"'train_location':'([^']+)'", t_info_str)
                    if location_match:
                         ticket_info_for_passenger_form['train_location'] = location_match.group(1)

                except Exception as e:
                    print(f"解析 ticketInfoForPassengerForm 失败: {e}")
            
            print(f"Token: {token}")
            
            passenger_url = "https://kyfw.12306.cn/otn/confirmPassenger/getPassengerDTOs"
            p_data = {
                "_json_att": "",
                "REPEAT_SUBMIT_TOKEN": token
            }
            p_resp = self.session.post(passenger_url, data=p_data, headers=self.headers, impersonate="chrome120")
            passengers = p_resp.json().get("data", {}).get("normal_passengers", [])
            
            return token, ticket_info_for_passenger_form, passengers
            
        except Exception as e:
            print(f"GetTokenAndPassenger Error: {e}")
            return None, None, None

    def confirm_queue(self, train_no, passengers, token, key_check_isChange, left_ticket, train_location):
        """4. 确认出票"""
        passenger_ticket_str_list = []
        old_passenger_str_list = []

        for passenger in passengers:
            seat_type = "O"  # 默认二等座
            # passengerTicketStr: seat_type,0,ticket_type(1=adult),name,id_type,id_no,mobile,save_flag(N)
            p_str = f"{seat_type},0,1,{passenger['passenger_name']},{passenger['passenger_id_type_code']},{passenger['passenger_id_no']},{passenger['mobile_no']},N"
            passenger_ticket_str_list.append(p_str)

            # oldPassengerStr: name,id_type,id_no,passenger_type
            # 注意：这里末尾必须带 _
            o_str = f"{passenger['passenger_name']},{passenger['passenger_id_type_code']},{passenger['passenger_id_no']},1_"
            old_passenger_str_list.append(o_str)

        passenger_ticket_str = "_".join(passenger_ticket_str_list)
        old_passenger_str = "".join(old_passenger_str_list)

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
            resp = self.session.post(check_url, data=check_data, headers=self.headers, impersonate="chrome120")
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
                "choose_seats": "", # 选座，暂空
                "seatDetailType": "000",
                "whatsSelect": "1",
                "roomType": "00",
                "dwAll": "N",
                "_json_att": "",
                "REPEAT_SUBMIT_TOKEN": token
            }
            
            resp = self.session.post(confirm_url, data=confirm_data, headers=self.headers, impersonate="chrome120")
            print(f"ConfirmQueue: {resp.json()}")
            return resp.json().get("data", {}).get("submitStatus") == True
        except Exception as e:
            print(f"ConfirmQueue Error: {e}")
            return False

    def run_order_flow(self, from_station, to_station, date, target_train_no):
        """执行完整的下单流程"""
        # 1. 查票
        trains = self.query_ticket(from_station, to_station, date)
        if target_train_no not in trains:
            print(f"车次 {target_train_no} 不存在或不可预订")
            return

        info = self.ticket_info.get(target_train_no)
        secret_str = info['secret']
        left_ticket = info['leftTicket']
        train_location = info['location']
        
        # 2. CheckUser
        if not self.check_user():
            print("用户未登录或状态异常，请重新运行程序扫码登录")
            return

        # 3. SubmitOrderRequest
        if not self.submit_order_request(secret_str, date, from_station, to_station):
            print("提交订单请求失败")
            return

        # 4. Get Token & Passengers
        token, ticket_info, passengers = self.get_token_and_passenger()
        if not token or not passengers:
            print("获取 Token 或乘客信息失败")
            return
        
        print(f"\n发现 {len(passengers)} 位乘车人:")
        for idx, p in enumerate(passengers):
            print(f"{idx}: {p['passenger_name']} ({p['passenger_id_no']})")
        
        # 手动选择乘车人
        selected_passengers = []
        while True:
            selection = input("\n请输入乘车人序号(多选使用逗号分隔, 例如 0,1): ").strip()
            if not selection:
                print("请输入序号")
                continue
            
            try:
                # 支持中文逗号和英文逗号
                indices = [int(i.strip()) for i in selection.replace('，', ',').split(',')]
                valid = True
                temp_selected = []
                for i in indices:
                    if 0 <= i < len(passengers):
                        temp_selected.append(passengers[i])
                    else:
                        print(f"序号 {i} 无效")
                        valid = False
                        break
                
                if valid:
                    selected_passengers = temp_selected
                    break
            except ValueError:
                print("输入格式错误，请输入数字")

        names = ", ".join([p['passenger_name'] for p in selected_passengers])
        print(f"正在为 [{names}] 抢 {target_train_no} 的票...")

        # 更新 leftTicketStr 和 train_location (如果 initDc 返回了新的值)
        if ticket_info.get('leftTicketStr'):
            print(f"使用最新的 leftTicketStr: {ticket_info.get('leftTicketStr')[:20]}...")
            left_ticket = ticket_info.get('leftTicketStr')
        
        if ticket_info.get('train_location'):
             train_location = ticket_info.get('train_location')

        # 5. Confirm Queue
        if self.confirm_queue(target_train_no, selected_passengers, token, ticket_info.get('key_check_isChange'), left_ticket, train_location):
            print("下单请求已提交！请去 APP 查看未完成订单！")
            
            # 这里还可以增加一个 queryOrderWaitTime 的轮询，来确认是否真正出票成功
            # 但作为 MVP，提交成功通常就意味着排队成功
        else:
            print("下单失败")


if __name__ == "__main__":
    bot = TicketBooking()
    if bot.run(): 
        print("\n=== 自动抢票模式 ===")
        # 示例：抢明天的票
        tomorrow = time.strftime("%Y-%m-%d", time.localtime(time.time() + 172000))
        from_st = "武汉"
        to_st = "杭州"
        
        # 1. 先查一次，让用户看有什么车
        available_trains = bot.query_ticket(from_st, to_st, tomorrow)
        
        if available_trains:
            target = input("\n请输入要抢的车次 (例如 G1): ").strip()
            if target in available_trains:
                bot.run_order_flow(from_st, to_st, tomorrow, target)
            else:
                print("车次无效")
