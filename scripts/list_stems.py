from pathlib import Path
import sys

img_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('.')
for p in img_dir.iterdir():
    if p.is_file():
        print(p.stem)
