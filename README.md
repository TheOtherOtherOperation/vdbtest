# VDBTest

## License
Copyright (c) 2016 DeepStorage, LLC (deepstorage.net) and Ramon A. Lovato (ramonalovato.com).

See the file LICENSE for copying permission.

Author: Ramon A. Lovato (ramonalovato.com)
For: DeepStorage, LLC (deepstorage.net)
Version: 1.0

## Introduction
VDBTest (vdbtest.py) is a tool for automating VDbench storage benchmark testing for networked virtual machines. It leverages the NetJobs tool's agent-controller infrastructure to synchronize workloads. VDBTest's ultimate purpose is to search for the optimal IOPS (I/Os per second) rate for a a storage system such as to maximize IOPS while keeping IO latency below a specified threshold.

## Requirements
- Python 3.4 or later (http://www.python.org/)
- NetJobs 2.2 or later (included)
- Oracle VDbench 5.04.01 or later (http://www.oracle.com/technetwork/server-storage/vdbench-downloads-1901681.html)
- Java SE Runtime Environment (JRE) 1.6 or later (http://www.oracle.com/technetwork/java/javase/downloads/index.html)

## Setup

### Virtual Machines
VDBTest is intended to be used with some number *n* of similar virtual machines (called "targets") on a LAN, with access to a common file share and the storage system under test. Each virtual machine must be running NetJobsAgent.py (included with NetJobs) and have VDbench installed.

The recommended configuration is to create a separate controller machine, which may be either a physical machine or another VM, to run vdbtest.py and host the common file share (NFS or something similar). The controller machine does not need direct access to the storage system under test. The file share should have a directory structure similar to the following:

```
- share/
    - config/
        - vdb1
        - vdb2
        - ...
        - vdbN
    - output/
    - work/
```

The target VMs must have the same path to the share, so if VM 1's share path is, for example, "/mnt/nfsshare/", then all other VMs must also have the share mounted at "/mnt/nfsshare/". VDBTest assumes that each target VM's call to VDbench will have the same name---for example, "start_vdbench.sh". However, each virtual machine must have a unique identifier, such as "vdb1", "vdb2", ..., "vdbN". Thus, we recommend creating a single script for all virtual machines and modifying it with each VM's identifier. The recommended way to do this is to create a single VM, clone it *n* times, and then update each VM's script accordingly.

An example script, "sample_vm_script.sh", is provided:

```bash
#!/bin/bash
#
# Directions:
#
# Fill in the right values for NAME, SHARE, and LUN.
#
# Make sure SHARE has the following directory structure:
# SHARE
# -- config     # Contains VDbench config files named after NAME.
# -- output     # For output files.
# -- work       # Some directory for containing NetJobs work files.
#

export NAME="vdb1"              # Unique identifier for this VM.
export SHARE="/mnt/nfsshare"    # Where the share is mounted.
export LUN="/dev/sdb"           # Device identifier for LUN.

# ########################################################################### #
# DO NOT MODIFY PAST THIS LINE                                                #
# ########################################################################### #
command="/VDbench/vdbench -f '$SHARE/config/$NAME' -o '$SHARE/output/$NAME' lun='$LUN'"
echo "> " "$command"
eval $command
```

Here, the VM's identifier is "vdb1", which must be unique to this VM; the VM has the share mounted at "/mnt/nfsshare", and the storage device under test is located at "/dev/sdb". Expanding the variables, the VDbench configuration for this VM would then need to be locatable at "/mnt/nfsshare/config/vdb1", and VDbench would save its output to "/mnt/nfsshare/output/vdb1".

**Important:** notice how both the parameters for "-f '$SHARE/config/$NAME'" and "-o '$SHARE/output/$NAME'" in the command line end with the variable "$NAME". VDBTest identifies target VMs by the names of their configuration files. After each round of testing, it then expects the output directory ("$SHARE/output" in this case) to contain VDbench-generated subdirectories with the same name. In other words, if the base name of the configuration file path and the base name of the output path are not the same, VDBTest won't be able to locate the output files. Also because of this, VDBTest doesn't know what to do with extraneous or unused files in the config, output, and work directories. The tool makes a best effort attempt to ignore hidden and temporary files, but in general, all extraneous files and old test data should be migrated outside the test tree. To prevent accidental deletion of important test results, overwriting of files is not allowed, so leaving old test results or archived configuration files in the output or config folders will usually cause testing to fail.

### Configuration File
The VDBTest configuration file (not to be confused with the VDbench configuration files for each target VM) require exactly two parameters: "command: [SOME COMMAND]" and "targets:", where "command" specifies the name of the script to execute on each VM and "targets" is a newline-delimited list of target VMs (either IP addresses or DNS names). Empty lines and any lines beginning with a hash ("#") are ignored.

See "sample_vdbt_config.txt" for an example:
```
#
# Sample config file for vdbtest.
#

command: foo

targets:
localhost
192.168.0.1
172.17.0.1
127.0.0.1
```

## Usage
```
usage: vdbtest.py [-h] [-m MAX_RUNS] [-t TIMEOUT] [-s SUCCESS_MULTIPLIER]
                  [-f FAILURE_MULTIPLIER] [-c CONSECUTIVE_FAILURES]
                  [-z FUZZINESS] [-i IOPS_TOLERANCE] [-v]
                  configFile configDir outputParent workFolder logPath
                  targetLatency

positional arguments:
  configFile            path to the configuration file
  configDir             directory containing VDbench config files
  outputParent          the parent directory of the directories containing
                        output files
  workFolder            path to the work folder for intermediate file storage
  logPath               where to save the log file
  targetLatency         target latency we're trying for (in ms)

optional arguments:
  -h, --help            show help message and exit
  -m MAX_RUNS, --max-runs MAX_RUNS
                        override maximum number of runs before aborting
                        (default 5)
  -t TIMEOUT, --timeout TIMEOUT
                        set a timeout in seconds for the scheduler (default 0)
  -s SUCCESS_MULTIPLIER, --success-multiplier SUCCESS_MULTIPLIER
                        override IO rate multiplier when target is below
                        target latency (default 5.0)
  -f FAILURE_MULTIPLIER, --failure-multiplier FAILURE_MULTIPLIER
                        override IO rate multiplier when target is above
                        target latency (default 0.3)
  -c CONSECUTIVE_FAILURES, --consecutive-failures CONSECUTIVE_FAILURES
                        terminate after n consecutive failures (default 2)
  -z FUZZINESS, --fuzziness FUZZINESS
                        acceptable fractional skew from target latency, such
                        that targetLatency * (1.0 - fuzziness) <= x <=
                        targetLatency * (1.0 + fuzziness) (default 0.0)
  -i IOPS_TOLERANCE, --iops-tolerance IOPS_TOLERANCE
                        if IOPS achieved * IOPS tolerance < IOPS requested,
                        terminate early (default 1.5)
  -v, --verbose         enable verbose mode
```

### Example
```bash
vdbtest.py sample_vdbt_config.txt /var/nfsshare/config/ /var/nfsshare/output/ /var/nfsshare/work/ /var/nfsshare/log.txt 5.0
```

Runs VDBTest with the following:
- VDBTest configuration: sample_vdbt_config.txt
- Where to find VDbench configurations for the VMs: /var/nfsshare/config/
- The parent directory in which to find VDbench output directories: /var/nfsshare/output/
- Where to put NetJobs work files: /var/nfsshare/work/
- Where to save the log file: /var/nfsshare/log.txt
- Target latency: 5.0 ms

### Optional Parameters
- `-m MAX_RUNS, --max-runs MAX_RUNS`
By default, VDBTest tries at most five (5) times to hunt for the optimal IOPS value before aborting. This overrides that value.
- `-t TIMEOUT, --timeout TIMEOUT`
Specifies a timeout (in seconds) for the scheduler. If this amount of time passes without all target machines completing, the current test is automatically aborted. A value of 0 indicates no timeout (default).
- `-s SUCCESS_MULTIPLIER, --success-multiplier SUCCESS_MULTIPLIER`
Each time a VDbench run completes, VDBTest scans the output files to see if all of the target VMs had IO latency below the specified threshold ("targetLatency"). If yes, the IOPS rate is multiplied by this value for the next run (default 5.0).
- `-f FAILURE_MULTIPLIER, --failure-multiplier FAILURE_MULTIPLIER`
Similar to --success-multiplier, but if *any* VM failed (was above) the target latency, the IOPS rate is multiplied by this value on the next run (default 0.3).
- `-c CONSECUTIVE_FAILURES, --consecutive-failures CONSECUTIVE_FAILURES`
By default, VDBTest aborts early if two (2) consecutive VDbench runs fail. This overrides that behavior.
- `-z FUZZINESS, --fuzziness FUZZINESS`
Specifies an acceptable fraction of skew from the target latency, such that targetLatency * (1.0 - fuzziness) <= x <= targetLatency * (1.0 + fuzziness). For example, if the target latency is 5.0 and fuzziness is 0.1, then any latency x such that 4.5 <= x <= 5.5 will be considered a pass. By default, this value is 0, so VDBTest will just keep searching until (a) *all* target VMs achieve the exact target latency, which is unlikely, or (b) some other condition causes the test to end.
- `-i IOPS_TOLERANCE, --iops-tolerance IOPS_TOLERANCE`
On some storage systems, VDbench soft caps at certain IOPS rates, such that further increasing the IOPS value does not actually cause VDbench to perform more IOPS, which also means the latency no longer increases. Since these soft caps can effectively be considered the optimal IOPS rate for the specified target latency on those systems, this parameter determines when VDBTest stops trying to increase the IOPS value. Specifically, if IOPS achieved * IOPS tolerance < IOPS requested on any of the target VMs, the test terminates early (default 1.5).

## Version History
1.0 - Initial release.



This document was last updated on 03/29/16.
