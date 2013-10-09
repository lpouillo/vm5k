#!/usr/bin/env python

import os
from pprint import pprint
from operator import itemgetter
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.mlab as ml

def my_key(item):
    return tuple(int(part) for part in item.split('.')[0:4])


dt = np.dtype( {'names': ['timestamp', 'sys_start', 'sys_end', 'user_start', 'user_end', 'exec_start', 'exec_end', 'flops'],
                                'formats': [np.int, np.float, np.float, np.float, np.float, np.float, np.float, np.float]})

result_dir = 'VMMulticore_Jonathan/'
#result_dir = 'VMMulticore_20130625_100238_+0200/'


list_comb = os.listdir(result_dir)
for ignore in [ 'sweeps', 'stdout+stderr', 'graphs' ]:
    list_comb.remove(ignore)


raw_data = [ ]

for comb_dir in list_comb:
    k = comb_dir.replace('/',' ').split('-')
    i = iter(k)
    params = dict(zip(i,i))
    
    comb_res = os.listdir(result_dir+comb_dir)
    
    data = {}    
    #fig = plt.figure(figsize=(15, 10), dpi=150)
    for infile in sorted(comb_res, key = my_key):
        if 'g5k' not in infile:
            vm_ip = '.'.join( [ n for n in infile.split('.')[0:4] ])
        
            f = open(result_dir + comb_dir +'/'+ infile)
            data[vm_ip] = np.loadtxt(f, dtype = dt, delimiter = " - ", skiprows = 0)
            f.close()
            
            #plt.plot(data[vm_ip]['timestamp'], data[vm_ip]['flops'])
    
    #plt.savefig(result_dir+'/graphs/xp-active_core-'+params['active_core']+'-dist-'+params['dist']+'.png')
    raw_data.append( {'active_core': int(params['active_core']), 'n_vm': sum( [ int(i) for i in params['dist'] ] ), 
                      'dist': params['dist'], 'data': data})
    


#raw_data.sort(key = itemgetter('n_vm'))

flops_n_vm = []
flops_n_vm_by_total_cores = []
flops_n_vm_by_core = []

contour_data = {'n_vm_by_core': [], 'n_other_vm': [], 'flops': []}
test = {}
 
for result in raw_data:
    all_vms = []
    
    for vm_ip in sorted(result['data'].keys(), key = my_key):
        all_vms.append(np.median(result['data'][vm_ip]['flops']))
    flops_n_vm.append( (result['n_vm'], np.median(np.array(all_vms))) )
    flops_n_vm_by_total_cores.append( (float(result['n_vm'])/float(result['active_core']), np.median(np.array(all_vms))))
    
    
    if len(all_vms) > 0: 
        iter_vms = iter(all_vms)
        i_vm = 0
        for n_vm_core in result['dist']:
            core_vms = []
            for i in range( int(n_vm_core)):
                try:
                    core_vms.append(iter_vms.next())
                    i_vm += 1
                except:
                    pass
            flops_n_vm_by_core.append( (int(n_vm_core), np.median(np.array(core_vms)) ) )

            
            contour_data['n_vm_by_core'].append( int(n_vm_core) )
            contour_data['n_other_vm'].append( len(all_vms) - int(n_vm_core) )
            contour_data['flops'].append( np.median(np.array(core_vms)) )
            
            if test.has_key(int(n_vm_core)):
                test[int(n_vm_core)].append( (len(all_vms) - int(n_vm_core), np.median(np.array(core_vms))) )
            else:
                test[int(n_vm_core)] = [(len(all_vms) - int(n_vm_core), np.median(np.array(core_vms))) ]
                





#fig = plt.figure(figsize=(15, 10), dpi=300)
#for n_vm_core, result in test.iteritems():
#    n_other_vm, flops = zip(*result)
#    plt.plot(n_other_vm, flops, '+', label = n_vm_core)
#plt.savefig('test.png')    


#for n_vm, values in test.iteritems():
#    n_other_vm, flops = zip(*values)
#    plt.plot(n_other_vm, flops, '+', label = n_vm)
#plt.savefig('test.png')



#for i in range(20):
#    print contour_data['n_vm_by_core'][i], contour_data['n_other_vm'][i], contour_data['flops'][i]







#fig = plt.figure(figsize=(10, 5), dpi=300)
#for i in range(10):
#    plt.plot(Y[i], Z[i], '+')
#plt.savefig('new_test.png')
#
#exit()
#
#for i in range(20):
#    print X[i][i], Y[i][i], Z[i][i]
#    
#print X.min(), X.max()
#print Y.min(), Y.max()
#print Z.min(), Z.max()



#pprint (X)
#pprint (Y)
#pprint(Z)
#print len(Z), len(Z[0])
#print len(X), len(Y)
#exit()
#
#for i in range(20):
#    print contour_data['n_vm_by_core'][i], contour_data['n_other_vm'][i], contour_data['flops'][i]


xi = np.linspace(min(contour_data['n_vm_by_core']), max(contour_data['n_vm_by_core']))
yi = np.linspace(min(contour_data['n_other_vm']), max(contour_data['n_other_vm']))
X, Y = np.meshgrid(xi, yi)
Z = ml.griddata(contour_data['n_vm_by_core'], contour_data['n_other_vm'], contour_data['flops'], X, Y)



fig = plt.figure(figsize=(10, 5), dpi=150)
#plt.contour(X, Y, Z,  linewidths = 0.5, colors = 'k')
plt.pcolormesh(X, Y, Z,  cmap = plt.get_cmap('jet'))
cb = plt.colorbar()
cb.set_label('Flops')
plt.scatter(contour_data['n_vm_by_core'], contour_data['n_other_vm'], marker = 'o', c = 'b', s = 5, zorder = 10)
plt.xlabel('Number of VM in the core')
plt.ylabel('Number of VM in the other cores')
plt.title(params['cluster'])


plt.savefig('contour.png')
exit()


n_vm, flops = zip(*flops_n_vm)
fig = plt.figure(figsize=(10, 5), dpi=150)
plt.plot(n_vm, flops, '+')
plt.savefig('flops_n_vm.png')

n_vm_by_total_core, flops = zip(*flops_n_vm_by_total_cores)
fig = plt.figure(figsize=(10, 5), dpi=150)
plt.plot(n_vm_by_total_core, flops, '+')
plt.savefig('flops_n_vm_by_total_core.png')
        
        
fig = plt.figure(figsize=(10, 5), dpi=150)
n_vm_by_core, flops = zip(*flops_n_vm_by_core)
plt.plot(n_vm_by_core, flops, 'ro')

plt.savefig('flops_n_vm_by_core.png')


exit()




#
#
#     
#vms_ip = [  ip for ip in os.listdir(result_dir+comb_dir) ]
#sum( [ int(i) for i in
#
#vms = { 'vm-'+str(id): for id in vms_id }
#
#for vm in vms_id:
#    print vm

#for vm in 
