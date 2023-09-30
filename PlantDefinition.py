# declare your DTU IP
# DTU_IP = '192.168.40.130'
DTU_IP = '192.168.59.158'

# declare list of serial numbers of inverters connected to your DTU
# glo_inverters = ['116484414795', '116484415551', '116484415768', '116484416422']
glo_inverters = ['116484414833', '116484414805', '116484414779', '116484414773', '116484414694']

# declare your plant panel layout. For each position declare pair of (<inverter_index>,<inverter_port>)
#   inverter_index is 0 based index of inverter listed on glo_inverters
#   inverter_port is number of MPPT port, where panel is connected.
# If you have initialized Hoymiles cloud plant layout, you can read inverterter serialnumbers
# and ports from layout picture.

# glo_panels = [
#     [(0, 4), (0, 2), (1, 4), (1, 3), (1, 2), None,   (1, 1), (2, 4), (2, 3), (2, 2), (2, 1), (3, 2)],
#     [(0, 3), (0, 1), None,   None,   None,   None,   None,   None,   None,   (3, 4), (3, 3), (3, 1)],
# ]

glo_panels = [
    [(0, 3), (0, 4), (1, 3), (1, 4)],
    [(0, 1), (0, 2), (1, 1), (1, 2)],
    [(2, 3), (2, 4), (3, 3), (3, 4)],
    [(2, 1), (2, 2), (3, 1), (3, 2)],
    [(4, 1), (4, 2), (4, 3), (4, 4)],
]

glo_panel_powers = 505

# declare status destination file used by append_to_file
glo_status_destination_file='aurinko.txt'

# Some language dependent strings for status printing.
glo_print_temperatures_label="Lämpötilat:"
glo_today_label="tänään"
glo_total_label="yhteensä"