#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
mkdir -p "$task_root/build"
"${CXX:-clang++}" -std=c++17 -O1 -g -Wall -Wextra -Werror -pedantic \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    -I "$task_root/firmware/include" "$task_root/firmware/tests/control_test.cpp" \
    -o "$task_root/build/control-test"
"$task_root/build/control-test"
