# Input SVG files

Put your original, unmodified CorelDRAW-exported SVG files here.

The input must already have its garment pieces aligned correctly with the
fabric's length/grain direction. The program takes **fabric width in inches**
from the command line, not from the SVG canvas size. The original file is
never edited.

Example:

```bash
garment-nesting nest "input/your-pattern.svg" --fabric-width-in 36
```
