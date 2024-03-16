import sys
import datetime
import json
import threading
# from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.server import BaseHTTPRequestHandler, HTTPServer
import requests
from HoymilesPrint import get_plant_data, append_to_file, get_power, print_status, glo_inverters, glo_panels
from HoymilesToJson import get_panels_json, get_panels_png
from hoymiles_modbus2.datatypes import PlantData
from typing import Union
from io import BytesIO

server_port = 8001
kwhmeter_url = "http://192.168.59.68:2222/REF"


def get_next_update_time():
    # Lasketaan seuraava tasaminuutti
    now = datetime.datetime.now()
    next_minute = (now.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1))
    # minutes = next_minute.minute
    # if minutes in [0, 15, 30, 45]:  # jätetään väliin vartit
    #    next_minute = next_minute + datetime.timedelta(minutes=1)

    # Asetetaan ajastin seuraavalle tasaminuutille
    delay = (next_minute - now).total_seconds()
    print(datetime.datetime.now().time(), "next: ", delay)
    return delay, next_minute


last_plant_data: Union[PlantData, None] = None
last_update_time: datetime = datetime.datetime.now()


def get_hoymiles_data():
    global last_plant_data
    global last_update_time

    delay, update_time = get_next_update_time()
    threading.Timer(delay, get_hoymiles_data).start()

    try:
        print(datetime.datetime.now().time(), "start")
        new_plant_data = get_plant_data()
        print(datetime.datetime.now().time(), "end")
        if not new_plant_data:
            print("no new plant data")
            return
        # print(datetime.datetime.now().time(), "haku")
        print_status(new_plant_data, glo_inverters, glo_panels, sys.stdout, True)
        # append_to_file(new_plant_data)
    except Exception as err:
        print("Exception: ", datetime.datetime.now().time(), err)
        return

    summa_w = 0
    if new_plant_data.pv_power == 0:
        summa_w = get_power(new_plant_data)
        new_plant_data.pv_power = summa_w
    print(last_update_time, "->", datetime.datetime.now().time(), ":", new_plant_data.pv_power, "W", summa_w, "W")

    if last_update_time and (last_update_time.minute-1) % 5 == 0:
        append_to_file(new_plant_data)

    last_plant_data = new_plant_data
    last_update_time = update_time


def handle_hoymiles():
    if not last_plant_data:
        return {'pvPower': 0,
                'last_plant_data': None,
                'pvEnergyTotal': None,
                'pvEnergyToday': None
                }
    total = float(last_plant_data.total_production)
    today = float(last_plant_data.today_production)
    if total < 6428000: # prevent mornig problem
        total = None
    if today == 0:
        today = None
    return {'pvPower': float(last_plant_data.pv_power),
            'pvEnergyTotal': total,
            'pvEnergyToday': today
            }


def handle_kwh_meter():
    response = requests.get(kwhmeter_url)
    if response.status_code != 200:
        print("kwhmeter code: ", response.status_code)
        return {'message': 'error'}
    text = response.text
    sts = text.split(";")
    return {
        'mainkW': float(sts[0]),
        'mainkWh': float(sts[2]),
        'geokW': float(sts[3]),
        'geokWh': float(sts[5])
    }



class MyHandler(BaseHTTPRequestHandler):
    def get_png(self, t):
        self.send_response(200)
        self.send_header("Content-type", "image/png")
        self.end_headers()
        image = get_panels_png(last_plant_data, t)
        output = BytesIO()
        image.save(output, format="PNG")
        self.wfile.write(output.getvalue())
        return t

    def do_GET(self):
        if self.path == "/GetPanelPng":
            return self.get_png(1);
        if self.path == "/GetPanelPng2":
            return self.get_png(2);
        if self.path == "/GetPanelPng3":
            return self.get_png(3);
        if self.path == "/favicon.ico":
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        if self.path == "/pannari":
            data = handle_kwh_meter()
        elif self.path == "/hoymiles":
            data = handle_hoymiles()
        elif self.path == "/all":
            data1 = handle_hoymiles()
            data2 = handle_kwh_meter()
            data = {**data1, **data2}
        elif self.path == "/GetPanelData":
            data = get_panels_json(last_plant_data)
        else:
            data = {
                'message': 'Tuntematon kutsu?'
            }
        json_data = json.dumps(data)
        self.wfile.write(json_data.encode('utf-8'))
        print(data)


# def run(server_class=ThreadingHTTPServer, handler_class=MyHandler, port=server_port):
def run(server_class=HTTPServer, handler_class=MyHandler, port=server_port):
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    print('Serving at port', port)
    get_hoymiles_data()
    # threading.Timer(get_next_update_time()[0], get_hoymiles_data).start()
    httpd.serve_forever()


run()
