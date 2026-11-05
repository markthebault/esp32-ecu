#!/usr/bin/env python3
"""Solve a new-copy courtyard placement problem; no routing/physical claims.

OR-Tools9.14.6206 runs separately from KiCad's system Python. Every candidate
must still pass actual integer-coordinate KiCad geometry/ERC/DRC checks.
"""
import argparse,hashlib,json,math
from pathlib import Path
import ortools
from ortools.sat.python import cp_model

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('problem',type=Path);p.add_argument('output',type=Path);p.add_argument('--seconds',type=float,default=180);p.add_argument('--grid-um',type=int,default=50);p.add_argument('--first',action='store_true');a=p.parse_args()
 if a.output.exists():raise SystemExit('Use a new solution output')
 body=a.problem.read_bytes();digest=hashlib.sha256(body).hexdigest();data=json.loads(body);assert data['schema']==1 and a.grid_um in (1,10,25,50,100)
 m=cp_model.CpModel();scale=1000/a.grid_um;gap=data['gap_mm']/2
 def integer(v):return int(round(v*scale))
 def rect(b):
  x=math.floor((b[0]-gap)*scale+1e-6);y=math.floor((b[1]-gap)*scale+1e-6)
  return[x,y,math.ceil((b[2]+gap)*scale-1e-6)-x,math.ceil((b[3]+gap)*scale-1e-6)-y]
 xs=[];ys=[];objects={};cost=[]
 for ref,row in data['fixed'].items():
  x,y,w,h=rect(row['court_mm']);xs.append(m.new_fixed_size_interval_var(x,w,ref+'_fixed_x'));ys.append(m.new_fixed_size_interval_var(y,h,ref+'_fixed_y'))
 lo_x,lo_y,hi_x,hi_y=map(integer,data['bounds_mm']);rf=list(map(integer,data['antenna_mm']))
 for ref,row in data['movable'].items():
  x=m.new_int_var(lo_x,hi_x,ref+'_x');y=m.new_int_var(lo_y,hi_y,ref+'_y');r=m.new_bool_var(ref+'_rotated');shapes=[]
  for angle,pres in ((0,r.Not()),(90,r)):
   b=row['rotated_courts_mm'][str(angle)];_,_,w,h=rect(b);shapes.append((w,h))
   xs.append(m.new_optional_fixed_size_interval_var(x,w,pres,ref+str(angle)+'x'));ys.append(m.new_optional_fixed_size_interval_var(y,h,pres,ref+str(angle)+'y'))
   m.add(x+w<=hi_x).only_enforce_if(pres);m.add(y+h<=hi_y).only_enforce_if(pres)
   choices=[m.new_bool_var(ref+str(angle)+'rf'+str(i))for i in range(4)]
   m.add(x+w<=rf[0]).only_enforce_if(choices[0]);m.add(x>=rf[2]).only_enforce_if(choices[1]);m.add(y+h<=rf[1]).only_enforce_if(choices[2]);m.add(y>=rf[3]).only_enforce_if(choices[3]);m.add_bool_or([pres.Not(),*choices])
  objects[ref]=(x,y,r,shapes)
  # Origin-distance objective favors existing functional neighborhoods. This
  # does not evaluate wire quality, current, bypass impedance or heat flow.
  b=row['rotated_courts_mm']['0'];preferred=row['desired_origin_mm'];px=integer(preferred[0]+b[0]-gap);py=integer(preferred[1]+b[1]-gap)
  dx=m.new_int_var(0,integer(300),ref+'_dx');dy=m.new_int_var(0,integer(300),ref+'_dy');m.add_abs_equality(dx,x-px);m.add_abs_equality(dy,y-py);cost.extend((dx,dy))
  if lo_x<=px<=hi_x:m.add_hint(x,px)
  if lo_y<=py<=hi_y:m.add_hint(y,py)
  m.add_hint(r,0)
 def pad_expression(ref,pin):
  if ref in data['fixed']:
   return tuple(integer(v)for v in data['fixed'][ref]['absolute_pads_mm'][pin])
  row=data['movable'][ref];x,y,r,_=objects[ref];offsets=[]
  for angle in (0,90):
   b=row['rotated_courts_mm'][str(angle)];q=row['rotated_pads_mm'][str(angle)][pin];offsets.append((integer(gap-b[0]+q[0]),integer(gap-b[1]+q[1])))
  return x+offsets[0][0]+(offsets[1][0]-offsets[0][0])*r,y+offsets[0][1]+(offsets[1][1]-offsets[0][1])*r
 for cap,(owner,pin)in data['bypass'].items():
  a1=pad_expression(cap,'1');a2=pad_expression(owner,pin)
  if a1 is not None and a2 is not None:
   dx=m.new_int_var(0,integer(130),cap+'_bypass_dx');dy=m.new_int_var(0,integer(130),cap+'_bypass_dy');m.add_abs_equality(dx,a1[0]-a2[0]);m.add_abs_equality(dy,a1[1]-a2[1]);m.add(dx+dy<=integer(12.9))
 m.add_no_overlap_2d(xs,ys);m.minimize(sum(cost))
 solver=cp_model.CpSolver();solver.parameters.max_time_in_seconds=a.seconds;solver.parameters.num_search_workers=4;solver.parameters.random_seed=1;solver.parameters.log_search_progress=True;solver.parameters.stop_after_first_solution=a.first
 status=solver.solve(m);assert hashlib.sha256(a.problem.read_bytes()).hexdigest()==digest,'Input changed while solving'
 name=solver.status_name(status);report=dict(status=name,ortools=ortools.__version__,grid_um=a.grid_um,problem_sha256=digest,wall_seconds=solver.wall_time,qualification=__doc__,positions={})
 if status in (cp_model.OPTIMAL,cp_model.FEASIBLE):
  report['objective']=solver.objective_value
  for ref,(x,y,r,_)in objects.items():
   angle=90 if solver.value(r)else 0;b=data['movable'][ref]['rotated_courts_mm'][str(angle)]
   report['positions'][ref]=dict(xy_mm=[solver.value(x)/scale+gap-b[0],solver.value(y)/scale+gap-b[1]],angle_deg=angle)
 a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status=name,placed=len(report['positions']),output=str(a.output))))
 if status not in (cp_model.OPTIMAL,cp_model.FEASIBLE):raise SystemExit(1)

if __name__=='__main__':main()
