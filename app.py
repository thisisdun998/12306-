import json
import time
import threading
import os
from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
import redis
from main import TicketBooking

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # 生产环境请更换为安全的密钥
CORS(app)

# Redis连接配置
try:
    redis_client = redis.Redis(
        host=os.getenv('REDIS_HOST', 'localhost'),
        port=int(os.getenv('REDIS_PORT', 6379)),
        password=os.getenv('REDIS_PASSWORD', 'xiaodun'),  # 使用您提供的密码
        db=int(os.getenv('REDIS_DB', 0)),
        decode_responses=True,
        socket_connect_timeout=5
    )
    # 测试连接
    redis_client.ping()
    print("Redis连接成功")
    USE_REDIS = True
except Exception as e:
    print(f"Redis连接失败: {e}")
    redis_client = None
    USE_REDIS = False

# 全局变量存储登录状态和实例
booking_instances = {}
qr_status_polling = {}

class BookingManager:
    def __init__(self):
        self.booking = TicketBooking()
        self.login_status = False
        self.current_qr_uuid = None
        self.qr_status_thread = None
        self.qr_status_result = None
        
    def save_session(self, session_id):
        """保存会话状态到Redis"""
        if USE_REDIS and redis_client:
            try:
                session_data = {
                    'login_status': self.login_status,
                    'current_qr_uuid': self.current_qr_uuid,
                    'ticket_info': self.booking.ticket_info
                }
                # 设置24小时过期时间（延长登录保持时间）
                redis_client.setex(f"session:{session_id}", 86400, json.dumps(session_data))  # 24小时
                print(f"会话状态已保存: {session_id}")
                return True
            except Exception as e:
                print(f"保存会话失败: {e}")
                return False
        return False
    
    def load_session(self, session_id):
        """从Redis加载会话状态"""
        if USE_REDIS and redis_client:
            try:
                session_data = redis_client.get(f"session:{session_id}")
                if session_data:
                    data = json.loads(session_data)
                    self.login_status = data.get('login_status', False)
                    self.current_qr_uuid = data.get('current_qr_uuid')
                    self.booking.ticket_info = data.get('ticket_info', {})
                    # 尝试恢复登录 Cookies（用于 Web 端重启后的会话续期）
                    if self.login_status:
                        try:
                            self.booking.load_cookies()
                        except Exception:
                            pass
                    print(f"会话状态已恢复: {session_id}")
                    return True
            except Exception as e:
                print(f"加载会话失败: {e}")
        return False
    
    def clear_session(self, session_id):
        """清除会话状态"""
        if USE_REDIS and redis_client:
            try:
                redis_client.delete(f"session:{session_id}")
                print(f"会话已清除: {session_id}")
                return True
            except Exception as e:
                print(f"清除会话失败: {e}")
                return False
        return False

    def get_qr_code(self):
        """获取登录二维码（Web 端）"""
        result = self.booking.get_qr_code_data(show_image=False)
        if result.get("success"):
            self.current_qr_uuid = result.get("uuid")
            self.login_status = False
            self.qr_status_result = {"status": "waiting", "message": "等待扫描..."}
        return result

    def start_qr_polling(self):
        """启动二维码状态轮询线程"""
        if not self.current_qr_uuid:
            return
        if self.qr_status_thread and self.qr_status_thread.is_alive():
            return
        
        uuid = self.current_qr_uuid

        def _poll():
            while qr_status_polling.get(uuid):
                result = self.booking.check_qr_status_once()
                self.qr_status_result = result
                
                if result.get("status") in ["success", "failed", "expired"]:
                    if result.get("status") == "success":
                        self.login_status = True
                        try:
                            self.booking.save_cookies()
                        except Exception:
                            pass
                    qr_status_polling.pop(uuid, None)
                    break
                
                time.sleep(2)

        self.qr_status_thread = threading.Thread(target=_poll, daemon=True)
        self.qr_status_thread.start()

def get_manager():
    """获取当前会话对应的管理器实例"""
    session_id = session.get('session_id')
    if not session_id:
        session_id = os.urandom(24).hex()
        session['session_id'] = session_id
    if session_id not in booking_instances:
        booking_instances[session_id] = BookingManager()
    return booking_instances[session_id]

@app.before_request
def load_user_session():
    """在每个请求前加载用户会话"""
    session_id = session.get('session_id')
    if session_id:
        manager = get_manager()
        manager.load_session(session_id)

@app.after_request
def save_user_session(response):
    """在每个请求后保存用户会话"""
    session_id = session.get('session_id')
    if session_id:
        manager = get_manager()
        if manager.login_status:
            manager.save_session(session_id)
    return response

@app.route('/')
def index():
    # 确保每个用户都有唯一的会话ID
    if 'session_id' not in session:
        session['session_id'] = os.urandom(24).hex()
    return render_template('index.html')

@app.route('/api/login/qrcode', methods=['POST'])
def get_qr_code():
    """获取登录二维码"""
    try:
        manager = get_manager()
        result = manager.get_qr_code()
        if result['success']:
            # 开始轮询状态
            qr_status_polling[result['uuid']] = True
            manager.start_qr_polling()
            return jsonify({
                'success': True,
                'uuid': result['uuid'],
                'qr_image': result.get('qr_image', '')
            })
        else:
            return jsonify({'success': False, 'message': result['message']})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/login/status/<uuid>', methods=['GET'])
def check_login_status(uuid):
    """检查登录状态"""
    try:
        manager = get_manager()
        if uuid != manager.current_qr_uuid:
            return jsonify({'success': False, 'message': '无效的UUID'})
            
        result = manager.qr_status_result
        if result:
            return jsonify({
                'success': True,
                'status': result['status'],
                'message': result['message'],
                'logged_in': manager.login_status
            })
        else:
            return jsonify({
                'success': True,
                'status': 'checking',
                'message': '正在检查登录状态...',
                'logged_in': False
            })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/stations/suggest', methods=['GET'])
def get_station_suggestions():
    """获取车站名称建议"""
    try:
        query = request.args.get('q', '').strip()
        if not query:
            return jsonify({'success': False, 'message': '请输入查询关键词'})
        
        manager = get_manager()
        suggestions = manager.booking.get_station_suggestions(query)
        return jsonify({
            'success': True,
            'suggestions': suggestions,
            'count': len(suggestions)
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/stations/list', methods=['GET'])
def get_stations_list():
    """获取完整的车站列表（包含编码）"""
    try:
        stations_data = []
        manager = get_manager()
        for name, code in manager.booking.mcp_service.station_cache.items():
            stations_data.append({
                'name': name,
                'code': code
            })
        return jsonify({
            'success': True,
            'stations': stations_data,
            'total': len(stations_data)
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/stations', methods=['GET'])
def get_stations():
    """获取车站列表"""
    try:
        manager = get_manager()
        stations = list(manager.booking.station_manager.stations.keys())
        return jsonify({
            'success': True,
            'stations': stations
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/tickets/query', methods=['POST'])
def query_tickets():
    """查询车票"""
    try:
        data = request.json
        from_station = data.get('from_station')
        to_station = data.get('to_station')
        date = data.get('date')
        
        if not all([from_station, to_station, date]):
            return jsonify({'success': False, 'message': '缺少必要参数'})
            
        manager = get_manager()
        if not manager.login_status:
            return jsonify({'success': False, 'message': '请先登录'})
            
        trains = manager.booking.query_ticket(from_station, to_station, date)
        if trains is None:
            return jsonify({'success': False, 'message': '查询失败'})
            
        # 返回车次信息
        tickets_data = []
        for train_no in trains:
            if train_no in manager.booking.ticket_info:
                info = manager.booking.ticket_info[train_no]
                tickets_data.append({
                    'train_no': train_no,
                    'secret': info.get('secret', ''),
                    'can_book': True,
                    'start_time': info.get('start_time', ''),
                    'arrive_time': info.get('arrive_time', ''),
                    'duration': info.get('duration', ''),
                    'ze_num': info.get('ze_num', '--'),
                    'zy_num': info.get('zy_num', '--'),
                    'swz_num': info.get('swz_num', '--')
                })
        
        return jsonify({
            'success': True,
            'trains': tickets_data
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/tickets/smart-query', methods=['POST'])
def smart_query_tickets():
    """智能查询车票 - 支持自然语言日期和筛选"""
    try:
        data = request.json
        from_station = data.get('from_station')
        to_station = data.get('to_station')
        date = data.get('date')
        train_types = data.get('train_types', '')  # 如 "G,D" 表示只查高铁和动车
        sort_by = data.get('sort_by', '')  # 如 "time" 按时间排序
        
        if not all([from_station, to_station, date]):
            return jsonify({'success': False, 'message': '缺少必要参数'})
            
        manager = get_manager()
        if not manager.login_status:
            return jsonify({'success': False, 'message': '请先登录'})
        
        # 使用MCP集成的智能查询
        tickets = manager.booking.smart_query_tickets(
            from_station, to_station, date, train_types, sort_by
        )
        
        return jsonify({
            'success': True,
            'tickets': tickets,
            'count': len(tickets)
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/tickets/batch-query', methods=['POST'])
def batch_query_tickets():
    """批量查询多个日期的车票"""
    try:
        data = request.json
        from_station = data.get('from_station')
        to_station = data.get('to_station')
        dates = data.get('dates', [])
        
        if not all([from_station, to_station, dates]):
            return jsonify({'success': False, 'message': '缺少必要参数'})
            
        manager = get_manager()
        if not manager.login_status:
            return jsonify({'success': False, 'message': '请先登录'})
        
        # 批量查询
        results = manager.booking.batch_query_tickets(from_station, to_station, dates)
        
        return jsonify({
            'success': True,
            'results': results
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/passengers', methods=['GET'])
def get_passengers():
    """获取乘客列表"""
    try:
        print("收到获取乘客列表请求")
        
        manager = get_manager()
        if not manager.login_status:
            print("用户未登录")
            return jsonify({'success': False, 'message': '请先登录'})
            
        print("正在调用get_passengers_direct方法...")
        passengers = manager.booking.get_passengers_direct()
        
        print(f"get_passengers_direct返回结果: {len(passengers) if passengers else 0} 位乘客")
        
        if not passengers:
            print("未获取到乘客数据")
            return jsonify({
                'success': False, 
                'message': '未找到联系人',
                'debug_info': '可能是登录状态失效或12306接口变更'
            })
            
        passenger_list = []
        for idx, p in enumerate(passengers):
            # 处理可能的字段名变化
            name = p.get('passenger_name') or p.get('name') or '未知姓名'
            id_no = p.get('passenger_id_no') or p.get('id_no') or '未知证件号'
            id_type = p.get('passenger_id_type_code') or p.get('id_type_code') or '1'
            mobile = p.get('mobile_no') or p.get('mobile') or ''
            
            passenger_list.append({
                'id': idx,
                'name': name,
                'id_no': id_no,
                'id_type': id_type,
                'mobile': mobile
            })
        
        print(f"成功处理 {len(passenger_list)} 位乘客信息")
        return jsonify({
            'success': True,
            'passengers': passenger_list,
            'count': len(passenger_list)
        })
    except Exception as e:
        print(f"获取乘客列表异常: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False, 
            'message': f'获取乘客失败: {str(e)}',
            'debug_info': '请检查网络连接和登录状态'
        })

@app.route('/api/booking/submit', methods=['POST'])
def submit_booking():
    """提交订单"""
    try:
        data = request.json
        from_station = data.get('from_station')
        to_station = data.get('to_station')
        date = data.get('date')
        train_no = data.get('train_no')
        passenger_ids = data.get('passenger_ids', [])
        seat_type = data.get('seat_type', 'O')
        
        if not all([from_station, to_station, date, train_no, passenger_ids]):
            return jsonify({'success': False, 'message': '缺少必要参数'})
            
        manager = get_manager()
        if not manager.login_status:
            return jsonify({'success': False, 'message': '请先登录'})
            
        # 获取乘客信息
        all_passengers = manager.booking.get_passengers_direct()
        selected_passengers = [all_passengers[i] for i in passenger_ids if i < len(all_passengers)]
        
        if not selected_passengers:
            return jsonify({'success': False, 'message': '未选择有效的乘客'})
            
        # 执行预订
        success = manager.booking.execute_booking(
            from_station, to_station, date, train_no, selected_passengers, seat_type
        )
        
        return jsonify({
            'success': success,
            'message': '下单成功，请立即打开12306 APP查看未完成订单并付款！' if success else '下单失败'
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/user/status', methods=['GET'])
def check_user_status():
    """检查用户登录状态"""
    try:
        manager = get_manager()
        is_logged_in = manager.login_status
        return jsonify({
            'success': True,
            'logged_in': is_logged_in
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
