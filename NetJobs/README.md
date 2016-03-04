# NetJobs

## License
Copyright (c) 2015 DeepStorage, LLC (deepstorage.net) and Ramon A. Lovato (ramonalovato.com).

See the file LICENSE for copying permission.

Author: Ramon A. Lovato (ramonalovato.com)
For: DeepStorage, LLC (deepstorage.net)
Version: 2.3

## Introduction
NetJobs is a network job synchronizer written in Python. Its primary use is the synchronization of benchmark jobs running on multiple virtual machines on a vLAN. Since VMs typically do not have regular access to the host machine's system clock, NetJobs aims to provide a service for starting jobs on multiple VMs at approximately the same time. True simultaneity under these conditions is impossible, of course, and NetJobs is no exception. Its aim is to reduce the latency between start times, not eliminate it completely.

## Requirements
Any machine running Python 3.4 or later.

## Architecture
- NetJobs.py: the main NetJobs control center.
- NetJobsAgent.py: the NetJobs agent to be run on target machines.

NetJobs communicates with its agents using standard TCP sockets. NetJobsAgent should be loaded onto each target virtual or physical machine, and the main NetJobs script should be run on the control center. Both scripts are designed to be run from the command line. A GUI is not provided.

## Instructions
If Python is installed in a nonstandard location, or if multiple versions of Python are installed on the same machine, launching the scripts by name may not work. In this case, the script names will need to be passed as arguments to the Python interpreter. E.g.:
	$ python3 NetJobsAgent.py

### NetJobsAgent
Usage: NetJobsAgent.py

The agent runs as a lightweight, non-daemon, TCP server, which should be loaded onto each target machine and run before starting NetJobs. It accepts no arguments. The process listens on port 16192 and accepts only a single connection at a time. Upon completion of a task, the agent returns to waiting mode. This process blocks indefinitely and must be manually terminated with a ctrl-c/ctrl-break keyboard interrupt.

### NetJobs
Usage: NetJobs.py [OPTIONS] [PATH]

OPTIONS
	-h Display help message.
	-s Run in simulator mode (disables networking).
	-v Run in verbose mode.
    -l Enable test result logging to file.
PATH
	Relative or absolute path to configuration file (required).

Example: $ NetJobs.py -v "C:\NetJobs\testconfig.txt"

If a configuration file is not provided, NetJobs will ask for one. On completion, NetJobs will print out the output received from each target machine. Running with the -v flag will cause NetJobs to also output its progress at each step.

NetJobs begins by parsing the configuration file and generating a list of test configurations. For each test, it begins by iterating through all targets and opening connections to them. Assuming socket creation was successful, it then performs a simple echo test to verify the connection. If this completes, it sends the target its intended command string and moves to the next. Once it finishes prepping all targets, it goes through the list again and tells each agent to start the run. It then spawns a worker thread to listen for that agent to complete. When all worker threads join, NetJobs outputs the results for that test and moves on to the next.

If -l is specified, a timestamped log file is generated for each test and placed in the same directory as the configuration file.

### Configuration File

#### Format
[TEST LABEL]:
-[GENERAL TIMEOUT]
-[MINHOSTS]
[TARGET]: [COMMAND]
-[OPTIONAL FLAG]
[TARGET]: [COMMAND]
-[OPTIONAL FLAG]
[...]
end

[TEST LABEL]:
[...]

#### Specifications
The configuration file consists of blocks containing the specifications for each test. Specifications are separated by newlines. A test block begins with an alphanumeric label, followed by a colon and a newline. Everything from that point on is then considered to be part of that test block until a line containing the keyword "end" is read, at which point, the next line read is expected to be the start of a new test block.

Each line that is not the start or end of a test block is made up of specially formatted "[KEY]: [VALUE]" pairs delimited by a colon. The parser is generally fairly tolerant of differences in white space surrounding the delimiter. Lines beginning with a hyphen ('-') are optional.

Lines beginning with a hash ('#') are treated as comment lines and ignored.

If -generaltimeout or -minhosts flags are to be used, they must appear at the beginning of a test block, before any targets are specified.

If "-generaltimeout" is set, all targets will default to that timeout. This value can be overwritten on a target-by-target basis by use of the "-timeout" flag.

The "-minhosts" flag specifies the minimum number of target hosts that must NOT timeout for the test to succeed. Acceptable values are "all" or any non-negative integer. If "-minhosts: all" (the default) is specified, the test ends immediately if any host times out. If "-minhosts: 0" is specified, the test continues even if all hosts time out.

Target lines take the form "[TARGET]: [COMMAND]", where "[TARGET]" is the host name or IP address of a machine running NetJobsAgent.py, and "[COMMAND]" is a shell-executable command (generally a script), enclosed in quotation marks, that target machine should execute.

Note that listing a single target multiple times in the same test block can lead to unpredictable results and should be avoided.

The "-timeout" flag can be set following any target line and specifies the amount of time to wait for that target to return a result. This value always overrides "-generaltimeout" and should allow sufficient time for the target's designated task to complete.

Both "-timeout" and "-generaltimeout" accept non-negative values in seconds ("s"), minutes ("m"), or hours ("h"), as well as "none" (default), which allows NetJobs to wait indefinitely. For example, "-timeout: 330s" will cause NetJobs to wait 5 minutes and 30 seconds.

#### Example:
test0:
-generaltimeout: none
-minhosts: all
localhost: "echo 'hello, world'"
-timeout: 1s
end

test1:
-generaltimeout: 5m
-minhosts: 0
172.17.1.19: "./some_test_script.sh"
-timeout: 30s
182.17.1.20: "./other_test_script.sh"
182.17.1.20: "./and_another_test_script.sh"
end

## A Note on Results
When a command initiated by NetJobsAgent returns, its standard output is piped to NetJobs and displayed as part of the results for that test. This can become difficult to read if the output for a command is particularly long. Thus, in general, we recommend redirecting long outputs to files stored locally on the target machines so as not to overload the results display from NetJobs.

## Version History

2.3 - Fixed a scoping bug that allowed configurations to persist across calls.
2.2 - NetJobsAgent now echoes subprocess output to standard out. Ping status checking added: once at least minhosts tests have reported success, each time a job completes, all currently active ListenThreads ping their targets to make sure the connection is still active.
2.1 - Output logging added. Running NetJobs with the -l flag now causes a timestamped log file to be generated for each test, in the same directory as the configuration file.
2.0 - Release version. Multiple commands now working as intended. Fixed a bug where sometimes the socket would close before all results had been transmitted.
1.2 - Fixed bugs that caused client to hang while waiting for agent results.
1.1 - Support for comment lines in config file. Input file parser rebuilt from scratch. Support for specifying multiple commands per agent.
1.0 - Initial release. Timeout values are now transmitted to agents. Agents now recover from errors and return to wait mode if a test is interrupted.
0.3 - Fixed bug that prevented working on remote machines.
0.2 - New fault handling, additional config options (timeout, etc.).
0.1 - Initial version.



This document was last updated on 03/03/16.
