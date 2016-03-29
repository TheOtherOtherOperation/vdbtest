#!/bin/bash
#
# Directions:
#
# Fill in the right values for NAME, SHARE, and LUN.
#
# Make sure SHARE has the following directory structure:
# SHARE
# -- config	# Contains VDbench config files named after NAME.
# -- output     # For output files.
# -- WORK       # Some directory for containing NetJobs work files.
#

export NAME="vdb1"    # Unique identifier for this VM/VDbench instance.
export SHARE="/mnt/nfsshare"    # Where the share is mounted.
export LUN="/dev/sdb"    # Device identifier for LUN.

# ########################################################################### #
# DO NOT MODIFY PAST THIS LINE                                                #
# ########################################################################### #
command="/VDbench/vdbench -f '$SHARE/config/$NAME' -o '$SHARE/output/$NAME' lun='$LUN'"
echo "> " "$command"
eval $command
