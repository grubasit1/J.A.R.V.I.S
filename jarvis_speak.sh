#!/bin/bash
export PULSE_RUNTIME_PATH="/run/user/1000/pulse"
espeak-ng -a 200 "$1" --stdout | paplay --volume=65536
