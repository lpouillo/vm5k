mount -t tmpfs cgroup_root /sys/fs/cgroup
mkdir /sys/fs/cgroup/cpuset
mkdir /sys/fs/cgroup/cpu
mkdir /sys/fs/cgroup/cpuacct
mkdir /sys/fs/cgroup/memory
mkdir /sys/fs/cgroup/devices
mkdir /sys/fs/cgroup/freezer
mkdir /sys/fs/cgroup/net_cls
mkdir /sys/fs/cgroup/blkio
mkdir /sys/fs/cgroup/perf_event
mount -t cgroup -o rw,nosuid,nodev,noexec,relatime,cpuset cgroup_cpuset /sys/fs/cgroup/cpuset
mount -t cgroup -o rw,nosuid,nodev,noexec,relatime,cpu cgroup_cpu /sys/fs/cgroup/cpu
mount -t cgroup -o rw,nosuid,nodev,noexec,relatime,cpuacct cgroup_cpuacct /sys/fs/cgroup/cpuacct
mount -t cgroup -o rw,nosuid,nodev,noexec,relatime,memory cgroup_memory /sys/fs/cgroup/memory
mount -t cgroup -o rw,nosuid,nodev,noexec,relatime,devices cgroup_devices /sys/fs/cgroup/devices
mount -t cgroup -o rw,nosuid,nodev,noexec,relatime,freezer cgroup_freezer /sys/fs/cgroup/freezer
mount -t cgroup -o rw,nosuid,nodev,noexec,relatime,net_cls cgroup_net_cls /sys/fs/cgroup/net_cls
mount -t cgroup -o rw,nosuid,nodev,noexec,relatime,blkio cgroup_blkio /sys/fs/cgroup/blkio
mount -t cgroup -o rw,nosuid,nodev,noexec,relatime,perf_event cgroup_perf_event /sys/fs/cgroup/perf_event

