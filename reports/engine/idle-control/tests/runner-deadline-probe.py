from pathlib import Path
import sys,json
sys.path.insert(0,str(Path('tools').resolve()))
s=Path('.cache/engine/idle-plant-review/probe_runner_deadline.py').read_text();a=s.index('base=');b=s.index('import engine_sil',a);s=s[:a]+"base=Path('.cache/engine/idle');snapshot=Path('.');\n"+s[b:]
exec(compile(s,'review_probe_current','exec'))
