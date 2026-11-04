# Idle review resolution

Independent reviewers worked read-only against snapshots and isolated probes. Root made the implementation changes. Each report has its own bounded scope; no reviewer accepted a complete ECU or vehicle installation.

| Finding | Resolution and retained evidence |
| --- | --- |
| Antiwindup discarded a whole integral step and could never progress | Partial achievable headroom is admitted; positive/negative saturation and recovery regressions are in the current native idle tests. The initial failing probe remains in `reviews/control/pass1/`. |
| Fresh TPS hysteresis could enter without observing closed throttle | Entry proof now precedes exit hysteresis. Native regression covers reset inside the hysteresis band. |
| Disabled nonzero commands could clear a PWM fault | Recovery requires an explicit zero; contradictory disabled/nonzero commands reject. Native PWM and independent owner guard probes cover it. |
| PWM observations mixed pending and cycle-applied identities | Separate pending and applied sequence/revisions accompany their corresponding waveform. Native test covers a mid-cycle change. |
| Allowed late PWM edges were stamped with scheduled time | Phase still follows the schedule; observation time records actual dispatch. Native test checks a 20 µs late boundary. |
| Slew could temporarily exceed a reduced hard maximum | Final output obeys the hard maximum; native regression changes the limit while the controller is active. |
| Repeated already-low stops prevented fault recovery | Both owners preserve supervised quiet continuity while already low. Independent master-off/on recovery rechecks pass. |
| Rejected phase context could re-enable idle from the proposer | PWM enable requires the executor's effective accepted command and matching identities/epoch. Independent mismatch/phase probes pass. |
| A 100% PWM timer boundary had no edge and looked like missing work | Explicit timer-progress marker advances native time without inventing an edge. Independent owner/wrapper probes pass. |
| Outlined array indexing entered flash from the ISR | Two scheduling arrays use fixed native indexing. Independent final image review and publication ISR audits find no flash helper path. |
| Simple SIL cut the valve before integrating to the cut time | Integrate first, then apply the actual edge. A permanent rise-at-0/cut-at-150 µs regression matches an independent pulse replay. |
| Reference PWM conversion disagreed with auxiliary ticks | Declared native HAL conversion uses 4 µs/native32 or 16 µs/native16; actual frequency/duty checks cover both. Production idle logic is unchanged. |
| Native initial compare never started ordinary idle PWM | Once-only counter+1 initialization is explicit; unseeded negative controls remain. No target startup equivalence is claimed. |
| Reference reported zero duty while PWM_OLCL kept running | Preserved as an upstream discrepancy. Actual pin probes and a post-halt timer window expose it, separate from external cutoff. |
| Current INI map editors referenced nonexistent pages | All seven own005 table editors reference page 1. Independent layout checks and actual offline spark-map QA pass. |
| Browser accepted malformed idle availability | Present availability must be boolean; independent Chrome/native malformed-page probes reject atomically. |
| Own005 offsets followed mutable JSON insertion order | Explicit ordered fields/arrays freeze the layout; independent reordered-defaults and whole-page roundtrips pass. |
| SIL and tuning logs lacked new idle/source fields | SIL003 has 48 columns; engine003 has 91. Availability, source/age and full integer text are checked. Actual MegaLogViewer plots both. |
| Idle master bounds/units were too broad | Current INI uses native target/gain bounds and normalized units. Independent final layout recheck passes. |
| Blank browser numbers could silently become zero | Root added a numeric guard after the integration snapshot; publication Chrome test rejects a blank before Save. |
| Supply and valve plugs could be interchanged, bypassing the switch | Supply is now a fixed Phoenix screw terminal; valve remains VH. Independent hardware pass 2 verifies the revised contract. |
| Unused driver output net names differed | Normalized OUTB_NC; native schematic parity is zero. |

The owner final source hashes still match current owner/core sources. The later web/guide assets change the selected/generic ELF hashes; root reran all three ISR audits and both USB audits on those publication images. The timing-bench image hash is unchanged. The integration snapshot predates the root blank-number guard, clearer wiring copy and a legacy-codec docstring update; final Chrome and generated-artifact checks bind that small delta. The exact offline application INI predates the three presentation-bound changes, and is retained separately.

Hardware pass 2 leaves actual carrier take-off/bias, module straps, alternate ground return, protected power, routing, load characterization and physical fit unresolved. Those findings remain open, the accessory remains unrouted and physical idle output remains disabled. Simulator/source/CAD acceptance is not a substitute for the outstanding electrical, timing, engine or vehicle tests.
