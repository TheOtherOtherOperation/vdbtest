#!/usr/bin/env python3

#
# vdbconfig.py - VDbench Configuration Script
#
# Author: Ramon A. Lovato (ramonalovato.com)
# For: DeepStorage, LLC (deepstorage.net)
#

import argparse
import os.path
import re

def getArgs():
    parser = argparse.ArgumentParser(description="Clone VDbench config files, changing their IO rates.")
    
    parser.add_argument("sourcePath", type=str,
        help="path to VDbench config file to clone and modify")
    parser.add_argument("destPath", type=str,
        help="where to place the output file")
    parser.add_argument("newIORate", type=int,
        help="new IO rate for the output file")

    args = parser.parse_args()

    return args

def tokenize(line):
    return [t.split("=") for t in line.split(",")]

def makeNewConfig(sourcePath, destPath, newIORate):
    with open(sourcePath, "r") as inFile, open(destPath, "w") as outFile:
        for line in inFile:
            if re.match(r"[\/\#\*].*", line):
                outFile.write(line)
            else:
                tokens = tokenize(line)
                for i in range(len(tokens)):
                    token = tokens[i]
                    if len(token) < 1:
                        continue
                    if len(token) < 2:
                        outFile.write(token[0])
                    else:
                        key = token[0]
                        value = token[1]

                        if key == "iorate":
                            value = newIORate

                        outFile.write("{key}={value}{sep}".format(key=key, value=value,
                            sep=("" if i == len(tokens)-1 else ",")))
def main():
    args = getArgs()
    makeNewConfig(args.sourcePath, args.destPath, args.newIORate)

if __name__ == "__main__":
    main()