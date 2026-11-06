# Independent idle hardware architecture review

Reviewed root HEAD `cbfbe4a`, 2026-11-03. Read-only review of production/source files; only this ignored review folder was written. No native CAD or output activation was performed. This is a concrete draft interface, not a manufacturing or vehicle qualification.

## Decision

Use **GPIO3, U3 socket pad13**, as the default idle PWM candidate, with a physical **2.2k pulldown at the GPIO** and a **1k series resistor** into a high-impedance driver input. Prefer a small screw-mounted, all-through-hole accessory over repacking the 120mm A4 carrier before the purchased module fit is resolved. Preserve A3 and A4 as-is; a later A5 can integrate the same circuit after fit/routing review.

GPIO45/U3pad37 can also be driven after boot, but its reset-high meaning can select 1.8V flash supply when eFuses leave that selection to the strap. An uncharacterized module, pullup, auxiliary-powered accessory or held output is therefore a more consequential bootstrap failure. Merely seeing N16R8 printed on a listing does not prove eFuse state. A high-impedance, independently powered input and pulldown would make GPIO45 technically possible, but it is the second choice.

GPIO3 has no internal pull resistor and affects JTAG selection rather than flash voltage. With factory-default EFUSE_STRAP_JTAG_SEL=0 its level is ignored for JTAG routing. **Read the actual module eFuses without writing them before physical release.** If STRAP_JTAG_SEL=1 and both JTAG paths are otherwise allowed, pulling GPIO3 low selects pad JTAG on GPIO39-42, already used by WDI/SAFE_N/I2C. That combination is a release blocker, not an instruction to burn eFuses. Other JTAG-disable eFuses can override selection; retain their readout and assess the actual truth table. Native USB CDC use does not justify blindly assuming all JTAG straps are harmless. Espressif requires strap stability for 3ms after EN rises. A permanent pulldown meets the intended low hold; firmware must initialize PWM low before any ARM assertion.

## Recommended leaded components and pin-level circuit

A sound way to retain hardware gating and avoid adding an ordinary 5V HCT clamp path to a strap is **TI UCC27524P.B, PDIP8**, plus the already-used **ST VNP35N07-E, TO220**, and an external axial flyback diode. The UCC product is active and its exact P grade is listed in the package addendum, although direct TI inventory was unavailable when checked. Exact distributor availability and matching package drawing remain procurement checks. Freeze the datasheet revision and confirm the P-grade electrical guarantees before a released BOM; do not silently substitute SOIC/DFN.

Driver wiring:

- UCC pin1 ENA: carrier **RUN_5V**, via 1k; add **4.7k from ENA to GND** locally. ENA internally defaults high, so this external pulldown is mandatory. An unplugged RUN lead must disable the accessory.
- UCC pin2 INA: GPIO3 through 1k. The 2.2k pulldown belongs on the GPIO side, at the module/carrier, so removing the accessory cannot remove the strap bias. Add a local 10k pulldown on INA if the signal connector can be disconnected while powered.
- UCC pin3 GND: local power-switch source ground reference, bonded by the planned star/return arrangement.
- UCC pins4 INB and8 ENB: GND. Pin5 OUTB: unconnected. Never leave the unused channel enable floating.
- UCC pin6 VDD: **regulated carrier +5V logic**, not raw vehicle 12V. Fit short-lead **100n ceramic plus1u film/radial** locally. Check actual capacitor voltage, tolerance, ESR and transient current requirements.
- UCC pin7 OUTA: **220 ohms** to VNP pin1 INPUT. Fit **10k INPUT-to-SOURCE** on the switch side so loss of driver wiring/power cannot leave a charged gate.
- VNP pin2 DRAIN and metal tab: **IAC_LS**. Its tab is live, not a chassis heatsink connection. Pin3 SOURCE: dedicated power return.
- Two-wire normally-closed solenoid: one lead to protected, fused, relay-switched **IAC_12V**, the other to **IAC_LS**.
- Flyback **Vishay SB5H100-E3** (DO201AD,100V/5A family): anode to IAC_LS, cathode/band to IAC_12V. Its published current rating depends on case/lead temperature; final diode temperature must be measured. This is a concrete alternative to the existing Diodes SB5100 family, whose manufacturer page lists an EOL PCN; do not equate identical generic markings with current procurement/qualification.

This yields `IAC_ON = IDLE_PWM AND RUN_5V`, where the existing hardware computes `RUN_5V = ARM AND SAFE_N AND INTERLOCK`. U9pin6 and TP6 provide RUN_5V; TP3 is +5V; TP1 is ground. A released adapter should use a keyed proper header or new carrier connector rather than rely on unrestrained test-point flywires. New control header contract: signal ground, regulated5V, IDLE_PWM3V3, RUN_5V. Separate high-current connectors: supply/PGND and valve+/IAC_LS. Define power and signal return geometry before layout. Valve current must not use J2/J4 sensor/service return wires. Ground-open and alternative-return faults must be examined; redundant ground wires can accidentally route coil current through a logic connector.

Why this driver: independently enabled, TTL input thresholds compatible with3.3V, internal UVLO forces output low, and its input/enable voltages are independent of VDD. A plain SN74HCT08 accepts3.3V when powered but has a VCC clamp path when unpowered and no guaranteed operation below4.5V. It is useful existing logic, but a sole HCT gate is a weaker accessory input/power-sequence boundary. The protected VNP part provides useful local overload/thermal behavior and accepts TTL drive, but its device current limit is around35A, not a2A valve limiter. Thermal and repetitive inductive limits remain real.

## Power and load compatibility contract

Declare the accessory for **one two-wire, normally-closed, energize-to-open, continuous-duty12V PWM solenoid**, with verified polarity and no incompatible internal electronics. A motorized valve, bipolar/reversing valve, stepper, DBW motor or unidentified three-wire valve is outside this contract.

Initial interface bounds: nominal12V, **9-16V continuous at the accessory input**, and **2A maximum coil current over the declared voltage/temperature/duty range**. These are acceptance bounds, not measured performance. A valve whose cold resistance yields greater than2A at16V is not covered simply because a reseller calls it a2A valve. The design does not regulate current. Actual resistance, inductance, duty/frequency limits, energized duty rating and spring-return direction must be characterized. Maximum inductive energy is `0.5*L*I_peak^2`; no arbitrary inductance limit can be justified without that load data.

Use a separate externally fused, relay-switched actuator feed. **Never obtain coil power from carrier J1's1A logic branch, protected logic VIN,3V3,5V or sensor5V.** A branch fuse initially in the2.5-3A class needs final time-current, temperature, wire, interruption and fault-current review. It protects the harness; it is not a precise2A current limiter. A switch drain-source short or mechanical valve jam cannot be cured by the PWM bit: main actuator power removal and fuel/spark cut policy remain necessary.

Require reverse-polarity/transient protection on the actuator branch. If it is not already supplied upstream, the accessory draft must include its own appropriately oriented series reverse diode and local transient clamp before the valve positive node, plus bulk and HF decoupling. An axial SB5H100-family reverse diode can dissipate roughly a watt at2A and needs actual thermal review. Reusing a1.5KE27CA-family TVS is only a starting clamp arrangement; repeated surge energy, fuse coordination, long-harness overshoot and source impedance must be checked. Do not label this automotive surge-qualified based on a nominal TVS or70V switch rating.

The diode loop must remain local to the valve/switch harness and cathode must connect after any reverse diode and relay contact, at the same supply node as the valve. Missing or reversed flyback protection is a hardware failure. A plain flyback diode intentionally slows current decay and therefore valve closure. A gate-off command, or even opening the positive relay contact, does not make magnetic energy/airflow disappear instantaneously. Do not fit a high-voltage flyback zener to improve closing speed without requalifying switch, diode, harness and EMI energy.

## Reset, brownout, backfeed and software integration

- At reset, GPIO3's pulldown commands low. Existing ARM/INTERLOCK pulldowns hold RUN_5V low, and the driver ENA pulldown independently disables its output.
- With logic5V absent and actuator12V present, driver UVLO and the switch INPUT-to-SOURCE pulldown must keep the coil off. With external MCU3V3/USB power present and driver5V absent, the driver inputs are designed not to clamp to VDD; preserve current-limiting series resistors and test actual backfeed. This does not authorize existing forbidden USB/carrier dual powering elsewhere on the board.
- SAFE_N loss or physical interlock opening must force ENA low through hardware, even if LEDC remains at a stale nonzero duty. The selected N16R8 physical policy remains compiled out until qualification; a new resistor-only dummy-load build must explicitly own this additional pin and keep default pin-output masks honest.
- Use one reserved LEDC low-speed timer/channel, fixed board GPIO3, no fade operation. Default100Hz is a starting test frequency only; an actual valve's allowed range must govern released calibration. Candidate software range50-250Hz with10-bit duty resolution is technically modest, but enabling it requires the valve data. Use a stable clock source and prove coexistence with RMT/USB and MCPWM/GPTimer capture/compare resources.
- Never clear a LEDC-owned output by only calling gpio_set_level(0): peripheral output routing may still own the pin. Stop LEDC at idle level0 and/or disable its output through the documented API. ESP-IDF5.5 supports ISR use of ledc_stop with CONFIG_LEDC_CTRL_FUNC_IN_IRAM when cache-independent failure shutdown is required. Independently, the existing IRAM all-low path must drop ARM and therefore the driver's ENA.
- Bind idle command validity to the existing control heartbeat, synchronization/state and timing-fault policy. A free-running PWM peripheral can outlive a stalled producer. Existing MAX1232 has up to2s watchdog delay; it is only the eventual hardware fallback, not proof of prompt idle closure. Use the existing executor's stale-command fault timing, zero idle on fault/stop/configuration hold, and verify the measured delay.
- PWM zero/off must be the only default. Apply duty/frequency changes transactionally, avoid resume-before-enable glitches, and account for the LEDC full-scale representation limit rather than blindly writing2^resolution. A requested100% value needs an explicitly tested representation/policy.
- No current/position feedback is allocated by this circuit. UI may report proposed/applied duty and inhibit reasons, but cannot claim measured current, valve movement, closure or fault feedback. VNP input feedback would need a separate measured/isolated diagnostic path before being advertised.

## Physical acceptance work still required

Scope GPIO3, ENA/RUN, switch input, IAC_LS, current and supply rails through power-up/down, ENreset, downloader entry, externalUSB-only power, missing accessory5V, open control leads, open ground, watchdog, SAFE_N and interlock faults. Record the strap readout and verify repeated cold/warm boots without eFuse changes. Test PWM0/min/max/full-scale, frequency transitions, stalled producer and fault ISR shutdown. Use a current-limited supply and resistor load first; then an identified unpowered-characterized solenoid. Measure peak/RMS current, flyback overshoot and decay, valve closure latency, switch/diode/regulator heat, supply droop and EMI/RF behavior in the intended enclosure. Test shorts only with a reviewed, protected fixture; neither software nor a fuse alone qualifies a short fault.

An accessory needs screw mounting, insulated clearance from its live tab and harness strain relief; place outside the antenna/foil exclusion. Its exact dimensions are layout-dependent. It avoids silently enlarging the120mm carrier but is not proof that it fits the existing printed box. All carrier/socket/module/splash qualification holds remain.

## Exact primary sources

1. Espressif ESP32-S3 Series Datasheet v2.2, sections3.2/3.4, tables3-2/3-4/3-5: https://www.espressif.com/sites/default/files/documentation/esp32-s3_datasheet_en.pdf
2. Espressif hardware schematic checklist, SPI voltage/straps: https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/schematic-checklist.html
3. TI UCC27524 datasheet, SLUSFA9 June2024 and package addendum; enable defaults, input thresholds, VDD-independent inputs, UVLO and P-grade listing: https://www.ti.com/lit/ds/symlink/ucc27524.pdf
4. Exact TI UCC27524P part record: https://www.ti.com/product/UCC27524/part-details/UCC27524P
5. ST VNP35N07-E datasheet, DocID023779 Rev3: https://www.st.com/resource/en/datasheet/vnp35n07-e.pdf
6. Vishay SB5H90/SB5H100 datasheet88722: https://www.vishay.com/docs/88722/sb5h90.pdf
7. TI SN74HCT08 datasheet SCLS063G: https://www.ti.com/lit/ds/symlink/sn74hct08.pdf
8. Espressif ESP-IDF5.5.6 LEDC reference: https://docs.espressif.com/projects/esp-idf/en/v5.5.6/esp32s3/api-reference/peripherals/ledc.html
9. Diodes SB5100 part record and EOL PCN evidence: https://www.diodes.com/part/view/SB5100
10. Littelfuse1.5KE family primary datasheet: https://www.littelfuse.com/assetdocs/littelfuse_tvs_diode_1_5ke_datasheet.pdf?assetguid=9d02c7d2-86a5-4bff-9251-966d6af02bf7

Downloaded source PDFs and hashes, where the hosts allowed direct download, are in `sources/manifest.json`. ST direct downloads timed out here; those documents were inspected through the web source, not silently replaced with distributor copies.
