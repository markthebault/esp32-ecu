#!/usr/bin/env python3
"""Make an annotation-only SW2 assembly export without editing production CAD.

Run with KiCad9 Python. The output copy spaces two overlapping references and
keeps upper mounting references inside the page. No fit/assembly qualification.
"""
import argparse,hashlib,json,re,subprocess,sys
from pathlib import Path
import pcbnew as pcb
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from kicad9_carrier_copy import chunks
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def xy(p):return [p.x,p.y]
def geometry(board):
 return dict(footprints=sorted((f.GetReference(),xy(f.GetPosition()),f.GetOrientationDegrees(),f.GetLayer(),
  sorted((p.GetNumber(),xy(p.GetPosition()),xy(p.GetSize()),xy(p.GetDrillSize()),p.GetNetname(),p.GetLayerSet().FmtHex())for p in f.Pads()))for f in board.GetFootprints()),
  tracks=sorted((x.GetClass(),xy(x.GetStart()),xy(x.GetEnd()),x.GetWidth(pcb.F_Cu)if isinstance(x,pcb.PCB_VIA)else x.GetWidth(),x.GetLayer(),x.GetNetname())for x in board.GetTracks()),
  zones=[(z.GetNetname(),z.GetLayerSet().FmtHex(),z.Outline().Format(),z.GetFilledPolysList(pcb.B_Cu).Format())for z in board.Zones()])
def without_references(path):
 text=path.read_text()
 for a,b,block in reversed(list(chunks(text,'property'))):
  if re.match(r'\(property\s+"Reference"',block):text=text[:a]+text[b:]
 # Preserve quoted strings exactly while disregarding serialization spacing.
 return re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+',text)
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report-dir',type=Path,required=True);a=p.parse_args();out=a.report_dir.resolve();out.mkdir(parents=True,exist_ok=False)
 source=ROOT/'hardware/switch-inputs/switches.kicad_pcb';original=digest(source);board=pcb.LoadBoard(str(source));before=geometry(board)
 labels={'U1':(41,26),'C1':(50,18),'H1':(14,12),'H2':(86,12),
  'R1':(61.5,28.8),'R3':(70.5,32.5),'R7':(80,29),'R13':(60.8,30),'R20':(17,41)}
 for fp in board.GetFootprints():
  if fp.GetReference()in labels:fp.Reference().SetPosition(pcb.VECTOR2I(*(pcb.FromMM(v)for v in labels[fp.GetReference()])))
 copy=out/'annotation-copy.kicad_pcb';pcb.SaveBoard(str(copy),board)
 if before!=geometry(pcb.LoadBoard(str(copy)))or without_references(source)!=without_references(copy)or digest(source)!=original:raise ValueError('Non-reference data or original source changed')
 svg=out/'assembly.svg';subprocess.run(['kicad-cli','pcb','export','svg',str(copy),'--output',str(svg),'--layers','F.Fab,F.SilkS,Edge.Cuts','--mode-single','--fit-page-to-board','--exclude-drawing-sheet','--sketch-pads-on-fab-layers'],check=True)
 (out/'provenance.json').write_text(json.dumps(dict(source=str(source.relative_to(ROOT)),source_sha256=original,annotation_copy_sha256=digest(copy),plot_sha256=digest(svg),geometry_signature_equal=True,all_nonreference_tokens_equal=True,reference_positions_changed_mm=labels,qualification='Annotation-only export copy; no original CAD change or assembly/fit qualification'),indent=2)+'\n')
 print('Exported spaced reference annotations with unchanged geometry and source')
if __name__=='__main__':main()
