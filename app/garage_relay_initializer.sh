#!/usr/bin/env/ bash
# /etc/init.d/garage_relay_initializer.sh
#
# This is more or less a direct copy-paste from the instructables that I
# followed to get this working. The pins default to turning on at startup
# which can open the grage door if the pi restarts in the middle of the night
# or something. Not good. So this script runs at startup to ensure the garage
# door mode is set to not do that.
# [link](https://www.instructables.com/Raspberry-Pi-Garage-Door-Opener/)
#
# When this is downloaded onto the target raspberry pi, add it to this
# location via a symlink: `/etc/init.d/garage_relay_initializer.sh` so that
# any updates to this repo will flow into there upon pull from master.
#
# Additionally you will want to run:
# $ sudo chmod 777 /etc/init.d/garage_relay_initializer.sh
# $ sudo update-rc.d -f garage_relay_initializer.sh start 4
# to ensure that the script runs at boot time.

# Carry out specific functions when asked to by the system
case "$1" in
    start)
        echo "Starting Relay"
        # Turn pin 14 on which keeps relay off
        /usr/local/bin/gpio write 14 1
        # Start Gpio
        /usr/local/bin/gpio mode 14 out
        ;;
    stop)
        echo "Stopping gpio"
        ;;
    *)
        echo "Usage: /etc/init.d/garage_relay_initializer.sh {start|stop}"
        exit 1
        ;;
esac

exit 0
