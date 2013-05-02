#!/usr/bin/env python
# -*- coding: UTF-8 -*-
import time
import numpy as np
import os
import pylab as P
from pprint import pformat, pprint
from execo_engine import slugify
from execo.time_utils import unixts_to_datetime
import matplotlib.dates as MD



#result_dir = 'Live_Migration_20130328_003239_+0100/'
result_dir = 'G5K_Live_Migration_20130409_160943_+0200/'

#result_dir = 'Live_Migration_20130328_133128_+0100/'
try:
    os.mkdir(result_dir+'graphs')
except:
    pass

xfmt = MD.DateFormatter('%H:%M:%S')
x_major_locator = P.MaxNLocator(5)


res_n_vm = {}
n_comb = 0
for comb in os.listdir(result_dir):
    
    if 'suno' in comb:
        n_comb += 1
        comb_dir = comb+'/'
        print n_comb, comb_dir
        k = comb_dir.replace('/',' ').split('-')
        i = iter(k)
        params = dict(zip(i,i))
        
        comb_res = os.listdir(result_dir+comb_dir)
        mig_type = []
        for infile in comb_res:
            if 'ping' not in infile and '.png' not in infile: 
                mig_type = mig_type + [infile.split('_')[0]] if infile.split('_')[0] not in mig_type else mig_type
            
        n_mig = len(mig_type)
        
        dt = np.dtype( {'names': ['timestamp', 'vm-id', 'measure', 'duration'],
                        'formats': [np.int, '|S4', np.int, np.float]})
        fig = P.figure(figsize=(5*n_mig, 10), dpi=80, )
        #P.suptitle(params['cluster']+'\n mem_size='+params['mem_size']+'Mo, Speed='+params['mig_speed']+', Refresh rate='+params['mem_update_rate'])
        #ax_ping = P.subplot2grid( (2, n_mig), (2,0), colspan = n_mig)
        
        data = {}
        for infile in comb_res:
            infile.replace('.out', '')
            
            if 'ping' in infile:
                vm_id = infile.split('_')[2]
#                names = [ 'timestamp', 'ping' ]
#                ping_data = np.genfromtxt(result_dir + comb_dir + infile, 
#                                    skiprows = 1, names = names, delimiter =" ")
#                 
#                #exit()
#                ax_ping.xaxis_date()
#                ax_ping.xaxis.set_major_formatter(xfmt)
#                ax_ping.xaxis.set_major_locator(x_major_locator )
#                ax_ping.xaxis.grid( color = 'black', linestyle = 'dashed' )
#            
#                dates = [unixts_to_datetime(ts) for ts in ping_data['timestamp']]
#                datenums = MD.date2num(dates)
#                ax_ping.semilogy(datenums, ping_data['ping'])
#                ax_ping.set_xlim( [unixts_to_datetime(ping_data['timestamp'].min()), unixts_to_datetime(ping_data['timestamp'].max()) ])
#                ax_ping.set_ylabel('Latency')
#                P.xticks(rotation = 30)                
                
                
            elif '.out' in infile:
                mig = infile.split('_')[0]
                with open(result_dir + comb_dir + infile) as f:
                    if not data.has_key(mig):
                        data[mig] = np.loadtxt(f, dtype = dt, comments = "#", skiprows = 0)
                    else:
                        data[mig] = np.concatenate((data[mig], np.loadtxt(f, dtype = dt, comments = "#", skiprows = 0)))
                    f.close()

                
#        for mig, values in data.iteritems():
#            if mig == 'PARA':
#                print params['n_vm'], values['duration'].max()
#                exit()
        
        i_mig = 0
        
        
        
        for mig in mig_type:      

           
            
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
            
#             if mig == 'PARA':
#                 newdata = [x/params['n_vm'] for x in data['duration']]
#                 data['duration'] = newdata
#             
#             if mig == 'CROSSPARA':
#                 newdata = [x/(params['n_vm']/2) for x in data['duration']]
#                 data['duration'] = newdata
#            if mig == 'SEQ':
#x,"                print mig, median
#            if mig == 'PARA':
#                print mig, median/float(params['n_vm'])
            
            ax_duration = P.subplot2grid( (3, n_mig), (0, i_mig), title = mig)
            lmean = ax_duration.axhline(y = mean, color = 'r', label = 'mean='+str(mean))
            lmed = ax_duration.axhline(y = median, color = 'b', label = 'median='+str(median))
            ax_duration.axhline(y = mean+std, color = 'r', linestyle='--', label='std='+str(std))
            ax_duration.axhline(y = mean-std, color = 'r', linestyle='--')
            ax_duration.plot(data[mig]['measure'], data[mig]['duration'], 'o')
            ax_duration.set_xlabel('Measure')
            ax_duration.set_ylabel('Migration time (s)')
        
            ax_hist     = P.subplot2grid( (2, n_mig), (1, i_mig))
        
            n, bins, patches = ax_hist.hist(data[mig]['duration'], 5, histtype = 'stepfilled', rwidth=0.8)
            P.setp(patches, 'facecolor', 'g', 'alpha', 0.75)
            
            ax_hist.set_xlabel('Migration time (s)')
            
            ax_hist.set_ylabel('Number of measurements')
            ax_hist.set_ylim([0, max(n)])
            ya = ax_hist.get_yaxis()
            ya.set_major_locator(P.MaxNLocator(integer=True))
            i_mig +=1


                
            n_vm = int(params['n_vm'])
            
            
            hdd_size = int(params['hdd_size'])
            n_cpu = int(params['n_cpu'])
            mem_size = int(params['mem_size'])
            if not res_n_vm.has_key(n_vm):
                res_n_vm[n_vm] = {}
            if not res_n_vm[n_vm].has_key(hdd_size):
                res_n_vm[n_vm][hdd_size] = {}
            if not res_n_vm[n_vm][hdd_size].has_key(n_cpu):
                res_n_vm[n_vm][hdd_size][n_cpu] = {}
            if not res_n_vm[n_vm][hdd_size][n_cpu].has_key(mig):               
                res_n_vm[n_vm][hdd_size][n_cpu][mig] = { 'mem_size': [], 'duration': [], 'stdev': [] }
            
            
            res_n_vm[n_vm][hdd_size][n_cpu][mig]['mem_size'].append( mem_size )
            res_n_vm[n_vm][hdd_size][n_cpu][mig]['duration'].append( float(median) )
            res_n_vm[n_vm][hdd_size][n_cpu][mig]['stdev'].append( float(std) )
            
#P.savefig(result_dir+'graphs/'+slugify(params)+'.png', dpi=150)


#pprint(res_n_vm)



vm_number = []
hdd_sizes = []
cpu_number = []
for n_vm in sorted(res_n_vm.iterkeys()):
    if n_vm not in vm_number:
        vm_number.append(n_vm)
    for hdd_size in sorted(res_n_vm[n_vm].iterkeys()):
        if hdd_size not in hdd_sizes:
            hdd_sizes.append(hdd_size)
        for n_cpu in sorted(res_n_vm[n_vm][hdd_size].iterkeys()):
#print n_cpu
            if n_cpu not in cpu_number:
                cpu_number.append(n_cpu)
vm_number.sort()
hdd_sizes.sort()
cpu_number.sort()

n_vm_number = len(vm_number)


#


base_colors = 'bgrcmykw'
cpu_colors = {}
for idx, n_cpu in enumerate(cpu_number):
    cpu_colors[n_cpu] = base_colors[idx] 


base_symbol = 'osdp'
mig_symbol = {}
for idx, mig in enumerate([ 'SEQ', 'PARA', 'CROSSSEQ', 'CROSSPARA' ]):
    mig_symbol[mig] = base_symbol[idx]


#print mig_symbol
#print cpu_colors


n_n_vm = len(vm_number)
n_n_vm = 4
n_hdd_size = len(hdd_sizes)




#print hdd_sizes
#print vm_number
#print cpu_number

fig = P.figure(figsize=(5*n_n_vm, 5*n_hdd_size), dpi=150, )

for n_vm in sorted(res_n_vm.iterkeys())[0:4]:
    mem_size = []
    
    for hdd_size in sorted(res_n_vm[n_vm].iterkeys()):
        
#print  n_hdd_size, n_n_vm, (hdd_sizes.index(hdd_size)*n_n_vm)+(vm_number.index(n_vm)+1)
        ax = P.subplot( n_hdd_size, n_n_vm, (hdd_sizes.index(hdd_size)*n_n_vm)+(vm_number.index(n_vm)+1))
        
        for n_cpu in sorted(res_n_vm[n_vm][hdd_size].iterkeys()):
            for mig in res_n_vm[n_vm][hdd_size][n_cpu].iterkeys():
                data = res_n_vm[n_vm][hdd_size][n_cpu][mig]
      
               
                ax.scatter(data['mem_size'], data['duration'], c = cpu_colors[n_cpu],
                           marker = mig_symbol[mig], label = str(n_cpu)+' '+mig)
                for mem in data['mem_size']:
                    if mem not in mem_size:
                        mem_size.append(mem)
        
        
        log_mem_size = [ np.log(mem) for mem in mem_size ]
        ax.set_xticks( mem_size )
         
        ax.set_xlim( [0, max(mem_size)*1.05])
        
        ax.yaxis.grid( color = '#cccccc', linestyle = 'dashed' )
        
        if vm_number.index(n_vm) == 0:
            ax.set_ylabel('Migration time (s)', fontsize = 10)
        if hdd_sizes.index(hdd_size) == len(hdd_sizes)-1:
            ax.set_xlabel('Memory size(Mb)', fontsize = 10)
            
        ax.legend(loc='upper center', bbox_to_anchor=(0.5, 1.05),
          ncol=4, fancybox=True, shadow=True, prop = {'size': 7}, title = 'n_vm='+str(n_vm)+', hdd_size='+str(hdd_size))
        
        P.xticks(rotation = -90)
        P.tick_params(axis='both', which='major', labelsize = 8)
        #ax.set_title('n_vm='+str(n_vm)+', hdd_size='+str(hdd_size)+'', fontsize = 12)
        
        
        
P.tight_layout()
P.savefig('test_suno.png', dpi=150)


print time.strftime('%d/%m/%y %H:%M',time.localtime()) 









