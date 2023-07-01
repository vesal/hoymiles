import json
from http.server import BaseHTTPRequestHandler, HTTPServer
import requests

port=8000
kwhmeter_url = "http://192.168.59.68:2222/REF"

def handle_kwh_meter():
    response = requests.get(kwhmeter_url)
    if response.status_code != 200:
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
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        if self.path=="/pannari":
            data = handle_kwh_meter()
        else:
            data = {
                'message': 'hoikka'
            }
        json_data = json.dumps(data)
        self.wfile.write(json_data.encode('utf-8'))

def run(server_class=HTTPServer, handler_class=MyHandler, port=port):
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    print('Serving at port', port)
    httpd.serve_forever()

run()