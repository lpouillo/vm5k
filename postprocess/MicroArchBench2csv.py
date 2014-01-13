#!/usr/bin/env python
import os
from pprint import pprint
import sys
import getopt
import numpy as np
import csv

def my_key(item):
    return tuple(int(part) for part in item.split('.')[0:4])

def main(argv):
    result_dir="defaultdir"
    output_csv="default.csv"
    try:
        opts, extraparams = getopt.getopt(sys.argv[1:],"hi:o:",["input-dir=","output-csv="]) 
    except getopt.GetoptError:
        print 'test.py -i <inputdirectory> -o <outputfile.csv>'
        sys.exit(2)

    for o,p in opts:
        if o == '-h':
            print 'execoToCSV.py -i <inputdir> -o <outputcsv>'
            print 'inputdir: a input directory where the EXECO results are stored'
            print 'outputdir: an output csv file where the results will be stored'
            sys.exit(2)
        elif o in ['-i','--input-dir']:
            result_dir = p
        elif o in ['-o','--output-csv']:
            output_csv = p


    if result_dir == "defaultdir":
        print "You must define a input directory where the EXECO results are stored"
        sys.exit()

    if output_csv == "default.csv":
        print "You must define an output csv file where the results will be stored"
        sys.exit()

    print 'Input result directory:',result_dir
    print 'Output CSV file: ',output_csv


    dt = np.dtype( {'names': ['timestamp', 'sys_start', 'sys_end', 'user_start', 'user_end', 'exec_start', 'exec_end', 'flops'],
                                'formats': [np.int, np.float, np.float, np.float, np.float, np.float, np.float, np.float]})

    list_comb = os.listdir(result_dir)
    for ignore in [ 'sweeps', 'stdout+stderr', 'graphs', '#stdout+stderr#' ]:
        if ignore in list_comb:
            list_comb.remove(ignore)

    raw_data = [ ]

    for comb_dir in list_comb:
        k = comb_dir.replace('/',' ').split('-')
        i = iter(k)
        params = dict(zip(i,i))
    
        comb_res = os.listdir(result_dir+'/'+comb_dir)
        #print params
        
        count_vm = 0
	count_multi_core = 0
	
	vm_on_core = {}
	coreIdCell1 = 0
	coreIdCell2 = 1
	count_core = 0
	vmOnCell1 = 0
	vmOnCell2 = 0
	
        for nbvmcore in params['dist']:
	  count_vm += int(nbvmcore)
	  if count_core < 6:
	    vm_on_core[coreIdCell1] = int(nbvmcore)
	    coreIdCell1 = coreIdCell1 + 2
	    vmOnCell1 = vmOnCell1 + int(nbvmcore)
	  else:
	    vm_on_core[coreIdCell2] = int(nbvmcore)
	    coreIdCell2 = coreIdCell2 + 2
	    vmOnCell2 = vmOnCell2 + int(nbvmcore)
	  count_core = count_core + 1
	  
	count_core = 0
        for nbvmcore in params['multi_cpu']:
	  count_multi_core += int(nbvmcore)
	  if count_core in vm_on_core:
	    vm_on_core[count_core] = vm_on_core[count_core] + int(nbvmcore)
	  else:
	    vm_on_core[count_core] = int(nbvmcore) 
	  vmOnCell1 = vmOnCell1 + 1
	  count_core = count_core  + 1
	  
        data = {}    
        mdata = {}
        cpt_vm = 0

        filetoint = {}
	filevmmultitoint = {}
	second_cell_active = False
	
        for infile in sorted(comb_res):
	  if infile.find("vm_multi") == -1:
	    lastPart = infile.split(".")[3]
	    dkey = int(lastPart.split("_")[0])
	    filetoint[dkey] = infile
	  else:
	    dkey = int(infile.split("_")[2].split(".")[0])
	    filevmmultitoint[dkey] = infile
            
            
        if count_vm != len(filetoint):
	  print "Failed comb %s" % comb_dir
	elif len(filevmmultitoint) != count_multi_core:
	  print "Failed comb %s" % comb_dir
	else:
	  print "Successful comb %s" % comb_dir
        
        total_count_vm = count_vm + count_multi_core
        
        for inkey in sorted(filetoint.keys()):
            infile = filetoint[inkey]

	    infileIP = infile.split('_')[0]
            
            vm_ip = '.'.join( [ n for n in infileIP.split('.')[0:4] ])
        
            f = open(result_dir + '/' + comb_dir +'/'+ infile)
            data[vm_ip] = np.loadtxt(f, dtype = dt, delimiter = " - ", skiprows = 0)
            f.close()
            
            mdata[vm_ip] = {}
            
            str_local_core = infile.split('_')[1]
            local_core = int(str_local_core.split('.')[0])
            cell_number = 0
            
            if (local_core%2 == 0):
	      cell_number = 0
	      mdata[vm_ip]['vm_on_cell'] = vmOnCell1
	    else:
	      cell_number = 1
	      mdata[vm_ip]['vm_on_cell'] = vmOnCell2
	      second_cell_active = True
	      
            mdata[vm_ip]['core_number'] = local_core
            mdata[vm_ip]['vm_on_core'] = vm_on_core[local_core]
            mdata[vm_ip]['cell_number'] = cell_number
	    mdata[vm_ip]['multi'] = 0
	    mdata[vm_ip]['vm_id'] = cpt_vm
	    cpt_vm = cpt_vm + 1
	    
        for inkey in sorted(filevmmultitoint.keys()):
            infile = filevmmultitoint[inkey]
            
            vm_ip = infile.split('.')[0]
        
            f = open(result_dir + '/' + comb_dir +'/'+ infile)
            data[vm_ip] = np.loadtxt(f, dtype = dt, delimiter = " - ", skiprows = 0)
            f.close()
            
            mdata[vm_ip] = {}
            
            local_core = int(inkey)
            
            mdata[vm_ip]['core_number'] = local_core
            mdata[vm_ip]['vm_on_core'] = vm_on_core[local_core]
            mdata[vm_ip]['cell_number'] = 0
            mdata[vm_ip]['vm_on_cell'] = vmOnCell1
	    mdata[vm_ip]['multi'] = 1
	    mdata[vm_ip]['vm_id'] = cpt_vm
	    cpt_vm = cpt_vm + 1
	    
        active_core = 0
        for i in params['dist']:
            if int(i) > 0:
                active_core+=1

	active_cell = 1
	if (second_cell_active):
	  active_cell = 2

        raw_data.append( {'active_core': active_core, 'active_cell': active_cell, 'n_vm': total_count_vm, 
                      'dist': params['dist'], 'data': data, 'mdata' : mdata, 'vm_multi': params['multi_cpu']})

    with open(output_csv, 'wb') as csvfile:
        csvwriter = csv.writer(csvfile)
        for result in raw_data:
            for vm_ip in result['data'].keys():
		if result['data'][vm_ip].size > 1:
		  ##print result['dist']
		  
		  for ict in range(0,len(result['data'][vm_ip]['sys_start'])):
		      csvwriter.writerow([result['dist'],result['vm_multi'],result['active_core'],result['active_cell'],result['n_vm'],result['mdata'][vm_ip]['vm_id'],result['mdata'][vm_ip]['vm_on_core'],
				      result['mdata'][vm_ip]['vm_on_cell'],result['mdata'][vm_ip]['core_number'],result['mdata'][vm_ip]['cell_number'],result['mdata'][vm_ip]['multi'],
				      result['data'][vm_ip]['timestamp'][ict],result['data'][vm_ip]['sys_start'][ict], result['data'][vm_ip]['sys_end'][ict], 
				      result['data'][vm_ip]['user_start'][ict], result['data'][vm_ip]['user_end'][ict], result['data'][vm_ip]['exec_start'][ict], 
				      result['data'][vm_ip]['exec_end'][ict], result['data'][vm_ip]['flops'][ict]])

if __name__ == "__main__":
   main(sys.argv[1:])
