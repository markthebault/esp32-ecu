#!/bin/sh
set -eu
radio_root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
cd "$radio_root"
mkdir -p build
"${CXX:-c++}" -std=c++17 -O1 -g -Wall -Wextra -Werror -pedantic \
 -fsanitize=address,undefined -fno-omit-frame-pointer \
 -Ifirmware/include firmware/tests/espnow_test.cpp -lcrypto -o build/espnow-test
build/espnow-test
python3 tools/test_radio.py
python3 tools/test_web_config.py
