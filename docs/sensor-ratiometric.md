# Sensor supply compensation

Linear and table calibration can optionally use a sensor signal that is ratiometric to the carrier's measured SENSOR_5V rail. The default is Off for every channel. Enable it only when the sensor documentation establishes that relationship. An independently regulated wideband/controller output usually needs its documented absolute-voltage curve instead.

In Calibration, select Linear or Table, enable **Sensor output is ratiometric**, and enter the supply used for that curve, normally 5 V. Curve voltage coordinates then mean the voltage at that reference supply:

```text
curve voltage = instantaneous connector voltage × curve supply / measured SENSOR_5V
```

For an illustrative 0.5..4.5 V, 10..110 kPa sensor characterized at 5 V, a true 50 kPa produces 2.1 V at 5 V supply and 2.016 V at 4.8 V supply. The absolute curve reads 47.9 kPa in the second case. The optional ratio restores the 2.1 V coordinate before conversion. These numbers illustrate the calculation; they are not a vehicle base calibration.

Changing the mode, unit, ratio option or reference supply clears the editor's calibration confirmation. Verify the whole curve against independent references before confirming it again. **Use live V** follows the edited ratio/reference settings, even before saving; it rejects stale/failed ADC data and invalid conversion supply. The live converted value continues using the saved profile until a successful save.

Raw ADC counts, ADC pin voltage and connector voltage remain actual acquisition observations. The editor also shows its curve voltage separately. Status JSON adds `ratiometric`, `transfer_voltage_v` and `display_transfer_voltage_v` for each sensor. The first transfer voltage is instantaneous; the second is the readout filter basis. A failed ratio conversion reports an unavailable basis instead of falling back to an absolute-voltage value.

Readout smoothing normalizes each sample before filtering. The engine input binding always uses the instantaneous conversion. Electrical fault thresholds use the instantaneous, absolute connector voltage. The engine's existing 4.75..5.25 V supply guard and sample freshness checks are unchanged; conversion math accepting a broader 4..5.3 V interval does not authorize engine operation. Physical engine outputs remain inhibited.

Voltage-only and NTC beta modes reject an explicit ratio flag. NTC beta already uses the measured supply and compensates the board's 55 kΩ input load. The option does not correct ground offsets, divider tolerances, sample skew, sensor nonlinearity or loading. Sensor power still passes through the shared fuse and wiring. Their voltage drop/current/thermal behavior requires physical testing.

## Profiles and interoperability

Sensor profile schema 2 requires `ratiometric` and `reference_supply_v` for all six sensors. Schema 1 loads/imports explicitly initialize Off and 5 V; they do not inherit settings from a previously enabled editor or parser object. Mixed schema 1 documents containing schema 2 fields reject. Loading a valid old saved profile normalizes it in RAM without rewriting the original file/NVS entry. A successful explicit save persists schema 2 with the usual revision check. Device storage uses a bounded blob under `ecu_config/profile_blob`, avoiding the SDK string ceiling when migration expands a previously valid profile. The old `profile` string stays read-only. A present malformed blob blocks saving instead of silently rolling back to that old record. Device commit errors preserve the active runtime profile and block further saves until restart/inspection; SDK flash atomicity is not established by this caller policy.

The existing 24 KiB general NVS partition and all partition offsets are unchanged. The 16 KiB envelope/blob cap is not a guarantee of available shared NVS capacity; an SDK space error follows the failure policy above. No automatic erase is requested. Downgrading firmware can load the retained older string instead of the current blob, so export the current profile before changing firmware.

An updated browser negotiates this capability from the running backend's profile version. An old profile 1 backend receives legacy-only saves and rejects profile 2 imports in the browser. No running service is restarted by this development change.

Sensor profile versions are separate from engine tune schema 9, own010 TunerStudio files, MSL007 and screen protocols. This change preserves those formats. ESP-NOW sensor values use the same normalized readout basis when enabled, with raw ADC fields retained.

## Reproduction and limits

The focused native test exercises the actual parser, conversion, filter, engine binding and controller with known ratios, reverse/table curves, ADC quantization, faults, migration and unchanged rail/freshness cuts. The Python tests exercise actual shared C++ behavior and file persistence. A native SDK API model exercises the actual sensor storage helper/parser, including the reviewed 3,775-byte legacy profile that becomes 4,033 bytes, blob priority, malformed data and read/write/commit failures. It does not emulate flash capacity, SDK recovery, wear or power loss. Chrome tests cover editing, capture, legacy migration, old-backend compatibility and narrow viewports.

```sh
python3 -B tools/test_sensor_native.py --output .cache/NEW_SENSOR_CORE
python3 -B tools/test_sensor_storage.py --output .cache/NEW_SENSOR_STORAGE
ECU_NATIVE_CACHE_ROOT=.cache/NEW_SENSOR_NATIVE python3 -B tools/test_web_config.py
ECU_NATIVE_CACHE_ROOT=.cache/NEW_SENSOR_NATIVE python3 -B tools/test_sensor_ratiometric.py
ECU_NATIVE_CACHE_ROOT=.cache/NEW_SENSOR_NATIVE uv run --offline --with playwright==1.64.0 python -B tools/test_sensor_ratiometric_ui.py --report-dir .cache/NEW_SENSOR_UI
ECU_NATIVE_CACHE_ROOT=.cache/NEW_SENSOR_NATIVE python3 -B tools/compare_sensor_calibration.py --output .cache/NEW_SENSOR_LEGACY
```

The legacy replay builds the published pre-ratio parser/converter from commit `1050d9276e89f4289cfe4ad1e275d604485c6243` in a fresh directory, then compares values, voltages, validity and fault strings. It requires that Git object and the pinned local ESP-IDF cJSON source. Its current 12,288 comparisons are bit-identical with compensation Off. This is a software regression check, not a sensor accuracy claim.

The nonideal circuit study remains conditional development evidence. Authored supply impedances, capacitor equivalents, sensor outputs and GPIO transfer assumptions are not measured board limits. Only ADC channel 7 includes the explicit typical sampling-load equivalent; other modeled channels include their board RC paths but omit ADC switching charge. Native control replay assumes clocked operation and declared per-channel sample timing. It does not execute the ESP32, physical supervisor or output scheduler. Hardware, temperature, EMI/surge, sensor wiring, module/RF and enclosure qualification remain open, alongside the wider Speeduino feature gaps.
