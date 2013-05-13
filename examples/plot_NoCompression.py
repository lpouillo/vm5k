#!/usr/bin/env python
# -*- coding: UTF-8 -*-
import numpy as np
import os
import pylab as P
from time import localtime, strftime
from pprint import pformat, pprint
from execo_engine import slugify
from execo.time_utils import unixts_to_datetime
import matplotlib.dates as MD


dt_theory = np.dtype( {'names': ['cpu_load', 'mem_size', 'mig_bw', 'mem_update_ratio', 'mem_update_rate', 'duration'],
                    'formats': [np.int, np.int, np.int, np.float, np.float, np.float]})
with open('single-mig.out-raw') as f:
    simulation = np.loadtxt(f, dtype = dt_theory, comments = "#", skiprows = 0)

result_dir = 'NoCompressionMigration_20130417_152218_+0200/'
result_dir = 'NoCompressionMigration_20130503_114229_+0200/'

try:
    os.mkdir(result_dir+'graphs')
except:
    pass

xfmt = MD.DateFormatter('%H:%M:%S')
x_major_locator = P.MaxNLocator(5)

results = {}
ax_duration = {}
n_comb = 0
max_duration = 0
list_comb = os.listdir(result_dir)
for ignore in [ 'sweeps', 'stdout+stderr', 'graphs', 'errors' ]:
    if ignore in list_comb:
        list_comb.remove(ignore)
n_error = 0

for comb in list_comb:
    n_comb += 1
    comb_dir = comb+'/'
    print n_comb, comb_dir
    k = comb_dir.replace('/',' ').split('-')
    i = iter(k)
    params = dict(zip(i,i))
    
    comb_res = os.listdir(result_dir+comb_dir)
    
    mig_type = []
    for infile in comb_res:
        if 'ping' not in infile: 
            mig_type = mig_type + [infile.split('_')[0]] if infile.split('_')[0] not in mig_type else mig_type
            
        
    n_mig = 3
    
    dt = np.dtype( {'names': ['timestamp', 'vm-id', 'measure', 'duration'],
                    'formats': [np.int, '|S4', np.int, np.float]})
    fig = P.figure(figsize=(5*n_mig, 10), dpi=80, )
    ax_ping = P.subplot2grid( (2, n_mig), (1,0), colspan = n_mig)
    
    data = {}
    i_mig = 0
    error = False
    for infile in comb_res:
        if 'ping' not in infile:
            mig = infile.split('_')[0]
            with open(result_dir + comb_dir + infile) as f:
                try:
                    if not data.has_key(mig):
                        data[mig] = np.loadtxt(f, dtype = dt, comments = "#", skiprows = 0)
                    else:
                        data[mig] = np.concatenate((data[mig], np.loadtxt(f, dtype = dt, comments = "#", skiprows = 0)))
                    f.close()
                except:
                    n_error += 1
                    print 'Error during measurements '+str(n_error)
                    error = True
                    pass  
    if not error: 
        src = []
        dst = []
                
        for vals in data['ONE']:
            if vals[2] % 2 == 0:
                src.append( vals )
            else:
                dst.append( vals ) 
        
        data['SRC'] = np.array(src, dtype = dt)
        data['DST'] = np.array(dst, dtype = dt)
        del data['ONE']
        
        
        i_mig = 0
        dur_min = 1000
        dur_max = 0
        for mig in [ 'SRC', 'DST', 'BOTH']:
            print data[mig]['duration']
            dur_min = min( min(data[mig]['duration']), dur_min)
            dur_max = max( max(data[mig]['duration']), dur_max)
            mean = data[mig]['duration'].mean()
            std = data[mig]['duration'].std()
            median = np.median(data[mig]['duration'])
            print mig, median
            
            ax_duration[mig] = P.subplot2grid( (2, n_mig), (0, i_mig), title = mig)
            lmean = ax_duration[mig].axhline(y = mean, color = 'r', label = 'mean='+str(mean))
            lmed = ax_duration[mig].axhline(y = median, color = 'b', label = 'median='+str(median))
            ax_duration[mig].axhline(y = mean+std, color = 'r', linestyle='--', label='std='+str(std))
            ax_duration[mig].axhline(y = mean-std, color = 'r', linestyle='--')
            ax_duration[mig].plot(data[mig]['measure'], data[mig]['duration'], 'o')
            ax_duration[mig].set_xlabel('Measure')
            ax_duration[mig].set_ylabel('Migration time (s)')
            ax_duration[mig].yaxis.set_major_locator(P.MaxNLocator(10))
        
            mig_bw = int(params['mig_bw'])
            rate = int(params['mem_update_rate'])
            mem_size = int(params['mem_size'])
            cpu_load = int(params['cpu_load'])
            
            if not results.has_key(cpu_load):
                results[cpu_load] = {}
            if not results[cpu_load].has_key(mig_bw):
                results[cpu_load][mig_bw] = {}
            if not results[cpu_load][mig_bw].has_key(mem_size):
                results[cpu_load][mig_bw][mem_size] = {}
            if not results[cpu_load][mig_bw][mem_size].has_key(rate):
                results[cpu_load][mig_bw][mem_size][rate] = {}
            if not results[cpu_load][mig_bw][mem_size][rate].has_key(mig):
                results[cpu_load][mig_bw][mem_size][rate][mig] = {'duration': float(median), 'stdev': std } 
        
    
fig = P.figure(figsize=(15, 10), dpi=150, )
ax = fig.add_subplot(111)

SRC = []
SRCerr = []
DST = []
BOTH = []
BOTHerr = []

n_done = 0

cpu_height = 600
for cpu_load in [ 0, 1, 2, 3 ]:
    min_cpu = len(SRC)
    mem_height = 500
    for mem_size in [ 2048, 4096, 8192 ]:        
        min_mem = len(SRC)         
        for mig_bw in [ 32, 125 ]:
            for mem_update in [0, 10, 25, 50, 75]:
                print len(SRC), cpu_load, mig_bw, mem_size, mem_update
                
                if results.has_key(cpu_load) and results[cpu_load].has_key(mig_bw) and results[cpu_load][mig_bw].has_key(mem_size) and results[cpu_load][mig_bw][mem_size].has_key(mem_update):
                    SRC.append( results[cpu_load][mig_bw][mem_size][mem_update]['SRC']['duration'] )
                    SRCerr.append( results[cpu_load][mig_bw][mem_size][mem_update]['SRC']['stdev'] )
                    DST.append( results[cpu_load][mig_bw][mem_size][mem_update]['DST']['duration'] )
                    BOTH.append( results[cpu_load][mig_bw][mem_size][mem_update]['BOTH']['duration'] )
                    BOTHerr.append( results[cpu_load][mig_bw][mem_size][mem_update]['BOTH']['stdev'] )
                    print results[cpu_load][mig_bw][mem_size][mem_update]['SRC']
                    n_done += 1
                else:
                    SRC.append( 0 )
                    SRCerr.append( 0 )
                    DST.append( 0 )
                    BOTH.append( 0 )
                    BOTHerr.append( 0 )
                    print 0
        mem_height += 10
        print mem_height, min_mem, len(SRC)
        a = ax.axhline(y = mem_height, xmin = min_mem/120., xmax = len(SRC)/120.,  color = 'k')
        print (len(SRC)-min_mem)/240.
        ax.text( x = min_mem + (len(SRC)-min_mem)/240., y = mem_height+5,s = str(mem_size))
    cpu_height += 10
    print cpu_height, min_cpu, len(SRC)    
    ax.axhline(y = cpu_height, xmin = min_cpu/120., xmax = len(SRC)/120.,  color = 'k')
    ax.text( x = min_cpu + (len(SRC)-min_cpu)/240., y = cpu_height+5,s = str(cpu_load)+' VM')
    
N = len(SRC)
ind = np.arange(N)
width = 0.45
rects1 = P.bar(ind, SRC, width, color = 'r', edgecolor = 'none', label = 'SRC', yerr = SRCerr)
rects4 = P.bar(ind+width, simulation['duration'], width, color = 'k', edgecolor = 'none', label = 'Simu')
ax.yaxis.grid( color = 'black', linestyle = 'dashed' )
ax.set_ylim([0, 900])

P.legend()
P.savefig('loop_param.png', dpi=300, bbox_inches='tight')
print strftime('%d/%m/%y %H:%M',localtime())
print float(n_done)/float(len(SRC))
 
