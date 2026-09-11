"""
Description
-----------
Run a scheduled alarm clock with red/green signaling "stay in bed" (red)
or "it is okay to get up!" (green) to your kid! It comes with the ability to
add audio `.wav` files to a specific directory that it can read and play at
random on the green schedule going live for the first time that day, assuming
that the green schedule has the audio play enabled and that there are audio
files to play.

The required wiring on a Raspberry Pi Zero is:

Pinout
------

   3V3  (1) (2)  5V    
 GPIO2  (3) (4)  5V    
 GPIO3  (5) (6)  GND   
 GPIO4  (7) (8)  GPIO14
   GND  (9) (10) GPIO15
GPIO17 (11) (12) GPIO18
GPIO27 (13) (14) GND   
GPIO22 (15) (16) GPIO23
   3V3 (17) (18) GPIO24
GPIO10 (19) (20) GND   
 GPIO9 (21) (22) GPIO25
GPIO11 (23) (24) GPIO8 
   GND (25) (26) GPIO7 
 GPIO0 (27) (28) GPIO1 
 GPIO5 (29) (30) GND   
 GPIO6 (31) (32) GPIO12
GPIO13 (33) (34) GND   
GPIO19 (35) (36) GPIO16
GPIO26 (37) (38) GPIO20
   GND (39) (40) GPIO21


(Callouts use the pin position, not GPIO ID #'s)

Lights
------
Red Light Power   = (5)
Green Light Power = (3)
Light Ground      = (9)

Speaker (I2S and ESP32)
-----------------------
G   = (6)
V   = (2) 
BCL = (12)
LRC = (35)
DIN = (40)

Config
------

Then the sistering config file pointed to by CONFIG_PATH should be set up
similar to the example here. You can see there are overrides shown in order of precedence:

- the highest priority of an ISO date specific override (example shown is Labor Day 2026)
- specific day of week overrides 
  - output from `date +%A` in the machine's locale, but not shown in the example
- weekday overrides in general
- weekend override
- the default fallback (if no other rules match)

Service Definition
------------------
The service definition is set up in the led_schedule.service file.

place that file at:

`/etc/systemd/system/led_schedule.service`

then run these commands to enable and start the service and to ensure it starts up on reboot:

```sh
sudo systemctl daemon-reload
sudo systemctl enable led_schedule.service
sudo systemctl start led_schedule.service
```

Config Schema
-------------
Here is the configuration schema. Anything "Optional" can be omitted:

{
    # Overrides to turn off features
    "kill_switches": {
        # Disables audio and lights
        "disable_all": Optional[bool] (default False),

        # Disables lights
        "disable_lights": Optional[bool] (default False),

        # Disables audio
        "disable_audio": Optional[bool] (default False),
    },
    
    # Timezone to evaluate the schedules against
    "timezone": str | Enum[timezone] | (example: "America/Chicago"),
    
    # Setting up the audio
    "audio": {
        # Where the .wav files are stored with recordings to play on audio trigger
        "audio_dir": Optional[str] | (default "/home/pi/sounds"),
    },

    # In-app state tracking, do not manually set, these will change
    "state": {
        # The previously played audio file to prevent duplicates (if only 1 present, it will be replayed)
        "last_played_file": Optional[str] (default ""),

        # The last triggered alarm to prevent re-triggering the same alarm that just fired
        "last_triggered_slot": Optional[str] (default "")
    },

    # The schedules to trigger. Each entry contain at least 1 "Schedule". There are 3 allowed entries/
    # Options
    # -------
    # - "default"
    # - "weekends"
    # - "weekdays"
    "schedules": {
        # The default schedules to consider if weekends or weekdays are not specified
        "default": Optional[List[Schedule]],

        # The schedules to consider on Saturday or Sunday
        "weekends": Optional[List[Schedule]],

        # The schedules to consider from Monday through Friday
        "weekdays": Optional[List[Schedule]],
    },

    # An optional date-keyed schedule that has overrides for specific calendar
    # days. The keys need to be in ISO date format without the time component.
    # An example is shown below:
    "date_overrides": {
    
        # An override schedule for Labor Day (US Holiday) in 2026
        "2026-09-07": List[Schedule],
    },
}

`Schedule` schema

Schedule = {
    "name": str,
    "start": str | format("HH:MM") 24 hour format,
    "end": str | format("HH:MM") 24 hour format (needs to be after start),
    "play_audio": bool
}

"""
import os
import time
import json
import random
import subprocess
from glob import glob
from datetime import datetime
from zoneinfo import ZoneInfo
from gpiozero import LED

# Initialize LEDs on GPIO 2 (green) and GPIO 3 (red)
green_led = LED(2)
red_led = LED(3)

CONFIG_PATH = "/home/pi/schedule.json"
DEFAULT_AUDIO_DIR = "/hom/pi/sounds"


def load_config():
    """Reads config from disk to dynamically apply settings changes."""
    try:
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error reading config: {e}")
        return None


def save_config(config):
    """Writes updated state/config safely to disk."""
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"Error saving config: {e}")


def play_random_wav(config):
    """Selects a random WAV file (different from last time) and plays it via aplay."""
    if config["kill_switches"].get("disable_audio", False):
        print("Audio suppressed by global kill switch.")
        return

    audio_dir = config["audio"].get("audio_dir", DEFAULT_AUDIO_DIR)
    wav_files = glob(os.path.join(audio_dir, "*.wav"))

    if not wav_files:
        print(f"No .wav files found in directory: {audio_dir}")
        return

    last_played = config["state"].get("last_played_file", "")
    candidates = [f for f in wav_files if f != last_played]
    if not candidates:
        candidates = wav_files

    chosen_file = random.choice(candidates)
    print(f"Playing WAV: {chosen_file}")

    try:
        subprocess.Popen(["aplay", chosen_file])
        config["state"]["last_played_file"] = chosen_file
    except Exception as e:
        print(f"Failed to run aplay: {e}")


def get_active_schedule_rules(now, config):
    """Selects schedule rules based on precedence: Specific Date > Day Name > Weekend/Weekday > Default."""
    date_str = now.strftime("%Y-%m-%d")
    day_name = now.strftime("%A")  # e.g., "Monday"
    is_weekend = now.weekday() >= 5  # 5=Saturday, 6=Sunday

    # 1. Date Specific Override (YYYY-MM-DD)
    date_overrides = config.get("date_overrides", {})
    if date_str in date_overrides and date_overrides[date_str]:
        print(f"Using date override for {date_str}")
        return date_overrides[date_str]

    schedules = config.get("schedules", {})

    # 2. Specific Day of Week (e.g., "Monday")
    if day_name in schedules:
        return schedules[day_name]

    # 3. Weekend vs Weekday Grouping
    if is_weekend and "weekends" in schedules and schedules["weekends"]:
        return schedules["weekends"]
    elif not is_weekend and "weekdays" in schedules and schedules["weekdays"]:
        return schedules["weekdays"]

    # 4. Fallback Default
    return schedules.get("default", [])


def get_current_slot(now, rules):
    """Evaluates active time rules against local clock."""
    current_time = now.time()

    for slot in rules:
        start_time = datetime.strptime(slot["start"], "%H:%M").time()
        end_time = datetime.strptime(slot["end"], "%H:%M").time()

        if start_time <= current_time < end_time:
            return slot["name"], slot

    return None, None


def update_system():
    config = load_config()
    if not config:
        return

    kill = config.get("kill_switches", {})
    if kill.get("disable_all", False):
        print("Master kill switch active. Turning off LEDs...")
        green_led.off()
        red_led.off()
        return

    tz = ZoneInfo(config.get("timezone", "America/Chicago"))
    now = datetime.now(tz)

    active_rules = get_active_schedule_rules(now, config)
    slot_name, slot_info = get_current_slot(now, active_rules)

    # 1. Update LEDs
    if not kill.get("disable_lights", False):
        if slot_name:
            green_led.on()
            red_led.off()
        else:
            green_led.off()
            red_led.on()
    else:
        green_led.off()
        red_led.off()

    # 2. Update Audio
    if slot_name and slot_info.get("play_audio", False):
        today_str = now.strftime("%Y-%m-%d")
        slot_trigger_id = f"{today_str}_{slot_name}"
        last_triggered = config.get("state", {}).get("last_triggered_slot", "")

        if last_triggered != slot_trigger_id:
            print(f"Triggering audio for slot: {slot_name}")
            play_random_wav(config)
            
            # Save trigger state immediately
            config["state"]["last_triggered_slot"] = slot_trigger_id
            save_config(config)

    status_str = f"Slot: {slot_name or 'OFF'}"
    print(f"[{now.strftime('%Y-%m-%d %H:%M:%S %Z')}] Check complete. ({status_str})")


def reset_speaker():
    print("Resetting speaker")
    process = subprocess.Popen(["speaker-test", "-c", "2", "-t", "wav"])
    time.sleep(1.5)
    process.terminate()
    process.wait()
    print(f"Speaker test exit code: {process.returncode}")


def main():
    try:
        reset_speaker()
    except:
        print("Something went wrong resetting the speaker")
    print("Starting LED & Audio Controller...")
    try:
        while True:
            update_system()
            time.sleep(30)
    except KeyboardInterrupt:
        print("\nStopping...")
        green_led.off()
        red_led.off()


if __name__ == "__main__":
    main()
