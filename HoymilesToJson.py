from typing import Tuple, NewType, List
from decimal import Decimal
from PlantDefinition import *

from hoymiles_modbus2.client import HoymilesModbusTCP
from hoymiles_modbus2.datatypes import MicroinverterType
from PIL import Image, ImageDraw

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


def get_panels_json():
    try:
        panel_max_powers = glo_panel_powers
    except NameError:
        panel_max_powers = None

    # print(panel_max_powers)

    result_json = hoymiles_to_json(get_plant_data(), glo_inverters, glo_panels, panel_max_powers)
    # add_temperatures([1,2,3])
    # print(json.dumps(result_json, indent=4))
    return result_json


def get_panels_png():
    json = get_panels_json()
    width, height = 600, 600
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.text((10, 10), "Hello, PNG!", fill="black")
    return image
