cd ~/aurinko
gnome-terminal -- bash -c 'python3.10 hoyserver2.py; exec bash'
sleep 5
modprobe vboxdrv
VBoxManage startvm "ha"
gnome-terminal -- bash -c 'py wdog.py; exec bash'
