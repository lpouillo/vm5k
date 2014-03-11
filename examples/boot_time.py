#!/usr/bin/env python
#
# A simple program to retrieve boot time for vms after
# a vm5k deployment
#
import sys
import time
import datetime
from numpy import array, median
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from execo import TaktukRemote, logger, default_connection_params

default_connection_params['user'] = 'root'

logger.info('Measuring boot time')

# Reading VMs list for directory given in arg
run_dir = sys.argv[1]

if not run_dir:
    logger.error('No directory specified')
    exit()

vms = []
f = open(run_dir + '/vms.list')
for line in f:
    tmp = line.split()
    vms.append({'id': tmp[1], 'ip': tmp[0]})
f.close()

# Measuring boot_duration
now = time.time()
get_uptime = TaktukRemote('cat /proc/uptime', [vm['ip']
                    for vm in vms]).run()
boot_time = {}
for p in get_uptime.processes:
    boot_time[p.host.address] = now - float(p.stdout.strip().split(' ')[0])

get_ssh_up = TaktukRemote('grep listening /var/log/auth.log' + \
            ' |grep 0.0.0.0|awk \'{print $1" "$2" "$3}\'',
            [vm['ip'] for vm in vms]).run()
boot_duration = []
for p in get_ssh_up.processes:
    ssh_up = time.mktime(datetime.datetime.strptime('2014 ' + \
            p.stdout.strip(), "%Y %b %d %H:%M:%S").timetuple())
    boot_duration.append(ssh_up - boot_time[p.host.address])


# Calculating stats
uptime = array(boot_duration)
dur_min = uptime.min()
dur_max = uptime.max()
mean = uptime.mean()
std = uptime.std()
median = median(uptime)
logger.info('VMS: %s', len(vms))
logger.info('Average: %s', mean)
logger.info('Standard deviation: %s', std)
logger.info('Min-max: %s-%s', dur_min, dur_max)

# Drawing historgram
n, bins, patches = plt.hist(uptime, bins=5,
                            facecolor='g', alpha=0.75)
plt.xlabel('Boot duration')
plt.ylabel('Number of VMs')
plt.grid(True)
plt.savefig(run_dir + '/boot_time.png')
