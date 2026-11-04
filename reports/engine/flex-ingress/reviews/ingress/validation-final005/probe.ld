ENTRY(flex_ingress_isr_probe)
SECTIONS {
 .iram0.text 0x40370000 : { *(.iram1.*.literal) *(.iram1 .iram1.*) }
 .dram0.data 0x3fc90000 : { *(.dram1 .dram1.*) *(.data .data.*) *(.bss .bss.*) }
 .flash.text 0x42000000 : { *(.literal .literal.*) *(.text .text.*) }
 .flash.rodata 0x3c000000 : { *(.rodata .rodata.*) *(.probe_flash) *(.eh_frame*) *(.init_array*) }
}
