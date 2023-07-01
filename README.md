# hoymiles
Hoymiles invertterien seuranta

See: <https://github.com/wasilukm/hoymiles_modbus/blob/main/README.md>

Some changes made to test different different registers.  So not yet asked to merge before working 100% sure.

- aurinko.cmd - skript that is run by windows schelude program every xx:01 time
- HoymilesPrint.py - main code to do allmost all the stuff. Change panels and invreters if needed
- hoymiles_modbus2 - directory where is to modified wasilukm's code
- hoyserevr2.py - made for own use to be called from Home Assistant.  Run this insted of aurinko.cmd when
  used by HA.  It call's the same print to make the log.file.


