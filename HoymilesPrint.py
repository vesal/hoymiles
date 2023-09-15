import datetime
from typing import Tuple, NewType, List
from decimal import Decimal
from PlantDefinition import *

from hoymiles_modbus2.client import HoymilesModbusTCP
from hoymiles_modbus2.datatypes import MicroinverterType

NUMBER_OF_PV_PANELS = len(glo_inverters)*4

Coord = NewType('Coord', Tuple[int, int])
Panels = NewType('GloPanels', List[List[Coord]])


def find_panel_pos(panels: Panels, inv_index: int, port: int) -> Coord:
    coord = (inv_index, port)
    for pr in range(0, len(panels)):
        for pc in range(0, len(panels[pr])):
            if panels[pr][pc] == coord:
                return Coord((pr, pc))
    return None


def print_powers(powers, file):
    for pr in range(0, len(powers)):
        file.write("     ")
        for pc in range(0, len(powers[pr])):
            if powers[pr][pc]!=None:
              file.write(f"{powers[pr][pc]:5.1f} ")
            else:
              file.write("      ")
        file.write("\n")


def print_temperatures(temperatures, file):
    file.write("      "+glo_print_temperatures_label)
    for d in temperatures:
        file.write(f"{d:5.1f}"+" °C")
    file.write("\n")


def print_status(plant_data, inverters, panels, file, min_print):
    microinverter_data = plant_data.microinverter_data

    powers: List[List[Decimal]] = []
    for ir in range(0, len(panels)):
        r: List[Decimal] = []
        for ic in range(0, len(panels[ir])):
            if panels[ir][ic]!=None:
              r.append(Decimal(0))
            else:
              r.append(None)
        powers.append(r)

    temps = []
    for i in range(0, len(inverters)):
        temps.append(0)

    sum_power = 0
    min_power_init = 100000
    min_power = min_power_init
    max_power = 0
    init_pos = '(-, -)'
    min_pos = init_pos
    max_pos = init_pos
    lost = 0

    d = datetime.datetime.now()
    print("Haku: " + str(d.strftime("%Y-%m-%d %H:%M:%S")) +"\n")
    for microinverter in microinverter_data:
        if not microinverter.link_status:
            print("ERROR: " + str(d.strftime("%Y-%m-%d %H:%M:%S")) + " " + str(microinverter.serial_number) + " " + str(microinverter.port_number) + " " + str(microinverter.pv_power) +"\n")
        if microinverter.link_status or True:
            # print(microinverter.serial_number,microinverter.port_number, microinverter.pv_power)
            ser = microinverter.serial_number
            port = microinverter.port_number
            inv_index = inverters.index(ser)

            if port == 1:
                temps[inv_index] = microinverter.temperature

            w = microinverter.pv_power
            pos = find_panel_pos(panels, inv_index, port)
            if pos!=None:
              pr: int = pos[0]
              pc: int = pos[1]
              powers[pr][pc] = w
              sum_power += w
              if w < min_power:
                  min_power = w
                  min_pos = pos
              if w > max_power:
                  max_power = w
                  max_pos = pos

              lost = 0
              for pr in range(0, len(powers)):
                  for pc in range(0, len(powers[pr])):
                      if powers[pr][pc]!=None:
                        lost += (max_power - powers[pr][pc])

    d = datetime.datetime.now()
    if not min_print:
        file.write(f"     {plant_data.today_production / 1000:7.3f} kWh "+glo_today_label+"\n")
        file.write(f"     {plant_data.total_production / 1000:7.3f} kWh "+glo_total_label+"\n")
        print_powers(powers, file)
        if min_power == min_power_init:
            min_power = 0
        lostp = ""
        if sum_power > 0:
            lostp = f"{100 * lost / sum_power:3.1f}%"
        file.write("    " + str(d.strftime("%Y-%m-%d %H:%M:%S")) +
                   f"{sum_power / 1000:5.2f} kW, {min_power:5.1f} W - {max_power:5.1f} W" +
                   str(min_pos) + "-" + str(max_pos) + " " + str(lost) + " W" + " " + lostp + "\n")
        print_temperatures(temps, file)
    else:
        if min_power < min_power_init and max_pos != init_pos:
            file.write(str(d.strftime("%Y-%m-%d %H:%M:%S")) + " " +
                       f";{sum_power / 1000:5.2f};{min_power:5.1f};{max_power:5.1f};" +
                       " " + str(min_pos) + " ; " + str(max_pos) + " " +
                       f";{plant_data.today_production / 1000:9.3f};{lost:6.1f};{min(temps):6.1f};{max(temps):6.1f}"
                       + "\n")

def get_power(plant_data):
    microinverter_data = plant_data.microinverter_data
    sum_power = 0
    for microinverter in microinverter_data:
        if microinverter.link_status or True:
            w = microinverter.pv_power
            sum_power += w
    return sum_power

# noinspection PyBroadException
def get_plant_data():
    #try:
        hoy_tcp = HoymilesModbusTCP(DTU_IP,
                                    microinverter_type=MicroinverterType.HM,
                                    number_of_pv_panels=NUMBER_OF_PV_PANELS)
        # Seuraava on se joka vie aikaa
        plant_data = hoy_tcp.plant_data
        return plant_data
    #except:
    #    return None


def append_to_file(plant_data):
    print_status(plant_data, glo_inverters, glo_panels, open(glo_status_destination_file, 'a'), True)
