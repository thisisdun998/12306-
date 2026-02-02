import re
import json
import os
import requests

class StationManager:
    def __init__(self, station_file='stations.json'):
        self.station_file = station_file
        self.stations = {} # name -> code
        self.load_stations()

    def download_stations(self):
        url = "https://kyfw.12306.cn/otn/resources/js/framework/station_name.js"
        try:
            print("正在下载最新车站信息...")
            resp = requests.get(url)
            resp.encoding = 'utf-8'
            content = resp.text
            # content format: var station_names ='@bjb|北京北|VAP|beijingbei|bjb|0|0357|北京|||...'
            # remove "var station_names ='" and last "'"
            start_index = content.find("'") + 1
            end_index = content.rfind("'")
            data = content[start_index:end_index]
            
            parts = data.split('@')
            station_dict = {}
            for part in parts:
                if not part:
                    continue
                fields = part.split('|')
                if len(fields) > 2:
                    name = fields[1]
                    code = fields[2]
                    station_dict[name] = code
            
            self.stations = station_dict
            with open(self.station_file, 'w', encoding='utf-8') as f:
                json.dump(self.stations, f, ensure_ascii=False, indent=2)
            print(f"车站信息已更新，共 {len(self.stations)} 个车站")
            
        except Exception as e:
            print(f"下载车站信息失败: {e}")

    def load_stations(self):
        if os.path.exists(self.station_file):
            try:
                with open(self.station_file, 'r', encoding='utf-8') as f:
                    self.stations = json.load(f)
            except Exception:
                self.download_stations()
        else:
            self.download_stations()

    def get_code(self, name):
        return self.stations.get(name)

    def get_name(self, code):
        for name, c in self.stations.items():
            if c == code:
                return name
        return None

if __name__ == "__main__":
    sm = StationManager()
    print(f"杭州的代码: {sm.get_code('杭州')}")
    print(f"武汉的代码: {sm.get_code('武汉')}")
