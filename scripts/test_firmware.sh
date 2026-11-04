#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
mkdir -p "$task_root/build"
"${CXX:-clang++}" -std=c++17 -O1 -g -Wall -Wextra -Werror -pedantic \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    -I "$task_root/firmware/include" "$task_root/firmware/tests/control_test.cpp" \
    -o "$task_root/build/control-test"
"$task_root/build/control-test"
"${CXX:-clang++}" -std=c++17 -O1 -g -Wall -Wextra -Werror -pedantic \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    -I "$task_root/firmware/include" "$task_root/firmware/tests/engine_test.cpp" \
    -o "$task_root/build/engine-test"
"$task_root/build/engine-test"
"${CXX:-clang++}" -std=c++17 -O1 -g -Wall -Wextra -Werror -pedantic \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    -I "$task_root/firmware/include" "$task_root/firmware/tests/engine_cylinder_test.cpp" \
    -o "$task_root/build/engine-cylinder-test"
"$task_root/build/engine-cylinder-test"
"${CXX:-clang++}" -std=c++17 -O1 -g -Wall -Wextra -Werror -pedantic \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    -I "$task_root/firmware/include" "$task_root/firmware/tests/tuning_test.cpp" \
    -o "$task_root/build/tuning-test"
"$task_root/build/tuning-test"
"${CXX:-clang++}" -std=c++17 -O1 -g -Wall -Wextra -Werror -pedantic \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    -I "$task_root/firmware/include" "$task_root/firmware/tests/tuning_allocation_test.cpp" \
    -Wl,--wrap=malloc -o "$task_root/build/tuning-allocation-test"
"$task_root/build/tuning-allocation-test"
"${CXX:-clang++}" -std=c++17 -O1 -g -Wall -Wextra -Werror -pedantic \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    -I "$task_root/firmware/tests/fakes" -I "$task_root/firmware/include" \
    "$task_root/firmware/tests/engine_storage_test.cpp" -o "$task_root/build/engine-storage-test"
"$task_root/build/engine-storage-test"
"${CXX:-clang++}" -std=c++17 -O1 -g -Wall -Wextra -Werror -pedantic \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    -I "$task_root/firmware/include" "$task_root/firmware/tests/timing_executor_test.cpp" \
    -o "$task_root/build/timing-executor-test"
"$task_root/build/timing-executor-test"
"${CXX:-clang++}" -std=c++17 -O1 -g -Wall -Wextra -Werror -pedantic \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    -I "$task_root/firmware/include" "$task_root/firmware/tests/engine_phase_test.cpp" \
    -o "$task_root/build/engine-phase-test"
"$task_root/build/engine-phase-test"
"${CXX:-clang++}" -std=c++17 -O1 -g -Wall -Wextra -Werror -pedantic \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    -I "$task_root/firmware/include" "$task_root/firmware/tests/engine_semi_test.cpp" \
    -o "$task_root/build/engine-semi-test"
"$task_root/build/engine-semi-test"
"${CXX:-clang++}" -std=c++17 -O1 -g -Wall -Wextra -Werror -pedantic \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    -I "$task_root/firmware/include" "$task_root/firmware/tests/trigger_log_test.cpp" \
    -o "$task_root/build/trigger-log-test"
"$task_root/build/trigger-log-test"
for task_idle_name in idle_control idle_pwm transient_enrichment engine_transient load_model engine_load secondary_tables engine_secondary; do
    "${CXX:-g++}" -std=c++17 -O1 -g -Wall -Wextra -Werror -pedantic \
        -fsanitize=address,undefined -fno-omit-frame-pointer \
        -I "$task_root/firmware/include" "$task_root/firmware/tests/${task_idle_name}_test.cpp" \
        -o "$task_root/build/${task_idle_name}-test"
    "$task_root/build/${task_idle_name}-test"
done
task_cjson="${PLATFORMIO_CORE_DIR:-$HOME/.platformio}/packages/framework-espidf/components/json/cJSON"
"${CC:-cc}" -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer \
    -c "$task_cjson/cJSON.c" -o "$task_root/build/trigger-cjson.o"
"${CXX:-clang++}" -std=c++17 -O1 -g -Wall -Wextra -Werror -pedantic \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    -I "$task_cjson" -I "$task_root/firmware/include" \
    "$task_root/firmware/tests/trigger_log_json_test.cpp" "$task_root/build/trigger-cjson.o" \
    -o "$task_root/build/trigger-log-json-test"
"$task_root/build/trigger-log-json-test"
"${CXX:-clang++}" -std=c++17 -O1 -g -Wall -Wextra -Werror -pedantic \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    -I "$task_cjson" -I "$task_root/firmware/include" \
    "$task_root/firmware/tests/engine_observability_test.cpp" "$task_root/build/trigger-cjson.o" \
    -o "$task_root/build/engine-observability-test"
"$task_root/build/engine-observability-test"
"${CXX:-clang++}" -std=c++17 -O1 -g -Wall -Wextra -Werror -pedantic \
    -fsanitize=address,undefined -fno-omit-frame-pointer -pthread \
    -I "$task_cjson" -I "$task_root/firmware/tests/log_fakes" -I "$task_root/firmware/include" \
    "$task_root/firmware/tests/engine_log_service_test.cpp" "$task_root/firmware/main/engine_log_service.cpp" \
    -o "$task_root/build/engine-log-service-test"
"$task_root/build/engine-log-service-test"
