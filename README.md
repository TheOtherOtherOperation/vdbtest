# VDBTest

## License
Copyright (c) 2016 DeepStorage, LLC (deepstorage.net) and Ramon A. Lovato (ramonalovato.com).

See the file LICENSE for copying permission.

Author: Ramon A. Lovato (ramonalovato.com)
For: DeepStorage, LLC (deepstorage.net)
Version: 1.0

## Introduction
VDBTest (vdbtest) is a tool for automating VDbench storage benchmark testing for networked virtual machines. It leverages the NetJobs tool's agent-controller infrastructure to synchronize workloads. VDBTest's ultimate purpose is to search for the optimal IOPS (I/Os per second) rate for a a storage system such as to maximize IOPS while keeping IO latency below a specified threshold.

## Requirements
- Python 3.4 or later (http://www.python.org/)
- NetJobs 2.2 or later (included)
- Oracle VDbench 5.04.01 or later (http://www.oracle.com/technetwork/server-storage/vdbench-downloads-1901681.html) --- requires Java
- Java SE Runtime Environment (JRE) 1.6 or later (http://www.oracle.com/technetwork/java/javase/downloads/index.html)

## Usage
Example: ./vdbtest.py sample_vdbt_config.txt /var/nfsshare/config/ /var/nfsshare/output/ /var/nfsshare/work/ 5.0

## Version History
1.0 - Initial release.



This document was last updated on 03/29/16.
