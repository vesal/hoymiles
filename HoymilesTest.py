import sys
import time

from HoymilesPrint import get_plant_data, print_status, glo_inverters, glo_panels

min_print = False
if len(sys.argv) > 1 and sys.argv[1] == "min":
    min_print = True

st = time.time()
print_status(get_plant_data(), glo_inverters, glo_panels, sys.stdout, min_print)

# print('Execution time:', time.time() - st, 'seconds')