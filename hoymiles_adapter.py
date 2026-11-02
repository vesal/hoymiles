from enum import Enum
from decimal import Decimal

from hoymiles_modbus3.client import HoymilesModbusTCP as NewHoymilesModbusTCP
from hoymiles_modbus3.datatypes import PlantData


class MicroinverterType(Enum):
    MI = 1
    HM = 2


class PlantDataAdapter:
    def __init__(self, data):
        self._data = data
        self.inverters = data.inverters

        # Lasketaan kaikki invertterit mukaan link_status-arvosta riippumatta.
        self.pv_power = sum(
            (i.pv_power for i in self.inverters), Decimal(0)
        )
        self.today_production = sum(
            i.today_production for i in self.inverters
        )
        self.total_production = sum(
            i.total_production for i in self.inverters
        )
        self.alarm_flag = any(
            i.alarm_code for i in self.inverters
        )

    @property
    def microinverter_data(self):
        return self.inverters

    def __getattr__(self, name):
        return getattr(self._data, name)


class HoymilesModbusTCP:
    def __init__(
        self,
        host,
        port=502,
        microinverter_type=None,
        unit_id=1,
        number_of_pv_panels=None
    ):
        self._client = NewHoymilesModbusTCP(host, port, unit_id)

    @property
    def plant_data(self):
        return PlantDataAdapter(self._client.plant_data)
