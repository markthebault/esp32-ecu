#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
task_build=${ECU_TEST_BUILD_ROOT:-$task_root/build}
mkdir -p "$task_build"
"${CXX:-clang++}" -std=c++17 -O1 -g -Wall -Wextra -Werror -pedantic \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    -I "$task_root/firmware/include" "$task_root/firmware/tests/control_test.cpp" \
    -o "$task_build/control-test"
"$task_build/control-test"
"${CXX:-clang++}" -std=c++17 -O1 -g -Wall -Wextra -Werror -pedantic \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    -I "$task_root/firmware/include" "$task_root/firmware/tests/engine_test.cpp" \
    -o "$task_build/engine-test"
"$task_build/engine-test"
"${CXX:-clang++}" -std=c++17 -O1 -g -Wall -Wextra -Werror -pedantic \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    -I "$task_root/firmware/include" "$task_root/firmware/tests/engine_cylinder_test.cpp" \
    -o "$task_build/engine-cylinder-test"
"$task_build/engine-cylinder-test"
"${CXX:-clang++}" -std=c++17 -O1 -g -Wall -Wextra -Werror -pedantic \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    -I "$task_root/firmware/include" "$task_root/firmware/tests/tuning_test.cpp" \
    -o "$task_build/tuning-test"
"$task_build/tuning-test"
"${CXX:-clang++}" -std=c++17 -O1 -g -Wall -Wextra -Werror -pedantic \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    -I "$task_root/firmware/include" "$task_root/firmware/tests/tuning_allocation_test.cpp" \
    -Wl,--wrap=malloc -o "$task_build/tuning-allocation-test"
"$task_build/tuning-allocation-test"
"${CXX:-clang++}" -std=c++17 -O1 -g -Wall -Wextra -Werror -pedantic \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    -I "$task_root/firmware/tests/fakes" -I "$task_root/firmware/include" \
    "$task_root/firmware/tests/engine_storage_test.cpp" -o "$task_build/engine-storage-test"
"$task_build/engine-storage-test"
"${CXX:-clang++}" -std=c++17 -O1 -g -Wall -Wextra -Werror -pedantic \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    -I "$task_root/firmware/include" "$task_root/firmware/tests/timing_executor_test.cpp" \
    -o "$task_build/timing-executor-test"
"$task_build/timing-executor-test"
"${CXX:-clang++}" -std=c++17 -O1 -g -Wall -Wextra -Werror -pedantic \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    -I "$task_root/firmware/include" "$task_root/firmware/tests/engine_phase_test.cpp" \
    -o "$task_build/engine-phase-test"
"$task_build/engine-phase-test"
"${CXX:-clang++}" -std=c++17 -O1 -g -Wall -Wextra -Werror -pedantic \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    -I "$task_root/firmware/include" "$task_root/firmware/tests/engine_semi_test.cpp" \
    -o "$task_build/engine-semi-test"
"$task_build/engine-semi-test"
"${CXX:-clang++}" -std=c++17 -O1 -g -Wall -Wextra -Werror -pedantic \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    -I "$task_root/firmware/include" "$task_root/firmware/tests/trigger_log_test.cpp" \
    -o "$task_build/trigger-log-test"
"$task_build/trigger-log-test"
for task_idle_name in idle_control idle_pwm boost_control transient_enrichment engine_transient load_model engine_load secondary_tables engine_secondary switch_acquisition switch_transport status_led flex_fuel flex_ingress engine_flex flex_capture_owner engine_radio_flex; do
    "${CXX:-g++}" -std=c++17 -O1 -g -Wall -Wextra -Werror -pedantic \
        -fsanitize=address,undefined -fno-omit-frame-pointer \
        -I "$task_root/firmware/include" "$task_root/firmware/tests/${task_idle_name}_test.cpp" \
        -o "$task_build/${task_idle_name}-test"
    "$task_build/${task_idle_name}-test"
done
task_cjson="${PLATFORMIO_CORE_DIR:-$HOME/.platformio}/packages/framework-espidf/components/json/cJSON"
"${CC:-cc}" -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer \
    -c "$task_cjson/cJSON.c" -o "$task_build/trigger-cjson.o"
"${CXX:-clang++}" -std=c++17 -O1 -g -Wall -Wextra -Werror -pedantic \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    -I "$task_cjson" -I "$task_root/firmware/include" \
    "$task_root/firmware/tests/trigger_log_json_test.cpp" "$task_build/trigger-cjson.o" \
    -o "$task_build/trigger-log-json-test"
"$task_build/trigger-log-json-test"
"${CXX:-clang++}" -std=c++17 -O1 -g -Wall -Wextra -Werror -pedantic \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    -I "$task_cjson" -I "$task_root/firmware/include" \
    "$task_root/firmware/tests/engine_observability_test.cpp" "$task_build/trigger-cjson.o" \
    -o "$task_build/engine-observability-test"
"$task_build/engine-observability-test"
"${CXX:-clang++}" -std=c++17 -O1 -g -Wall -Wextra -Werror -pedantic \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    -I "$task_cjson" -I "$task_root/firmware/include" \
    "$task_root/firmware/tests/engine_boost_test.cpp" "$task_build/trigger-cjson.o" \
    -o "$task_build/engine-boost-test"
"$task_build/engine-boost-test" "$task_root"
"${CXX:-clang++}" -std=c++17 -O1 -g -Wall -Wextra -Werror -pedantic \
    -fsanitize=address,undefined -fno-omit-frame-pointer -pthread \
    -I "$task_cjson" -I "$task_root/firmware/tests/log_fakes" -I "$task_root/firmware/include" \
    "$task_root/firmware/tests/engine_log_service_test.cpp" "$task_root/firmware/main/engine_log_service.cpp" \
    -o "$task_build/engine-log-service-test"
"$task_build/engine-log-service-test"
"${CXX:-g++}" -std=c++17 -O1 -g -Wall -Wextra -Werror -pedantic \
    -fsanitize=address,undefined -fno-omit-frame-pointer -pthread \
    -I "$task_cjson" -I "$task_root/firmware/tests/switch_fakes" -I "$task_root/firmware/include" \
    "$task_root/firmware/tests/switch_service_test.cpp" "$task_root/firmware/main/switch_service.cpp" \
    "$task_build/trigger-cjson.o" -o "$task_build/switch-service-test"
"$task_build/switch-service-test"
"${CXX:-g++}" -std=c++17 -O1 -g -Wall -Wextra -Werror -pedantic \
    -fsanitize=address,undefined -fno-omit-frame-pointer -pthread \
    -DECU_COMPACT_A3=1 -DECU_SELECTED_N16R8=1 -DECU_FLEX_G38_DRAFT=1 \
    -I "$task_cjson" -I "$task_root/firmware/tests/switch_fakes" -I "$task_root/firmware/include" \
    "$task_root/firmware/tests/shared_i2c_service_test.cpp" "$task_root/firmware/main/switch_service.cpp" \
    "$task_build/trigger-cjson.o" -o "$task_build/shared-i2c-service-test"
"$task_build/shared-i2c-service-test"
python3 -B "$task_root/scripts/test_flex_target_service.py" \
    --output "$task_root/.cache/engine/flex-target-suite-$(date +%s)-$$"
python3 -B "$task_root/scripts/test_radio_service.py" \
    --output "$task_root/.cache/engine/flex-radio-suite-$(date +%s)-$$"
