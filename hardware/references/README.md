# User-supplied ESP32 board reference

- `esp32-s3-44pin-aliexpress.pdf`: original 13,041,896-byte listing PDF, copied without modification.
- `esp32-s3-44pin-pinout.png`: original supplied pinout image.
- Listing: https://de.aliexpress.com/item/1005006418608267.html
- User-selected variant: **N16R8 (16 MB flash, 8 MB PSRAM)**. The PDF's cart selection was N8R2 and does not override this choice.

The source mixes board revisions: its pinout image calls GPIO47 the RGB signal, while the schematic calls it GPIO48. Do not infer an onboard LED pin from the product name. Header row spacing, exact board dimensions, USB projection and socket stack height are not dimensioned in these references. The extra 10 mm inward antenna allowance comes from the user's instruction, not a dimensioned manufacturer drawing.
