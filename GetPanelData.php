<?php
$command = escapeshellcmd('C:\Databases\ElectricConsumption\Code\Production\HoymilesToJson.py');
$output = shell_exec($command);
echo $output;
?>