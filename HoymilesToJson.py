from typing import Tuple, NewType, List
from decimal import Decimal
from PlantDefinition import *

from hoymiles_modbus2.client import HoymilesModbusTCP
from hoymiles_modbus2.datatypes import MicroinverterType
from PIL import Image, ImageDraw, ImageFont

NUMBER_OF_PV_PANELS = len(glo_inverters) * 4

Coord = NewType('Coord', Tuple[int, int])
Panels = NewType('GloPanels', List[List[Coord]])


# *****************************************************************************
def find_panel_pos(panels: Panels, inv_index: int, port: int) -> Coord:
    coord = (inv_index, port)
    for pr in range(0, len(panels)):
        for pc in range(0, len(panels[pr])):
            if panels[pr][pc] == coord:
                return Coord((pr, pc))
    return None


# *****************************************************************************
def add_powers(powers, result_json):
    result_json["PanelsData"] = []
    for pr in range(0, len(powers)):
        for pc in range(0, len(powers[pr])):
            if powers[pr][pc] is not None:
                panel_data = {"Power": float(powers[pr][pc]['Power'])}
                if 'MaxPower' in powers[pr][pc]:
                    panel_data["MaxPower"] = float(powers[pr][pc]['MaxPower'])
                location = {'x': pc, 'y': pr}
                panel_data["Location"] = location
                result_json["PanelsData"].append(panel_data)
    return result_json


# *****************************************************************************
def hoymiles_to_json(plant_data, inverters, panels, panel_max_powers=None):
    result_json = {"Power": 0}
    if panel_max_powers is not None:
        result_json["MaxPower"] = 0
    result_json["EnergyToday"] = 0
    result_json["EnergyTotal"] = 0
    result_json["PanelsMax"] = 0
    result_json["PanelsMin"] = 0
    result_json["PanelsData"] = []

    panel_def_power = None
    if panel_max_powers is not None:
        if type(panel_max_powers).__name__ != 'list':
            panel_def_power = panel_max_powers

    microinverter_data = plant_data.microinverter_data

    powers: List[List[Decimal]] = []
    for ir in range(0, len(panels)):
        r: List[Decimal] = []
        for ic in range(0, len(panels[ir])):
            if panels[ir][ic] is not None:
                power_info = {'Power': Decimal(0)}
                r.append(power_info)
            else:
                r.append(None)
        powers.append(r)

    result_json['Temperatures'] = []
    for i in range(0, len(inverters)):
        result_json['Temperatures'].append(0)

    sum_power = 0
    max_power = 0
    panels_max = 0
    panels_min = 1e10

    for microinverter in microinverter_data:
        if microinverter.link_status or True:
            # print(microinverter.serial_number,microinverter.port_number, microinverter.pv_power)
            ser = microinverter.serial_number
            port = microinverter.port_number
            inv_index = inverters.index(ser)

            if port == 1:
                result_json['Temperatures'][inv_index] = float(microinverter.temperature)

            w = microinverter.pv_power
            pos = find_panel_pos(panels, inv_index, port)
            if pos is not None:
                pr: int = pos[0]
                pc: int = pos[1]
                powers[pr][pc]['Power'] = w
                sum_power += w
                panels_max = max(panels_max, float(w))
                panels_min = min(panels_min, float(w))
                if panel_max_powers is not None:
                    mp = panel_def_power
                    if mp is None:
                        mp = panel_max_powers[pr][pc]
                    powers[pr][pc]['MaxPower'] = mp
                    max_power += mp

    # d = datetime.datetime.now()
    result_json["Power"] = float(sum_power)
    if max_power > 0:
        result_json["MaxPower"] = float(max_power)
    result_json["EnergyToday"] = plant_data.today_production
    result_json["EnergyTotal"] = plant_data.total_production
    result_json["PanelsMax"] = panels_max
    result_json["PanelsMin"] = panels_min
    return add_powers(powers, result_json)


# *****************************************************************************
# noinspection PyBroadException
def get_plant_data():
    # try:
    hoy_tcp = HoymilesModbusTCP(DTU_IP,
                                microinverter_type=MicroinverterType.HM,
                                number_of_pv_panels=NUMBER_OF_PV_PANELS)
    # Seuraava on se joka vie aikaa
    plant_data = hoy_tcp.plant_data
    return plant_data


# except:
#    return None


def get_panels_json(plant_data):
    try:
        panel_max_powers = glo_panel_powers
    except NameError:
        panel_max_powers = None

    # print(panel_max_powers)
    if not plant_data:
        plant_data = get_plant_data()

    result_json = hoymiles_to_json(plant_data, glo_inverters, glo_panels, panel_max_powers)
    # add_temperatures([1,2,3])
    # print(json.dumps(result_json, indent=4))
    return result_json


def draw_panel_by_json(draw, panel, font, t, panels_max):
    panel_width = 120
    panel_height = 60
    panel_x_cap = 5
    panel_y_cap = 2
    panel_power = (panel["Power"] or 0)  # + 200
    panel_pros = panel_power / panel["MaxPower"]
    x = panel["Location"]["x"] * (panel_width + panel_x_cap) + 10
    y = panel["Location"]["y"] * (panel_height + panel_y_cap) + 10
    draw.rectangle((x, y, x + panel_width, y + panel_height), fill=(0, 0, 0))
    if t == 1:
        draw.rectangle((x, y, x + panel_width * panel_pros, y + panel_height), fill=(0, 0, 255))
    if t == 2:
        c = int(panel_pros * 255)
        draw.rectangle((x, y, x + panel_width, y + panel_height), fill=(0, 0, c))
    if t == 3:
        c = int(panel_power / panels_max * 255)
        draw.rectangle((x, y, x + panel_width, y + panel_height), fill=(0, 0, c))

    draw.text((x+10, y+20), str(panel_power) + " W", font=font, fill=(255, 255, 255))


def get_panels_png(plant_data, t):
    json = get_panels_json(plant_data)
    # noinspection PyBroadException
    try:
        font = ImageFont.truetype("arialbd.ttf", 16)
    except:
        font = ImageFont.load_default()
    width, height = 600, 400
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    panels_max = float(json['PanelsMax'])
    for panel in json['PanelsData']:
        draw_panel_by_json(draw, panel, font, t, panels_max)

    x = 10
    y = height - 40
    power = json['Power']
    n = len(json["PanelsData"])
    abs_max = n * float(json['PanelsMax'])

    s = str(power) + " W. " + str(json['PanelsMin']) + \
        " - " + str(json['PanelsMax']) + " W" + \
        " " + str(abs_max) + " W " + str(int(power/abs_max*100)) + "%"

    draw.text((x, y), s , font=font, fill=(0,0,0))

    return image
