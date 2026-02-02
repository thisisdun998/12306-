import time
import base64
import io
from PIL import Image
from curl_cffi import requests

class Tiantiel12306Login:
    def __init__(self):
        # 初始化一个 Session，它会自动维持 Cookie (这是核心)
        self.session = requests.Session()
        
        # 伪装成 Chrome 浏览器
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://kyfw.12306.cn/",
            "Origin": "https://kyfw.12306.cn"
        }
        self.uuid = ""

    def get_qr_code(self):
        """步骤 1: 获取登录二维码"""
        url = "https://kyfw.12306.cn/passport/web/create-qr64"
        data = {
            "appid": "otn"
        }
        
        print("正在获取二维码...")
        try:
            # 使用 impersonate="chrome120" 模拟浏览器指纹
            resp = self.session.post(url, data=data, headers=self.headers, impersonate="chrome120")
            resp_json = resp.json()
            
            if resp_json.get("result_code") == "0":
                self.uuid = resp_json.get("uuid")
                image_b64 = resp_json.get("image")
                print(f"二维码获取成功! UUID: {self.uuid}")
                self._show_image(image_b64)
                return True
            else:
                print(f"获取二维码失败: {resp_json}")
                return False
                
        except Exception as e:
            print(f"请求异常: {e}")
            return False

    def _show_image(self, base64_str):
        """辅助方法: 解码并显示 Base64 图片"""
        try:
            image_data = base64.b64decode(base64_str)
            image = Image.open(io.BytesIO(image_data))
            print("请用手机 12306 APP 扫描弹出的二维码...")
            image.show() # 这会在你电脑上弹出一个图片窗口
        except Exception as e:
            print("图片显示失败，请检查是否安装了 Pillow 库")

    def check_qr_status(self):
        """步骤 2: 轮询二维码状态"""
        url = "https://kyfw.12306.cn/passport/web/checkqr"
        data = {
            "uuid": self.uuid,
            "appid": "otn"
        }

        while True:
            try:
                resp = self.session.post(url, data=data, headers=self.headers, impersonate="chrome120")
                resp_json = resp.json()
                
                code = resp_json.get("result_code")
                
                if code == "0":
                    print("等待扫描...", end="\r")
                elif code == "1":
                    print("已扫描，请在手机上点击确认...", end="\r")
                elif code == "2":
                    print("\n登录成功！")
                    # 打印一下当前的 Cookies，确认我们拿到了凭证
                    print("当前 Session Cookies:", self.session.cookies.get_dict())
                    return True # 退出循环，登录完成
                elif code == "3":
                    print("\n二维码已过期，请重新运行程序。")
                    return False
                else:
                    print(f"\n未知状态: {resp_json}")
                
                time.sleep(2) # 间隔 2 秒轮询一次，避免请求过快
                
            except Exception as e:
                print(f"\n轮询异常: {e}")
                time.sleep(2)

    def run(self):
        if self.get_qr_code():
            return self.check_qr_status()
        return False

if __name__ == "__main__":
    bot = Tiantiel12306Login()
    bot.run()