import datetime
from typing import Tuple, NewType, List
from decimal import Decimal

from hoymiles_modbus2.client import HoymilesModbusTCP
from hoymiles_modbus2.datatypes import MicroinverterType

glo_inverters = ['116484414833', '116484414805', '116484414779', '116484414773', '116484414694']
glo_panels = [
    [(0, 3), (0, 4), (1, 3), (1, 4)],
    [(0, 1), (0, 2), (1, 1), (1, 2)],
    [(2, 3), (2, 4), (3, 3), (3, 4)],
    [(2, 1), (2, 2), (3, 1), (3, 2)],
    [(4, 1), (4, 2), (4, 3), (4, 4)],
]

NUMBER_OF_PV_PANALES = 20

Coord = NewType('Coord', Tuple[int, int])
Panels = NewType('GloPanels', List[List[Coord]])


def find_panel_pos(panels: Panels, inv_index: int, port: int) -> Coord:
    coord = (inv_index, port)
    for pr in range(0, 5):
        for pc in range(0, 4):
            if panels[pr][pc] == coord:
                return Coord((pr, pc))
    return Coord((-1, -1))


def tulosta(tuotot, file):
    for pr in range(0, len(tuotot)):
        file.write("     ")
        for pc in range(0, len(tuotot[0])):
            file.write(f"{tuotot[pr][pc]:5.1f} ")
        file.write("\n")


def tulosta_temps(tmps, file):
    file.write("     ")
    for d in tmps:
        file.write(f"{d:5.1f}")
    file.write("\n")


def print_status(plant_data, inverters, panels, file, min_print):
    microinverter_data = plant_data.microinverter_data

    tuotot: List[List[Decimal]] = []
    for ir in range(0, len(panels)):
        r: List[Decimal] = []
        for ic in range(0, len(panels[0])):
            r.append(Decimal(0))
        tuotot.append(r)

    temps = []
    for i in range(0, len(inverters)):
        temps.append(0)

    summa_w = 0
    min_w_init = 100000
    min_w = min_w_init
    max_w = 0
    init_pos = '(-, -)'
    min_pos = init_pos
    max_pos = init_pos
    lost = 0

    for microinverter in microinverter_data:
        if microinverter.link_status or True:
            # print(microinverter.serial_number,microinverter.port_number, microinverter.pv_power)
            ser = microinverter.serial_number
            port = microinverter.port_number
            inv_index = inverters.index(ser)

            if port == 1:
                temps[inv_index] = microinverter.temperature

            w = microinverter.pv_power
            pos = find_panel_pos(panels, inv_index, port)
            pr: int = pos[0]
            pc: int = pos[1]
            tuotot[pr][pc] = w
            summa_w += w
            if w < min_w:
                min_w = w
                min_pos = pos
            if w > max_w:
                max_w = w
                max_pos = pos

            lost = 0
            for pr in range(0, len(tuotot)):
                for pc in range(0, len(tuotot[0])):
                    lost += (max_w - tuotot[pr][pc])

    d = datetime.datetime.now()
    if not min_print:
        file.write(f"     {plant_data.today_production / 1000:7.3f} kWh tänään\n")
        file.write(f"     {plant_data.total_production / 1000:7.3f} kWh yhteensä\n")
        tulosta(tuotot, file)
        if min_w == min_w_init:
            min_w = 0
        lostp = ""
        if summa_w > 0:
            lostp = f"{100 * lost / summa_w:3.1f}%"
        file.write("    " + str(d.strftime("%Y-%m-%d %H:%M:%S")) +
                   f"{summa_w / 1000:5.2f} kW, {min_w:5.1f} W - {max_w:5.1f} W" +
                   str(min_pos) + "-" + str(max_pos) + " " + str(lost) + " W" + " " + lostp + "\n")
        tulosta_temps(temps, file)
    else:
        if min_w < min_w_init and max_pos != init_pos:
            file.write(str(d.strftime("%Y-%m-%d %H:%M:%S")) + " " +
                       f";{summa_w / 1000:5.2f};{min_w:5.1f};{max_w:5.1f};" +
                       " " + str(min_pos) + " ; " + str(max_pos) + " " +
                       f";{plant_data.today_production / 1000:9.3f};{lost:6.1f};{min(temps):6.1f};{max(temps):6.1f}"
                       + "\n")

def get_power(plant_data):
    microinverter_data = plant_data.microinverter_data
    summa_w = 0
    for microinverter in microinverter_data:
        if microinverter.link_status or True:
            w = microinverter.pv_power
            summa_w += w
    return summa_w

# noinspection PyBroadException
def get_plant_data():
    #try:
        hoy_tcp = HoymilesModbusTCP('192.168.59.98',
                                    microinverter_type=MicroinverterType.HM,
                                    number_of_pv_panels=NUMBER_OF_PV_PANALES)
        # Seuraava on se joka vie aikaa
        plant_data = hoy_tcp.plant_data
        return plant_data
    #except:
    #    return None


def append_to_file(plant_data):
    print_status(plant_data, glo_inverters, glo_panels, open('aurinko.txt', 'a'), True)
