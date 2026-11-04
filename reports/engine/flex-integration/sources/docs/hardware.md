# A0 electrical design

Status: engineering prototype. No assembled board, measured waveforms or vehicle evidence exists. Reference limits below are design targets, not established operating ratings.

## Interfaces

| Connector | Pin order | Contract |
|---|---|---|
| J1 | fused key-switched 12 V, GND | External 1 A logic fuse near source. Never carry injector/coil supply through this header. |
| J2 | GND, TX, RX, EN, BOOT | 3.3 V UART; TX/RX are named from the ECU. No supply input. |
| J3 | 3.3 V, interlock | Normally open contact. Opening inhibits output hardware. No external voltage. |
| J4 | GND, 3.3 V, SDA, SCL, SAFE_N | Protected-enclosure expansion only. No vehicle harness or hot-plug qualification. |
| J5 | sensor 5 V, GND, MAP, TPS, CLT, IAT, wideband controller, buffered post-cat, GND, GND | External signals 0-5 V. No raw wideband cell, oxygen heater or unbuffered narrowband sensor. |
| J6 | sensor 5 V, GND, crank, cam | Hall signals only. Optional pullups are DNP. VR signals require a separate conditioner. |
| J7 | CANH, CANL, GND | Silent hardware and software listen-only by default. |
| J8 | MAIN_LS, PUMP_LS, FAN_LS, GND | External fused relay coils, target <=150 mA each. External flyback diode across each coil. No motors. |
| J9 | INJ1-4 low sides, four GND returns | High-impedance saturated PFI injectors only, target <=1.2 A each. Current/thermal/flyback qualification pending. |
| J10 | IGN1-4 logic, GND | Active-high smart coils with TTL thresholds and low input current. No coil primaries. Confirm exact coil transfer and pulse polarity. |

Every connector is a generic bench header. A sealed, keyed vehicle adapter, terminal ratings, contact retention, strain relief, grounding and enclosure are separate design work. Do not infer OEM connector numbering from PCB numbering.

## Power and transients

External fuse -> bidirectional SMCJ24CA across J1 -> STPS5H100BY series blocking diode -> bulk/HF capacitors -> LM5164-Q1 buck -> NCV1117 3.3 V LDO. Sensor 5 V passes through a 100 mA PTC. The PTC responds thermally; it is not a fast electronic current limiter.

The buck is designed around approximately 5 V, 303 kHz and a 33 uH SRP7028A-330M inductor. The calculated initial 5 V load ceiling is 0.4 A, with a 0.2 A continuous 3.3 V target pending thermal tests. The inductor has manufacturer-stated 2.5 A saturation and 2 A RMS ratings under its published test conditions. Capacitor DC bias, saturation derating, LDO ESR and losses still require review. See [buck data sheet](https://www.ti.com/lit/ds/symlink/lm5164-q1.pdf), [inductor data sheet](https://www.bourns.com/docs/product-datasheets/srp7028a.pdf), and [LDO data sheet](https://www.onsemi.com/pdf/datasheet/ncp1117-d.pdf).

The TVS's stated pulse clamp does not establish survival of load dump. Source resistance, waveform duration, temperature, harness inductance, fuse I²t, diode pulse stress and repeated events determine survival. There is no active sustained-overvoltage disconnect, no 24 V-system support, and no guaranteed crank ride-through. Below the regulated range, reset and inhibit are intended behavior. The buck's 100 V rating alone does not rate the entire board for 100 V.

Actuators require their own external fuses and relay-switched 12 V. The main relay contact supplies injector and coil positives. A drain-source short in an output transistor is not repaired by firmware; physical power removal is required. External actuator-rail protection and relay ratings must match the vehicle.

## Output inhibit and pulse bounds

PGOOD, watchdog WDO/ENOUT and supervisor RESET are wired together as open-drain SAFE_N. A diode also pulls ESP32 EN low on a fault. `RUN_5V = ARM AND SAFE_N AND INTERLOCK`; external pulldowns keep the unpowered/reset state inhibited. The external watchdog is nominally 1.6 s with R10 DNP so the ESP32 can boot. A populated R10 selects a nominal 200 ms timeout, only after boot timing has been measured. See the [watchdog data sheet](https://www.ti.com/lit/ds/symlink/tps3431-q1.pdf).

Each injector/coil command passes through a non-retriggerable timing window and a command AND gate. The reset is also gated by RUN and the command, so an ordinary short command clears its window and permits the next cycle. Nominal RC windows are 18.9 ms for injection and 4.76 ms for ignition. These are ceilings for stuck-high commands, not precise dwell settings. Confirm reset-edge triggering, RC recovery, propagation delay, component tolerance, power sequencing and all fault states on a scope. A watchdog heartbeat cannot prove correct engine timing. See [74HCT221 timing/reset behavior](https://assets.nexperia.com/documents/data-sheet/74HCT221.pdf).

The VNL5050 low sides provide device-level overload and thermal protection. They do not implement injector current regulation or identify an engine misfire. Their internal current limit is much greater than normal injector current; branch fuses and harness sizing remain necessary. Repetitive demagnetization energy must be checked against the actual injector. See [ST driver data sheet](https://www.st.com/resource/en/datasheet/vnl5050n3-e.pdf).

Removing a smart-coil dwell command can generate a spark. A cutoff must remove fuel and actuator power with a validated sequence. A0 bench mode must never be used with a fueled engine.

## Inputs and communications

Six analog inputs use 22k/33k division, RC filtering and rail clamps. ADC channels 6 and 7 monitor protected supply and sensor supply. A rail bleed sinks limited clamp current; it does not establish unpowered pin-injection or short-to-battery immunity. ADC full scale tracks the 3.3 V rail. Verify reference accuracy and source impedance/settling at the implemented sample rate. Raw ADC counts are reported until sensor curves are available.

CLT/IAT pullups are DNP and can be fitted for a characterized passive NTC. A raw rear oxygen sensor needs a suitable high-impedance buffer. A wideband sensor needs its complete external controller, including heater control and fault/status handling.

Crank/cam have series limiting, clamps and Schmitt inputs. Hall pullups are DNP until the sensor's output type is known. The software wheel decoder establishes 360-degree sync only. Cam edges are captured but 720-degree phase is not decoded.

JP1 enables CAN transmission electrically when closed; JP2 connects termination. Both are open by default. The supplied firmware uses listen-only mode even with JP1 closed. No OEM immobilizer, torque, ABS/ESC, dashboard, transmission or A/C messages exist. The [TCAN1051V-Q1 data sheet](https://www.ti.com/lit/ds/symlink/tcan1051-q1.pdf) defines silent mode; the ESP32 TWAI controller here is classic CAN, not CAN FD.

## Extending to a vehicle

Keep fuel/pulse mathematics independent of hardware. Use engine profiles for control parameters and separate harness adapters for each installation. A car does not need to be selected during generic platform development. Use dedicated modules for VR conditioning, direct injection, knock acquisition, electronic throttle, extra cylinders and oxygen heaters. Electronic throttle needs redundant sensing, an H-bridge, independent fault handling and a separate safety analysis.

A three-way catalyst requires validated mixture and misfire control. A0's bounded lambda algorithm is only a building block. It does not provide catalyst temperature estimation, knock control, cold-start/catalyst heating calibration, misfire diagnostics, OBD readiness or emissions approval.

Several parts, including the [ESP32-S3 module](https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf), are industrial components. AEC qualification of selected components does not qualify the complete ECU. Final placement must address a sealed enclosure's thermal limits, vibration and EMC.
