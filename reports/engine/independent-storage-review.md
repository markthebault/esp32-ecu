Engine storage review (2026-11-03)
Scope: firmware/include/ecu/engine_storage.hpp, its engine_service.cpp integration,
and firmware/partitions.csv. Production source was not edited.
Primary evidence: pinned local ESP-IDF 5.5.0 package (3.50500.0), especially
components/nvs_flash/include/nvs.h and nvs_flash/src implementations.

Finding: persistence errors do not disable subsequent saves (P2).
engine_service.cpp:44 returns 507 while storage_ok remains true. Reproduce by
having nvs_set_blob return ESP_ERR_NVS_REMOVE_FAILED; the runtime document and
revision stay old, snapshot still reports storage_ok=true, and another request
with that old revision reaches NVS again. nvs.h:340-343 explicitly says this
error can occur after the new value was written and recovery completes it on
reinitialization. Recommend latching storage_ok=false on persistence errors,
requiring restart/reload before further writes. No runtime mutation on the
failed request was found; flash rollback must not be inferred from that.

Qualification: preservation claims must distinguish app-invalid data from raw
NVS corruption. engine_storage.hpp contains no erase/delete calls and correctly
blocks fallback if the second blob read errors. ESP-IDF itself, however, erases
corrupt records: nvs_page.cpp:294-299 erases CRC-invalid payloads and reports
NOT_FOUND; :650-656 removes entries with inconsistent headers during loading.
If initialization removes the tune index, the initial size query can report
NOT_FOUND; engine_storage.hpp:45-54 then migrates retained legacy or treats it
as first boot. Therefore blanket claims that corruption is always retained and
blocks saving exceed this implementation. Narrow those claims to malformed
returned documents / reported API errors, or add independent presence evidence
if automatic fallback after a lost tune is unacceptable.

Checks with no additional defect found:
- Pinned partition parser verified nonoverlap: nvs [0x9000,0xf000), phy_init
  [0xf000,0x10000), factory [0x10000,0x210000), engine_nvs [0x210000,0x220000).
  Existing offsets and the 2 MiB app limit are unchanged; layout fits 8/16 MiB.
- 64 KiB is 16 NVS pages. SDK maximum for this partition is approximately
  60000 blob bytes; a bounded 16384-byte blob has room for old/new versions.
  This is a capacity calculation, not a real flash fragmentation endurance test.
- Query lengths are bounded before allocation. Actual lengths must equal queried
  lengths. Blob embedded NULs are rejected; std::string::c_str() provides a safe
  terminating NUL for strlen even though stored blob bytes omit one. Legacy
  strings require exactly one final NUL and reject internal NULs.
- Legacy namespace is opened NVS_READONLY, validated before migration, copied
  only when dedicated key is absent, and never explicitly removed. Errors are
  propagated; caller-visible output changes only after successful persistence.
- Active tune/document/controller change only after save returns ESP_OK, under
  the service mutex. Startup errors leave defaults active with saving disabled.
- SDK nvs_api.cpp:414 and nvs_handle_simple.cpp:101-105 show commit is currently
  a no-op for a valid handle: the set operation performs writes. Keep calling
  commit to satisfy the public API, but mock staging semantics are not proof of
  flash rollback, physical capacity, wear behavior, or power-loss qualification.

No target flashing or physical flash / brownout testing was performed in this
review. Parent owns the selected N16R8 build and portable API-model test run.


Implementer resolution after this review: engine_service.cpp now sets storage_ok=false on persistence error and rejects later saves until restart/inspection. Host file persistence follows the same lockout policy and fsyncs the containing directory. A fault-injection regression covers host lockout. Documentation and comments now distinguish application no-erase behavior from SDK raw-corruption recovery. Physical flash/power-loss tests remain outstanding.
