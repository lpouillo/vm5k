#!/usr/bin/env python
# -*- coding: UTF-8 -*-
import numpy as np
import os
import time
import pylab as P
from pprint import pformat, pprint
from execo_engine import slugify
from execo.time_utils import unixts_to_datetime
from collections import OrderedDict
import matplotlib.dates as MD

result_dir = 'MicroArchMigration_20130417_103254_+0200/'

list_comb = os.listdir(result_dir)
for ignore in [ 'sweeps', 'stdout+stderr' ]:
    list_comb.remove(ignore)

results = {}



for mem_case in [ 1024, 2048, 4096 ]:
    n_comb = 0    
    for comb in list_comb:
        n_comb += 1
        comb_dir = comb+'/'
        #print n_comb, comb_dir
        k = comb_dir.replace('/',' ').split('-')
        i = iter(k)
        params = dict(zip(i,i))
        
        comb_res = os.listdir(result_dir+comb_dir)
        
        data = {}
        for infile in comb_res:
            dt = np.dtype( {'names': ['timestamp', 'vm-id', 'measure', 'duration'],
                            'formats': [np.int, '|S4', np.int, np.float]})
            if '.out' in infile:
                mig = infile.split('_')[0]
                with open(result_dir + comb_dir + infile) as f:
                    if not data.has_key(mig):
                        data[mig] = np.loadtxt(f, dtype = dt, comments = "#", skiprows = 0)
                    else:
                        data[mig] = np.concatenate((data[mig], np.loadtxt(f, dtype = dt, comments = "#", skiprows = 0)))
                    f.close()
             
        for mig, data_mig in data.iteritems():
            if len(data_mig)>0:
                if 'PARA' in mig:
                    paradt = np.dtype( {'names': [ 'measure', 'duration'],
                            'formats': [ np.int, np.float]})
                    newdata = []
                    n_mes = len(data[mig])/int(params['n_vm'])
                    
                    for i_mes in range(n_mes):
                        tmpdata = []
                        for value in data[mig]:
                            if i_mes == value[2]:
                                tmpdata.append(value[3])
                        newdata.append(max(tmpdata)/int(params['n_vm']))
                    data[mig] = np.array([(i, newdata[i]) for i in range(len(newdata))] , dtype = paradt )
                mean = data[mig]['duration'].mean()
                std = data[mig]['duration'].std()
                median = np.median(data[mig]['duration'])            
    
                mapping = params['mapping']
                n_vm = int(params['n_vm'])
                n_cpu = int(params['n_cpu'])
                
                mem_size = int(params['mem_size'])
                
                
                
                if not results.has_key(mapping):
                    results[mapping] = {}
                if not results[mapping].has_key(n_vm):
                    results[mapping][n_vm] = {}
                if not results[mapping][n_vm].has_key(n_cpu):
                    results[mapping][n_vm][n_cpu] = {}
                if not results[mapping][n_vm][n_cpu].has_key(mig):               
                    results[mapping][n_vm][n_cpu][mig] = { 'mem_size': [], 'duration': [], 'stdev': [] }
                
                
                if mem_size == mem_case:
                    results[mapping][n_vm][n_cpu][mig]['mem_size'].append( mem_size )
                    results[mapping][n_vm][n_cpu][mig]['duration'].append( float(mean) )
                    #print data[mig]['duration']
                    #results[mapping][n_vm][n_cpu][mig]['duration'].append(data[mig][0]['duration'])
                    results[mapping][n_vm][n_cpu][mig]['stdev'].append( float(std) )
    
    
    base_colors = 'bgrcmykw'
    mapping_colors = {}
    for idx, n_cpu in enumerate(results.iterkeys()):
        mapping_colors[n_cpu] = base_colors[idx] 
    
    #print mapping_colors
    
    
    base_symbol = 'osdp'
    n_vm_symbol = {}
    for idx, mig in enumerate([ 1, 2, 4 ]):
        n_vm_symbol[mig] = base_symbol[idx]
    #print n_vm_symbol
    
    fig = P.figure(figsize=(15, 10), dpi=150)
    fig.suptitle( 'Experiments on cluster '+params['cluster'])
    
    n_n_vm = 2
    n_mig = 2
    
    
    n_points = 0
    for mapping in results.iterkeys():
        for n_vm in results[mapping].iterkeys():
            for n_cpu in results[mapping][n_vm].iterkeys():
                for mig in results[mapping][n_vm][n_cpu].iterkeys():
                
                    ax = P.subplot( n_n_vm, n_mig, ([1, 2].index(n_vm)*n_n_vm)+(['SEQ', 'PARA'].index(mig)+1))
                    if len( results[mapping][n_vm][n_cpu][mig]['duration'] ) == 1:
                        ax.scatter(n_cpu, results[mapping][n_vm][n_cpu][mig]['duration'], 
                              c = mapping_colors[mapping], marker = n_vm_symbol[n_vm], label = mapping)
                        n_points += 1
            #            ax.errorbar(n_cpu, results[mapping][n_vm][n_cpu][mig]['duration'], 
            #                        yerr = results[mapping][n_vm][n_cpu][mig]['stdev'])
                
                
    for n_vm in [1, 2]:
        for mig in ['SEQ', 'PARA']:
            ax = P.subplot( n_n_vm, n_mig, ([1, 2].index(n_vm)*n_n_vm)+(['SEQ', 'PARA'].index(mig)+1))
            handles, labels = ax.get_legend_handles_labels()
            by_label = OrderedDict(zip(labels, handles))
            ax.legend(by_label.values(), by_label.keys(), loc = 'upper left', prop = {'size': 10}, scatterpoints = 1)
            ax.set_title('n_vm = '+str(n_vm)+', mig='+mig)
            ax.set_xlabel('n_cpu')
            ax.set_xticks([1, 2, 6, 8])
            ax.set_ylabel('Migration time (s)')
            ax.yaxis.grid( color = 'black', linestyle = 'dashed' )
    P.tight_layout()
    P.savefig('microarch_'+str(mem_case)+'.png', dpi=150)
    print mem_case, n_points
print time.strftime('%d/%m/%y %H:%M:%S',time.localtime())               