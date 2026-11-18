"""Regenerate screens from adjacent subsystem settings; directory-name independent."""
from pathlib import Path
import importlib.util
import importlib
import xml.etree.ElementTree as E
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('_recording_launcher',ROOT/'run.py')
launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)
config=importlib.import_module(launcher.load_package()+'.tools.config')


def prop(p,k,v):e=E.SubElement(p,k);e.text=str(v);return e

def display(name,w=1120,h=810,prefix=''):
 r=E.Element('display',version='2.0.0')
 for k,v in dict(name=name,width=w,height=h).items():prop(r,k,v)
 prop(E.SubElement(r,'macros'),'P',prefix)
 return r

def widget(r,kind,name,x,y,w,h,**kw):
 e=E.SubElement(r,'widget',type=kind,version='3.0.0')
 for k,v in dict(name=name,x=x,y=y,width=w,height=h,**kw).items():prop(e,k,v)
 return e

def label(r,text,x,y,w=1000):return widget(r,'label',text,x,y,w,28,text=text)

def entry(r,name,x,y,w=120):return widget(r,'textentry',name,x,y,w,30,pv_name='ca://$(P):'+name)

def update(r,name,x,y,w=360):return widget(r,'textupdate',name,x,y,w,28,pv_name='ca://$(P):'+name)

def action(r,text,kind,pv_or_file,value,x,y,w=190):
 e=widget(r,'action_button',text,x,y,w,30,text=text)
 a=E.SubElement(E.SubElement(e,'actions'),'action',type=kind)
 if kind=='write_pv':prop(a,'pv_name','ca://$(P):'+pv_or_file);prop(a,'value',value)
 else:prop(a,'file',pv_or_file);prop(a,'target','tab')
 return e

def plot(r,name,x,y,w,h,xpv,ypv,xtitle,ytitle):
 e=widget(r,'xyplot',name,x,y,w,h,title=name,show_toolbar='true')
 axis=E.SubElement(e,'x_axis');prop(axis,'title',xtitle);prop(axis,'autoscale','true');prop(axis,'show_grid','true')
 axis=E.SubElement(E.SubElement(e,'y_axes'),'y_axis');prop(axis,'title',ytitle);prop(axis,'autoscale','true');prop(axis,'show_grid','true')
 trace=E.SubElement(E.SubElement(e,'traces'),'trace')
 for k,v in dict(name=name,x_pv='ca://$(P):'+xpv,y_pv='ca://$(P):'+ypv,axis=0,trace_type=0,line_width=1,point_type=2,point_size=2).items():prop(trace,k,v)

def save(root,name):
 E.indent(root);E.ElementTree(root).write(ROOT/'gui'/name,encoding='UTF-8',xml_declaration=True)

main=display('Genesis Archive',600,300)
label(main,'Genesis subsystem recorders',25,20,560)
for i,name in enumerate(config.SUBSYSTEMS):
 cfg=config.load(name)
 action(main,name.title(),'open_display',name+'.bob',None,25,65+i*45,540)
 r=display(name.title()+' recording and history',prefix=cfg['control_prefix'])
 label(r,name.title()+' — recording and saved history',25,20)
 label(r,'Normal save interval (s)',25,70,240);entry(r,'SaveInterval',270,68)
 label(r,'Effective interval (s)',440,70,230);update(r,'EffectiveInterval',680,70,160)
 label(r,'Channel',25,130,100);entry(r,'HistoryPV',130,128,670)
 action(r,'Choose channel','open_display',name+'_channels.bob',None,850,128)
 label(r,'Window (hours)',25,180,155);entry(r,'HistoryHours',190,178)
 label(r,'End: hours ago',355,180,165);entry(r,'HistoryOffsetHours',530,178)
 action(r,'Load / Refresh','write_pv','HistoryLoad',1,850,178)
 update(r,'HistoryStatus',25,225,1000)
 label(r,'UTC start',25,265,110);update(r,'HistoryStartUTC',140,265)
 label(r,'UTC end',570,265,100);update(r,'HistoryEndUTC',680,265)
 plot(r,'Saved data',25,310,1060,410,'HistoryX','HistoryY','Hours relative to window end','Recorded value (channel units)')
 label(r,'History loads on request. Up to 10,000 rows are displayed.',25,745)
 action(r,'All subsystems','open_display','overview.bob',None,25,775)
 if name=='ssrf':action(r,'Burn waveforms','open_display','ssrf_burns.bob',None,850,775)
 save(r,name+'.bob')
 rows=28;columns=(len(cfg['pvs'])+rows-1)//rows
 picker=display(name.title()+' channels',columns*400+25,1050,prefix=cfg['control_prefix'])
 label(picker,'Select a channel, then return to history and Load / Refresh.',20,15,columns*400)
 for j,pv in enumerate(cfg['pvs']):
  col,row=divmod(j,rows)
  action(picker,pv,'write_pv','HistoryPV',pv,15+400*col,60+35*row,390)
 save(picker,name+'_channels.bob')
 if name=='ssrf':
  burn=display('ssRF saved burns',1120,750,cfg['control_prefix'])
  label(burn,'ssRF — waveform saved in the burn log',25,20)
  label(burn,'Burn index (0 = most recent)',25,70,300);entry(burn,'BurnIndex',340,68)
  action(burn,'Load burn','write_pv','BurnLoad',1,850,68)
  update(burn,'BurnStatus',25,120,1000);update(burn,'BurnID',25,160,500);update(burn,'BurnStartUTC',580,160,500)
  plot(burn,'Saved burn waveform',25,220,1060,420,'BurnX','BurnY','Time since waveform start (s)','Waveform (V)')
  action(burn,'ssRF snapshots','open_display','ssrf.bob',None,25,680)
  save(burn,'ssrf_burns.bob')
save(main,'overview.bob')
