# Validation and release gates

The JSON reports in `reports/` are measured software/CAD results. The calculations are analytical. No physical tests below have been performed. A passing DRC establishes geometry/connectivity under its configured rules; it does not establish electrical performance.

## Reproducible software and CAD checks

`sh scripts/test_firmware.sh` compiles the portable core with warnings treated as errors and address/undefined-behavior sanitizers. Scenarios cover 60-2 and 36-1 decoding, cranking/redline speeds, bad/missing/extra teeth, sync reacquisition, stall, timestamp reversal, NaN/invalid inputs, hot coolant, overspeed, stale sensors, lambda limits, injector capacity, pulse overlap/overflow and late-edge cutoff, plus a deterministic noise sweep.

`platformio run -d firmware -e esp32s3 -e bench` cross-compiles both ESP32-S3 images. This is compilation, not execution on an ESP32. No connected serial board was assumed or flashed.

`sh scripts/check_hardware.sh` exports the actual KiCad netlist, runs ERC, DRC with zone refill and schematic parity, and checks physical module/driver/ADC/limiter pins against firmware assignments and nominal electrical inequalities. All reported errors, unconnected items and parity mismatches must be resolved. Warnings must be reviewed, not hidden.

## Physical bench sequence

1. Complete exact MPN and footprint review for every BOM line. Resolve generic passives, electrolytic ESR, timing capacitor dielectric/tolerance and header ratings. Review buck hot-loop/feedback routing, power return paths and driver copper area. No PCBA order is released by this repository.
2. Assemble only the supply section first. Use a current-limited laboratory supply with the input fuse. Check 5 V/3.3 V startup, ripple, load steps and regulator temperature. Then fit the processor and test reset/watchdog timing. Keep J3 open and all external relays disconnected.
3. With a logic analyzer and dummy loads, prove every output remains off through flashing, reset, watchdog timeout, missing 3.3 V/5 V, interlock opening and brownout. Scope the independent pulse ceilings and early reset/recovery at the maximum intended repetition rate. Deliberately stop the supervisor loop.
4. Drive known analog voltages and Hall patterns. Measure ADC transfer and settling, sensor reference error, input faults, edge jitter, capture wrap, queue overflow, stall and sync reacquisition. Measure the worst-case GPIO timing under maximum CAN load and logging. Test a range of supply voltages and temperatures.
5. With a laboratory pulse source, run the specified automotive supply and harness transients. Record waveform/source impedance, polarity, temperature, clamp overshoot, fuse behavior and component temperature. Include reverse battery, jump start, cold crank, sustained overvoltage, ground offsets, short/open inputs, ESD, and repeated injector flyback. Use the applicable OEM/ISO profile rather than a generic pulse-power number. Conducted/radiated EMC and immunity tests remain separate.
6. Only after the dummy-load and transient gates, test representative injectors/coils on an isolated non-fueled rig with current probes and protected power. Verify injector current and closing time, repetitive clamp energy, coil input levels/polarity, dwell and shutdown-induced spark. Check every external relay and contact/fuse path. Measure thermal rise in the intended enclosure.

## Vehicle work that requires the first car

This is a later commissioning stage. Generic board, firmware and simulated-engine development do not require a selected car. Develop common behavior against engine profiles, and use vehicle records only for installation evidence.

Start with the OEM wiring diagram, engine code and component part numbers. Record every OEM connector pin in the vehicle profile and a reviewed adapter drawing. Confirm PFI versus GDI, sensor type, trigger geometry/TDC offset, coil logic, injector curves, fuel pressure, throttle and VVT/idle needs. Do not assume the car is supported because it is naturally aspirated or made in 2015.

Implement actual sensor conversions, calibrated fuel/ignition maps, cranking/warmup/transient fueling, actuator diagnostics, cam phase and a target hardware-compare event planner. Integrate and measure the portable queue's deadlines in that backend. Implement power-loss behavior and fault latching/rearm. The current flashable images do none of this engine scheduling.

Retain legitimate immobilizer authorization and integrate the required vehicle network functions. Validate throttle/torque coordination, dashboard, ABS/ESC, transmission and air conditioning as applicable. Do not suppress emissions monitors to make a substitution appear compatible.

Before fuel, validate the crank/TDC relationship with an independent measurement. Engine/dyno work then establishes mixture, combustion stability, knock margins, fuel pressure, dwell/current and thermal behavior over the operating envelope. Catalyst protection needs misfire response, lambda fault handling and thermal evidence, including cold start. Road operation additionally requires the applicable inspection/emissions approval.

## Release status

There is no assembled hardware, transient test report, timing capture, engine run, dyno calibration or emissions report. These are open requirements, not implied passes. The project is delivered for engineering review and bench development.
