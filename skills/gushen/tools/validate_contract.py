#!/usr/bin/env python3
import sys
from pathlib import Path
required = ["巴菲特","芒格","段永平","李录","技术分析师","动量交易员","情绪分析师","风控官","data-gate","value-gate","trading-gate","cross-check","decision-gate"]
text = Path(sys.argv[1] if len(sys.argv)>1 else str(Path(__file__).resolve().parent.parent / "references/execution-contract.md")).read_text(encoding='utf-8')
missing=[x for x in required if x not in text]
if missing: print('CONTRACT_INVALID missing='+','.join(missing)); raise SystemExit(1)
print('CONTRACT_VALID agents=8 gates=5')
