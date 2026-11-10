"""Regenerate the Phoebus displays after changing PV lists."""
from pathlib import Path
import sys
import xml.etree.ElementTree as E
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from archiver import load_settings
ROOT = Path(__file__).resolve().parents[1]
_, _, pvs, _ = load_settings(ROOT/'settings/settings.yaml')


def prop(parent, key, value):
    e=E.SubElement(parent,key);e.text=str(value);return e


def display(name,w,h):
    r=E.Element('display',version='2.0.0')
    for k,v in [('name',name),('width',w),('height',h)]:prop(r,k,v)
    m=E.SubElement(r,'macros');prop(m,'P','UNH:GEN:ARCH');prop(m,'INTERVAL','UNH:GEN:ARCH:SaveInterval')
    return r


def widget(r,kind,name,x,y,w,h,**props):
    e=E.SubElement(r,'widget',type=kind,version='3.0.0')
    for k,v in dict(name=name,x=x,y=y,width=w,height=h,**props).items():prop(e,k,v)
    return e


def label(r,text,x,y,w=600,h=28):return widget(r,'label',text,x,y,w,h,text=text)
def write_button(r,text,pv,value,x,y,w=170):
    e=widget(r,'action_button',text,x,y,w,30,text=text)
    a=E.SubElement(E.SubElement(e,'actions'),'action',type='write_pv');prop(a,'pv_name','ca://'+pv);prop(a,'value',value)
    return e


def open_button(r,text,file,x,y):
    e=widget(r,'action_button',text,x,y,190,30,text=text)
    a=E.SubElement(E.SubElement(e,'actions'),'action',type='open_display');prop(a,'file',file);prop(a,'target','tab')

r=display('Genesis Slow Controls Archiver',1100,790)
label(r,'UNH Genesis — Slow Controls Archiver',25,18,1000,35)
label(r,'Seconds between saves',25,75,210)
widget(r,'textentry','SaveInterval',240,73,130,30,pv_name='ca://$(INTERVAL)',precision=3)
label(r,'Enter a positive value; changes apply immediately. Default: 1 s.',395,76,680)
label(r,'CSV history',25,135,800)
label(r,'Channel',25,180,90)
widget(r,'textentry','HistoryPV',120,178,680,30,pv_name='ca://$(P):HistoryPV')
open_button(r,'Choose channel…','archiver_channels.bob',825,178)
label(r,'Window (hours)',25,225,150)
widget(r,'textentry','HistoryHours',180,223,100,30,pv_name='ca://$(P):HistoryHours')
label(r,'End: hours ago',310,225,160)
widget(r,'textentry','HistoryOffsetHours',475,223,100,30,pv_name='ca://$(P):HistoryOffsetHours')
write_button(r,'Load / Refresh','$(P):HistoryLoad',1,825,223,190)
label(r,'0 hours ago ends now. History loads on request; recording continues.',25,265,1000)
widget(r,'textupdate','HistoryStatus',25,300,1000,28,pv_name='ca://$(P):HistoryStatus')
label(r,'UTC start',25,340,100)
widget(r,'textupdate','HistoryStartUTC',130,340,340,28,pv_name='ca://$(P):HistoryStartUTC')
label(r,'UTC end',535,340,100)
widget(r,'textupdate','HistoryEndUTC',635,340,400,28,pv_name='ca://$(P):HistoryEndUTC')
e=widget(r,'xyplot','CSVHistory',25,385,1040,350,title='Saved CSV values',show_toolbar='true')
x=E.SubElement(e,'x_axis');prop(x,'title','Hours relative to window end');prop(x,'autoscale','true');prop(x,'show_grid','true')
y=E.SubElement(E.SubElement(e,'y_axes'),'y_axis');prop(y,'title','Recorded value (channel units)');prop(y,'autoscale','true');prop(y,'show_grid','true')
t=E.SubElement(E.SubElement(e,'traces'),'trace')
for k,v in [('name','History'),('x_pv','ca://$(P):HistoryX'),('y_pv','ca://$(P):HistoryY'),('axis',0),('trace_type',0),('point_type',2),('point_size',2),('line_width',1)]:prop(t,k,v)
label(r,'Displays up to the latest 10,000 rows in the window. Saved CSVs are unchanged.',25,750,1000)

picker=display('Archive History — Choose Channel',1200,1080)
label(picker,'Choose a channel, then return to Archiver and click Load / Refresh.',20,15,1150)
for i,pv in enumerate(pvs):
    col,row=divmod(i,28)
    write_button(picker,pv,'$(P):HistoryPV',pv,15+col*395,60+row*35,385)
for name,root in [('archiver.bob',r),('archiver_channels.bob',picker)]:
    E.indent(root);E.ElementTree(root).write(ROOT/'gui'/name,encoding='UTF-8',xml_declaration=True)
