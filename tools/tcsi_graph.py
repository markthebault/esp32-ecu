"""Execute supported scalar algebra directly from the pinned TCSI MDL graph.

Masks are data-only parameters. MATLAB initialization/code, dynamic blocks,
unlisted operations and algebraic cycles fail explicitly. This adapter is for
source-component checks, not a claim that a complete Simulink model executes.
"""
import ast,math,operator,re
from tcsi_mdl import CACHE,load,systems

class Unsupported(ValueError):pass

def expression(text,env,u=None):
 """Evaluate only declared numeric operators/fields, never Python eval."""
 tree=ast.parse(text.replace('^','**'),mode='eval').body
 def field(n):
  if isinstance(n,ast.Name):return n.id
  if isinstance(n,ast.Attribute):return field(n.value)+'.'+n.attr
  raise Unsupported('Unsupported parameter reference')
 def number(n):
  if isinstance(n,ast.Constant) and type(n.value) in (float,int,str):return n.value
  if isinstance(n,(ast.Name,ast.Attribute)):
   key=field(n)
   if key=='u':
    if u is None:raise Unsupported('No Fcn input')
    return u
   if key in env:return env[key]
   if key in ('pi','inf','Inf','eps'):return dict(pi=math.pi,inf=math.inf,Inf=math.inf,eps=2**-52)[key]
   raise Unsupported('Unknown parameter '+key)
  if isinstance(n,ast.UnaryOp) and type(n.op) in (ast.USub,ast.UAdd):return -number(n.operand) if isinstance(n.op,ast.USub) else +number(n.operand)
  binary={ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul,ast.Div:operator.truediv,ast.Pow:operator.pow}
  if isinstance(n,ast.BinOp) and type(n.op) in binary:return binary[type(n.op)](number(n.left),number(n.right))
  if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and not n.keywords:
   name=n.func.id;args=[number(a) for a in n.args]
   if name=='u':
    if u is None or len(args)!=1 or type(args[0]) is not int or args[0]<1:raise Unsupported('Invalid one-based Fcn input')
    return (u if isinstance(u,tuple) else (u,))[args[0]-1]
   functions=dict(sqrt=math.sqrt,exp=math.exp,log=math.log,abs=abs,min=min,max=max,sin=math.sin,cos=math.cos)
   if name in functions:return functions[name](*args)
  raise Unsupported('Unsupported parameter/Fcn expression: '+text)
 return number(tree)

def parameters(cache=CACHE):
 result={}
 for line in (cache/'source/EngineData.m').read_text().splitlines():
  line=line.split('%',1)[0].strip()
  if not line:continue
  match=re.fullmatch(r'([A-Za-z]\w*(?:\.\w+)*)\s*=\s*(.*?)\s*;',line)
  if not match:raise Unsupported('Unsupported EngineData statement: '+line)
  name,value=match.groups();result[name]=expression(value,result)
 return result

def mask_parameters(block,parent):
 result=dict(parent)
 def parameter(p):
  name=p.get('Name');value=p.get('Value')
  if name is None or value is None:raise Unsupported('Incomplete mask parameter')
  result[name]=expression(value,parent)
 def visit(node):
  for child in node.children:
   if child.kind=='System':continue
   if child.get('Initialization') or child.get('MaskInitialization'):raise Unsupported('Mask initialization code is unsupported')
   if child.get('$ClassName')=='Simulink.MaskParameter':parameter(child)
   elif child.get('Type')=='Simulink.MaskParameter':
    if child.kind=='Array':
     for p in child.nodes('Object'):parameter(p)
    elif child.kind=='Object':parameter(child)
   visit(child)
 if block is not None:visit(block)
 return result

class Model:
 def __init__(self,cache=CACHE,parameter_inputs=None):
  self.tree,self.provenance=load(cache);self.parameters=parameters(cache)
  external=parameter_inputs or {}
  declared=set(re.findall(r'^\s*(toggle_\w+)\s*=',(cache/'source/RunEngine.m').read_text(),re.M))
  if set(external)-declared or set(external)&set(self.parameters) or any(type(v) not in (int,float) or v not in (0,1) for v in external.values()):raise Unsupported('Only declared external fault toggles0/1 may be supplied')
  self.parameters.update(external);self.provenance['external_parameters']=dict(external)
  self.defaults={b.get('BlockType'):b for b in self.tree.one('Model').one('BlockParameterDefaults').nodes('Block')}
  self.systems={path:(system,block) for path,system,block in systems(self.tree)}
 def setting(self,block,name):
  value=block.get(name)
  if value is None:
   default=self.defaults.get(block.get('BlockType'));value=default.get(name) if default is not None else None
  if value is None:raise Unsupported(f'Missing {name} at source line{block.line}')
  return value
 def graph(self,path):
  path=tuple(path);env=self.parameters
  for n in range(1,len(path)+1):env=mask_parameters(self.systems[path[:n]][1],env)
  return Graph(self,*self.systems[path],env,path)

class Graph:
 def __init__(self,model,system,block,env,path):
  self.model=model;self.system=system;self.env=env;self.path=path
  self.blocks={b.get('Name'):b for b in system.nodes('Block')}
  if len(self.blocks)!=len(system.nodes('Block')):raise Unsupported('Duplicate source block name')
  self.links={}
  def link(line,source=None):
   if line.get('SrcBlock') is not None:source=(line.get('SrcBlock'),int(line.get('SrcPort')))
   if line.get('DstBlock') is not None:
    dest=(line.get('DstBlock'),int(line.get('DstPort')))
    if source is None or dest in self.links:raise Unsupported('Missing/ambiguous source link')
    self.links[dest]=source
   for branch in line.nodes('Branch'):link(branch,source)
  for line in system.nodes('Line'):link(line)
  self.inputs={int(self.setting(b,'Port')):b.get('Name') for b in self.blocks.values() if b.get('BlockType')=='Inport'}
  self.outputs={int(self.setting(b,'Port')):b.get('Name') for b in self.blocks.values() if b.get('BlockType')=='Outport'}
  for kind,ports in (('Inport',self.inputs),('Outport',self.outputs)):
   if len(ports)!=sum(b.get('BlockType')==kind for b in self.blocks.values()) or set(ports)!=set(range(1,len(ports)+1)):raise Unsupported('Duplicate or noncontiguous source ports')
  self.children={name:Graph(model,b.one('System'),b,mask_parameters(b,env),path+(name,)) for name,b in self.blocks.items() if b.get('BlockType')=='SubSystem'}
  self.numeric={}
  self.integrators={name for name,b in self.blocks.items() if b.get('BlockType')=='Integrator'}
 def setting(self,b,key):return self.model.setting(b,key)
 def initial_states(self):return {name:expression(self.setting(self.blocks[name],'InitialCondition'),self.env) for name in self.integrators}
 def run(self,inputs,states=None,derivatives=False,output_ports=None,time_s=None):
  if self.integrators and (states is None or set(states)!=self.integrators):raise Unsupported('Explicit source integrator state boundaries required')
  if states is not None and set(states)!=self.integrators:raise Unsupported('Source state set differs')
  if not isinstance(inputs,dict):
   if len(inputs)!=len(self.inputs):raise Unsupported('Input count differs from source')
   inputs=dict(zip(sorted(self.inputs),inputs))
  if set(inputs)!=set(self.inputs):raise Unsupported('Input port set differs from source')
  cache={};pending=set()
  def value(name,port=1):
   key=(name,port)
   if key in cache:return cache[key]
   if key in pending:raise Unsupported('Algebraic cycle at '+repr(self.path+(name,)))
   pending.add(key);b=self.blocks[name];kind=b.get('BlockType')
   def get(n=1):
    if (name,n) not in self.links:raise Unsupported(f'Unconnected port{n} at line{b.line}')
    return value(*self.links[name,n])
   def parameter(field):
    key=(name,field)
    if key not in self.numeric:self.numeric[key]=expression(self.setting(b,field),self.env)
    return self.numeric[key]
   if kind=='Inport':result=inputs[int(self.setting(b,'Port'))]
   elif kind=='Integrator':result=states[name]
   elif kind=='Outport':result=get()
   elif kind=='Constant':result=parameter('Value')
   elif kind=='Gain':result=get()*parameter('Gain')
   elif kind=='Sum':
    signs=self.setting(b,'Inputs').replace('|','');signs='+'*int(signs) if signs.isdigit() else signs
    if not signs or set(signs)-set('+-'):raise Unsupported('Unsupported Sum signs')
    result=sum(get(n+1)*(1 if sign=='+' else -1) for n,sign in enumerate(signs))
   elif kind=='Product':
    signs=self.setting(b,'Inputs');signs='*'*int(signs) if signs.isdigit() else signs
    if not signs or set(signs)-set('*/'):raise Unsupported('Unsupported Product signs')
    result=1.
    for n,sign in enumerate(signs):result=result*get(n+1) if sign=='*' else result/get(n+1)
   elif kind=='Math':
    op=self.setting(b,'Operator')
    if op=='square':result=get()**2
    elif op=='sqrt':result=math.sqrt(get())
    elif op=='pow':result=get()**get(2)
    elif op=='exp':result=math.exp(get())
    else:raise Unsupported('Unsupported Math '+op)
   elif kind=='MinMax':
    op=self.setting(b,'Function');count=int(self.setting(b,'Inputs'))
    if op not in ('min','max'):raise Unsupported('Unsupported MinMax')
    result=(min if op=='min' else max)(get(n+1) for n in range(count))
   elif kind=='Saturate':result=max(parameter('LowerLimit'),min(parameter('UpperLimit'),get()))
   elif kind=='SubSystem':
    child=self.children[name]
    outputs=child.run({p:get(p) for p in child.inputs},time_s=time_s);cache.update({(name,p):v for p,v in outputs.items()});result=outputs[port]
   elif kind=='Fcn':result=expression(self.setting(b,'Expr'),self.env,get())
   elif kind=='Mux':result=tuple(get(n+1) for n in range(int(self.setting(b,'Inputs'))))
   elif kind=='Demux':result=get()[port-1]
   elif kind=='Abs':result=abs(get())
   elif kind=='Signum':result=(get()>0)-(get()<0)
   elif kind=='RelationalOperator':
    op=self.setting(b,'Operator');operations={'<':operator.lt,'>':operator.gt,'<=':operator.le,'>=':operator.ge,'==':operator.eq,'~=':operator.ne}
    if op not in operations:raise Unsupported('Unsupported relation '+op)
    result=operations[op](get(),get(2))
   elif kind=='DataTypeConversion':
    if self.setting(b,'OutDataTypeStr')!='double':raise Unsupported('Only explicit source double conversion is supported')
    result=float(get())
   elif kind=='MultiPortSwitch':
    if self.setting(b,'DataPortOrder')!='One-based contiguous':raise Unsupported('Unsupported source switch indexing')
    index=get();count=int(self.setting(b,'Inputs'))
    if not isinstance(index,(int,float)) or int(index)!=index or not 1<=index<=count:raise Unsupported('Invalid source switch control')
    result=get(int(index)+1)
   elif kind=='DiscretePulseGenerator':
    if self.setting(b,'PulseType')!='Time based' or type(time_s) not in (int,float) or not math.isfinite(time_s) or time_s<0:raise Unsupported('Explicit current time required for source time-based pulse')
    period=parameter('Period');width=parameter('PulseWidth');phase=parameter('PhaseDelay');amplitude=parameter('Amplitude')
    if period<=0 or not 0<=width<=100:raise Unsupported('Invalid source pulse parameters')
    result=amplitude if time_s>=phase and (time_s-phase)%period<period*width/100 else 0.
   else:raise Unsupported(f'Unsupported executable block{kind} at line{b.line}')
   values=result if isinstance(result,tuple) else (result,)
   if any(type(v) not in (int,float,bool) or not math.isfinite(v) for v in values):raise ValueError('Invalid/non-finite source graph result at '+repr(self.path+(name,)))
   pending.remove(key);cache[key]=result;return result
  wanted=set(self.outputs) if output_ports is None else set(output_ports)
  if not wanted<=set(self.outputs):raise Unsupported('Requested unknown source output port')
  outputs={port:value(name) for port,name in self.outputs.items() if port in wanted}
  if derivatives:return outputs,{name:value(*self.links[name,1]) for name in sorted(self.integrators)}
  return outputs
