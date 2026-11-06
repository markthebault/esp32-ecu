# Pinned USB Serial/JTAG component

This project-local ESP-IDF 5.5.0 component retains the upstream Apache-2.0 source, headers, notices and license. `upstream.json` records every original source hash and the patched driver hash. ESP-IDF selects this component ahead of its installed SDK copy; the SDK installation is unchanged.

The single driver change checks `tx_ring_buf` after TX ring allocation. Upstream mistakenly checked the already-created RX ring again, so a failed TX allocation could reach installation success with a null TX ring. Existing cleanup handles a partially installed driver.

The USB ISR still uses interrupt flags 0 and resides in flash. It can pause during flash operations. The engine ISR placement audit does not cover this USB ISR. Driver ring overflow has no exposed counter in this pinned implementation. Physical load, boot/panic output, allocation failure and cache-stall behavior remain unmeasured.

Run `python3 scripts/audit_tuning_build.py compact_n16r8_web OUTPUT.json` after building to verify source hashes, local override selection, UART0-only console configuration and USB ISR placement.
