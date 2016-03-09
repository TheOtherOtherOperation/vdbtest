#!/usr/bin/env python3

#
# vdbsetup.py - script for building VDbench configurations
#
# Author: Ramon A. Lovato (ramonalovato.com)
# For: DeepStorage, LLC (deepstorage.net)
#

import argparse
import os.path
import os
import re

#
# Factories.
#

# Parent class.
class Factory:
    validNames = []

    def __init__(self, name=None, keys=None):
        self.params = OrderedDict()
        if name:
            self.params["name"] = name
        if keys:
            for key in keys:
                self.params[key] = None

    def addKey(self, key):
        self.params[key] = None

    def set(self, key, *values):
        if not key in self.params:
            self.addKey(key)
        if len(values) < 1:
            raise ValueError("Error: no values passed for key {}.".format(
                key))
        elif len(values) == 1:
            self.params[key] = values[0]
        else:
            self.params[key] = values

    def setName(self, name):
        self.set("name", name)

    def append(self, key, *values):
        if not key in self.params:
            self.set(key, *values)
        else:
            if not isinstance(lst, self.params[key]):
                self.params[key] = [self.params[key]]
            for v in values:
                self.params[key].append(v)

    def toString(self):
        partials = []
        for k, v in self.params.items():
            if not v:
                raise Exception("Error: key {} has value None.".format(k))
            if isinstance(lst, v):
                if len(v) == 0:
                    raise Exception("Error: key {} is empty list.".format(k))
                if len(v) == 1:
                    partial = "{}={}".format(k, v[0])
                else:
                    partial = "{}=({})".format(k, ",".join(v))
            else:
                partial = "{}={}".format(k, v)
            partials.append(partial)

        validNames.append(self.params["name"])

        return ",".join(partials)

class SDFactory(Factory):
    def __init__(self):
        super().__init__(keys=[
            "lun",
            "openflags"
        ])
        self.set("openflags", ["o_direct"])

    def appendOpenFlags(self, *fstrings):
        self.append("openflags", fstrings)

class WDFactory(Factory):
    def __init__(self):
        super().__init__(keys=[
            "sd",
            "xfersize",
            "seekpct",
            "rdpct",
            "skew"
        ])

    def addRange(self, start, end):
        self.set("range", [start, end])

    def setAllSDs(self):
        self.set("sd", SDFactory.validNames)

class RDFactory(Factory):
    def __init__(self):
        super().__init__(keys=[
            "wd",
            "iorate",
            "format",
            "elapsed",
            "interval"
        ])

    def setAllWDs(self):
        self.set("wd", WDFactory.validNames)

#
# Functions.
#

# Get CLI arguments.
def getArgs():
    parser = argparse.ArgumentParser(
        description="create VDbench configuration files")
    # Positional.
    parser.add_argument("inPath", type=str,
        help="where to find the input file")
    parser.add_argument("outPath", type=str,
        help="where to save the configuration out file")

    # Optional.
    parser.add_argument("-h", "--header", type=str,
        help="add a comment header")
    parser.add_argument("-a", "--add-line", type=str,
        help="explicitly add a string as its own line in the file")

    args = parser.parse_args()

    args.outPath = os.path.realpath(args.outPath)

    # Verify directories exist.
    os.makedirs(os.path.dirname(args.outPath), exist_ok=True)

    return args

# Parse the input file.
def parseInput(inPath):
    with open(inPath, "r") as inFile:
        for line in inFile:
            pass # TK

# Build the output configuration file.
def buildOutput(outPath, config):
    with open(outPath, "w") as outFile:
        pass # TK

# Main.
def main():
    args = getArgs()

    try:
        config = parseInput(args.inPath)
    except IOError as e:
        raise e

    try:
        buildOutput(args.outPath, config):
    except IOError as e:
        rase e

if __name__ == "__main__":
    main()