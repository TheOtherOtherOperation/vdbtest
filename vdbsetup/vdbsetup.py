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
import textwrap
import numpy as np
import scipy as sp
import matplotlib as mpl
import matplotlib.pyplot as plt
from collections import OrderedDict

DEFAULT_MAJOR_DELIMITER = " *= *"
DEFAULT_MINOR_DELIMITER = " *, *"

#
# Helper dictionaries for single-entry input parsing.
#

# Dictionary of validation lambdas.
validators = {
    "dedupratio": lambda v: float(v) >= 0,
    "compratio": lambda v: float(v) >= 0,
    "wdcount": lambda v: float(v) > 0,
    "seekpct": lambda v: 0 <= float(v) <= 100,
    "rdpct": lambda v: 0 <= float(v) <= 100,
    "iorate": lambda v: float(v) > 0,
    "format": lambda v: re.match("(yes)|(no)", v.lower()),
    "elapsed": lambda v: int(v) > 0,
    "interval": lambda v: int(v) > 0,
    "hotspotnum": lambda v: int(v) >= 0,
    "hotspotcap": lambda v: 0 <= float(v) <= 100,
    "hotspotiopct": lambda v: 0 <= float(v) <= 100,
    "disttype": lambda v: re.match("(even)|(gaussian)|(custom)", v.lower())
}
# Dictionary of processing lambdas.
processors = {
    "dedupratio": lambda v: float(v),
    "compratio": lambda v: float(v),
    "wdcount": lambda v: int(v),
    "seekpct": lambda v: float(v),
    "rdpct": lambda v: float(v),
    "iorate": lambda v: float(v),
    "format": lambda v: v.lower(),
    "elapsed": lambda v: int(v),
    "interval": lambda v: int(v),
    "hotspotnum": lambda v: int(v),
    "hotspotcap": lambda v: float(v),
    "hotspotiopct": lambda v: float(v),
    "disttype": lambda v: v.lower()
}
# Dictionary of custom usage messages.
messages = {
    "dedupratio": 'Key "dedupratio" requires nonnegative value.',
    "compratio": 'Key "compratio" requires nonnegative value.',
    "wdcount": 'Key "wdcount" requires positive integer value.',
    "seekpct": 'Key "seekpct" requires percentage in range [0, 100].',
    "rdpct": 'Key "rdpct" requires percentage in range [0, 100].',
    "iorate": 'Key "iorate" requires positive IOPS value.',
    "format": 'Key "format" must be one of [yes, no].',
    "elapsed": 'Key "elapsed" requires positive integer number of seconds.',
    "interval": 'Key "interval" requires positive integer number of seconds.',
    "hotspotnum": 'Key "hotspotnum" requires nonnegative integer number of hotspots.',
    "hotspotcap": 'Key "hotspotcap" requires percentage in range [0, 100].',
    "hotspotiopct": 'Key "hotspotiopct" requires percentage in range [0, 100].',
    "disttype": 'Key "disttype" must be one of [even, gaussian, custom].'
}

#
# Factories.
#

# Parent class.
class Factory:
    def __init__(self, name_type="name", name=None, keys=None):
        self.name_type=name_type
        self.params = OrderedDict()
        self.params[name_type] = name
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
        self.set(self.name_type, name)

    def append(self, key, *values):
        if len(values) == 0:
            return
        if not key in self.params:
            self.set(key, values)
        else:
            if not isinstance(self.params[key], list):
                self.params[key] = [self.params[key]]
            for v in values:
                if isinstance(v, list):
                    for w in v:
                        self.params[key].append(w)
                else:
                    self.params[key].append(v)

    def toString(self):
        partials = []
        for k, v in self.params.items():
            if v == None:
                raise Exception("Error: key {} has value None.".format(k))
            if isinstance(v, list) or isinstance(v, tuple):
                if len(v) == 0:
                    raise Exception("Error: key {} is empty.".format(k))
                if len(v) == 1:
                    partial = "{}={}".format(k, v[0])
                else:
                    partial = "{}=({})".format(
                        k, ",".join([str(w) for w in v]))
            else:
                partial = "{}={}".format(k, v)
            partials.append(partial)

        return ",".join(partials)

class SDFactory(Factory):
    def __init__(self):
        super().__init__(name_type="sd", keys=[
            "lun",
            "openflags"
        ])
        self.set("openflags", ["o_direct"])

    def appendOpenFlags(self, *fstrings):
        # Filter out duplicates, including "o_direct, since it's provided by
        # default.
        for f in fstrings:
            for g in f:
                if g not in self.params["openflags"]:
                    self.append("openflags", g)

class WDFactory(Factory):
    def __init__(self):
        super().__init__(name_type="wd", keys=[
            "sd",
            "xfersize",
            "seekpct",
            "rdpct",
        ])

    def addRange(self, r):
        self.set("range", r)

class RDFactory(Factory):
    def __init__(self):
        super().__init__(name_type="rd", keys=[
            "wd",
            "iorate",
            "format",
            "elapsed",
            "interval"
        ])

#
# Functions.
#

# Get CLI arguments.
def getArgs():
    parser = argparse.ArgumentParser(
        description="create VDbench hotspot-distribution configuration files")
    # Positional.
    parser.add_argument("inPath", type=str,
        help="where to find the input file")
    parser.add_argument("outPath", type=str,
        help="where to output the configuration file")

    # Optional.
    parser.add_argument("-v", "--verbose", action="store_true",
        help="enable verbose mode")
    parser.add_argument("-g", "--graph", action="store_true",
        help="enable graph display of the resulting hotspot distribution")
    parser.add_argument("--no-overwrite", action="store_true",
        help="don't overwrite output file if it already exists")
    parser.add_argument("--header", type=str,
        help="add a comment header")
    parser.add_argument("-M", "--major-delimiter", type=str,
        default=DEFAULT_MAJOR_DELIMITER,
        help='major delimiter regex used in configuration file (default "{}")'.format(
            DEFAULT_MAJOR_DELIMITER))
    parser.add_argument("-m", "--minor-delimiter", type=str,
        default=DEFAULT_MINOR_DELIMITER,
        help='minor delimiter regex used in configuration file (default "{}"")'.format(
            DEFAULT_MINOR_DELIMITER))

    args = parser.parse_args()

    args.outPath = os.path.realpath(args.outPath)

    # Verify input file exists.
    if not os.path.exists(args.inPath):
        print("Error: input file {} does not exist.".format(args.inPath))
        exit()
    elif not os.path.isfile(args.inPath):
        print("Error: input path {} is not a valid file.".format(args.inPath))
        exit()
    # Verify output directories exist.
    os.makedirs(os.path.dirname(args.outPath), exist_ok=True)
    # Check delimiters.
    if not args.major_delimiter or len(args.major_delimiter) == 0:
        print("Error: major delimiter cannot be empty. Using default ({}).".format(
            DEFAULT_MAJOR_DELIMITER))
        args.major_delimiter = DEFAULT_MAJOR_DELIMITER
    elif not args.minor_delimiter or len(args.minor_delimiter) == 0:
        print("Error: minor_delimiter cannot be empty, Using default ({}).".format(
            DEFAULT_MINOR_DELIMITER))
    elif args.major_delimiter == args.minor_delimiter:
        print("Error: major and minor delimiter cannot be the same. Using defaults ({}, {}).".format(
            DEFAULT_MAJOR_DELIMITER, DEFAULT_MINOR_DELIMITER))
        args.major_delimiter = DEFAULT_MAJOR_DELIMITER
        args.minor_delimiter = DEFAULT_MINOR_DELIMITER

    return args

# Parse the input file.
def parseInput(inPath, major_del=DEFAULT_MAJOR_DELIMITER,
    minor_del=DEFAULT_MINOR_DELIMITER, verbose=False):
    # Uses an OrderedDict because certain parameters must be specified before
    # other parameters.
    config = OrderedDict({
        # General
        "dedupratio": None,          # Deduplication ratio
        "dedupunit": None,           # Deduplication unit
        "compratio": None,           # Compression ratio

        # SDs
        "luns": None,                # Luns, list OK

        # WDs
        "wdcount": None,             # Number of workloads
        "xfersize": None,            # Block size
        "seekpct": None,             # Percent random
        "rdpct": None,               # Percent read (vs. write)

        # RDs
        "iorate": None,              # IOPS
        "format": None,              # Pre-format lun
        "elapsed": None,             # Duration
        "interval": None,            # Update frequency

        # Distribution
        "hotspotnum": None,          # Number of hotspots
        "hotspotcap": None,          # Total capacity percent for all hotspots
        "hotspotiopct": None,        # Percent of IO for ALL hotspots
        "disttype": None             # Distribution type: even, gaussian, custom

        #
        # Added inline only if needed
        #

        # "openflags": []
        #     - open flags for SDs
        #     - o_direct provided by default as block devices require it

        # "distribution": []
        #     - parameters for the distribution type
        #     
        #       Type      | Params
        #       ------------------------------------------
        #     - even      | WIDTH
        #     - gaussian  | MEAN, STANDARD_DEVIATION
        #     - custom    | HS_1_pct, HS_2_pct, ...
    })

    with open(inPath, "r") as inFile:
        for realLine in inFile:
            line = realLine.strip()
            
            # Comment or empty.
            if len(line) == 0 or line.startswith("#"):
                continue

            tokens = re.split(major_del, line, maxsplit=1)
            if len(tokens) < 2:
                printBadLine(line)
            elif len(tokens[1]) < 1:
                printBadLine(line, custom="Empty value.")

            key = tokens[0].lower()
            values = [stripQuotes(v) for v in re.split(minor_del, tokens[1])]

            parseLine(key, values, line, config)

    # Check for incomplete entries.
    incompletes = []
    for k, v in config.items():
        if not v:
            incompletes.append(k)
        if (k == "disttype" and (v == "gaussian" or v == "custom")
            and not "distribution" in config.keys()):
            incompletes.append("distribution (required when disttype is "
                "gaussian or custom")
        if verbose:
            print("{}={}".format(k, str(v)))
    if len(incompletes) > 0:
        print("\nError: input file is missing the following specifications:")
        for k in incompletes:
            print("    - {}".format(k))
        exit()

    return config

# Evaluate a single input line.
def parseLine(key, values, line, config):
    # Keys for which lists are acceptable.
    listKeys = [
        "luns",
        "openflags",
        "distribution"
    ]

    if key in listKeys:
        parseListHelper(key, values, line, config)
    else:
        parseSingleHelper(key, values, line, config)

# Nonlist helper for parseLine.
def parseSingleHelper(key, values, line, config):
    if len(values) != 1:
        printBadLine(line, custom='Key "{}" accepts exactly one value.'.format(
            key))

    value = values[0]

    # Validate the key exists.
    validateKey(key, line, config)

    # Validate the key according to its specific criteria.
    try:
        # Short-circuits if no validator for this key.
        if key in validators.keys() and not validators[key](value):
            printBadLine(line, custom=messages[key])
    except ValueError as e:
        printBadLine(line, custom=messages[key])

    config[key] = (processors[key](value) if key in processors.keys() else value)

# List helper for parseLine.
def parseListHelper(key, values, line, config):
    # Distribution and openflags are special and get added only if present.
    if key == "distribution":
        if not config["hotspotnum"] or not config["disttype"]:
            printBadLine(line,
                custom='Keys "hotspotnum" and "disttype" must be specified before "distribution".')
        config["distribution"] = None

    if key == "openflags":
        config["openflags"] = None        

    # Validate the key exists.
    validateKey(key, line, config)

    # Get the lists out of the way first:
    #     - luns
    #     - openflags
    if key == "luns":
        if len(values) < 1:
            printBadLine(line, custom="No LUNs specified.")
        config["luns"] = values
    elif key == "openflags":
        config["openflags"] = values

    # Distribution specifications:
    #     - even: [] WIDTH
    #     - gaussian: [MEAN, STANDARD_DEVIATION]
    #     - custom: [HS_1_pct, HS_2_pct, ...]
    elif key == "distribution":
        distType = config["disttype"]
        if distType == "even":
            printBadLine(line,
                custom="Even distributions do not accept distribution specifications.") 
        if distType == "gaussian":
            if len(values) != 1:
                printBadLine(line,
                    custom="Gaussian distribution requires exactly one value for standard deviation.")
            try:
                v = float(values[0])
                if v < 0:
                    printBadLine(line,
                        custom="Standard deviation cannot be negative.")
            except ValueError as e:
                printBadLine(line,
                    custom="Value {} is not a valid standard deviation.".format(v))
        elif distType == "custom":
            if len(values) != config["hotspotnum"]:
                printBadLine(line,
                    custom='Number of distribution percentages ({}) does not equal number of hotspots ({}).'.format(
                        len(values), config["hotspotnum"]))
            total = 0.0
            for v in values:
                try:
                    i = float(v)
                    if i < 0.0 or i > 100.0:
                        printBadLine(line,
                            custom="Value {} is not in range [0, 100].".format(v))
                    total += i
                except ValueError as e:
                    printBadLine(line,
                        custom="Value {} is not a valid perentage.".format(v))
                if total > 100.0:
                    printBadLine(line,
                        custom="Sum of distribution percentages exceeds 100 percent.")
        try:
            config["distribution"] = list(map(float, values))
        except ValueError as e:
            printBadLine(line,
                custom="Distribution values must be floating point numbers.")

    # Unknown.
    else:
        printBadLine(line, custom='Unrecognized line: {}.'.format(line))

# Validate a key.
def validateKey(key, line, config):
    # Check to make sure the key is recognized.
    if key not in config:
        printBadLine(line, "Unrecognized key: {}.".format(key))

    # Check to make sure the key isn't a duplicate.
    if config[key]:
        printBadLine(line, "Duplicate specification.")

# Strip quotes.
def stripQuotes(string):
    if re.match(r"^[\"\'].*[\"\']$", string):
        return string[1:-1]
    else:
        # Nothing to do.
        return string

# Print uninterpretable line error and exit.
def printBadLine(line, custom=None):
    print('Error: bad input line "{}".{}'.format(line,
        " {}".format(custom) if custom else ""))
    exit()

# Create a header comment block.
def makeCommentHeader(header):
    wrapper = textwrap.TextWrapper(
        width=70, initial_indent="# ", subsequent_indent="# ",
        expand_tabs=True, drop_whitespace=True, fix_sentence_endings=False,
        break_long_words=True, break_on_hyphens=True)
    return ["#\n"] + wrapper.wrap(header) + ["\n#\n"]

# Create general configuration lines.
def makeGeneral(config):
    genList = []
    for k in ["dedupratio", "dedupunit", "compratio"]:
        genList.append("{}={}\n".format(k, config[k]))
    return genList

# Create storage definitions.
def makeSDs(config):
    sdList = []
    i = 0
    for lun in config["luns"]:
        i += 1
        sdf = SDFactory()
        sdf.setName("sd{}".format(i))
        sdf.set("lun", lun)
        sdf.appendOpenFlags(config["openflags"])
        sdList.append(sdf.toString() + "\n")
    return sdList

# Create skews -- percentage of allotted hotspot IO percentage that goes to
# each hotspot.
def makeSkews(config):
    skews = []
    mode = config["disttype"]
    hsCount = config["hotspotnum"]
    wdCount = config["wdcount"]
    totalCount = hsCount + wdCount
    ioPct = config["hotspotiopct"]

    # Even.
    if mode == "even":
        skews = [ioPct / totalCount] * hsCount

    # Gaussian
    elif mode == "gaussian":
        # Mean: percentage of IOs / number of hotspots
        mu = ioPct / hsCount
        print(mu)
        # Standard deviation as a percentage of mean: user-tunable
        dev = config["distribution"][0]
        skews = getGaussianSamples(mu, sigma, hsCount, ioPct)

    # Custom
    elif mode == "custom":
        skews = [0] * hsCount # TODO

    return skews

# Generate n samples from a Gaussian distribution normalized to a specific
# value.
#
# @param mean Mean average value we want for samples.
# @param dev Standard deviation *as a percentage of the mean*. E.g. if dev = 5,
#            the standard deviation for the normal distribution will be
#            specified as mu * 0.5.
# @param count Number of samples to generate.
# @param target Target sum for all samples. Samples will be normalized against
#               this value so that the sum of all samples returned equals target
#               (allowing for small floating-point errors).
#
def getGaussianSamples(mu, dev, count, target):
    # sigma = (dev/100) * mu
    sigma = dev
    samples = np.random.normal(mu, sigma, count)
    sampleSum = sum(samples)
    ratio = target / sampleSum
    return [(ratio * s) for s in samples]

# Graph a distribution using matplotlib.
def graphDistribution():
    mu, sigma = 0, 0.1 # mean and standard deviation
    s = np.random.normal(mu, sigma, 1000)
    count, bins, ignored = plt.hist(s, 30, normed=True)
    plt.plot(bins, 1/(sigma * np.sqrt(2 * np.pi)) *
        np.exp( - (bins - mu)**2 / (2 * sigma**2) ), linewidth=2, color='r')
    plt.show()

# Create hotspot distribution -- ranges for each hotspot such that the sum
# of their sizes eq
def makeHotspots(config):
    hotspots = []
    mode = config["disttype"]
    hsCount = config["hotspotnum"]
    wdCount = config["wdcount"]
    totalCount = hsCount + wdCount
    hsSpace = config["hotspotcap"]

    # Even
    if mode == "even":
        width = hsSpace / hsCount
        freeSpace = 100.0 - hsSpace
        gapCount = hsCount + 1
        gapWidth = freeSpace / gapCount
        stride = width + gapWidth

        for i in range(hsCount):
            start = (i * stride) + gapWidth
            end = start + width
            hotspots.append((start, end))

    # Gaussian
    elif mode == "gaussian":
        hotspots = [(0, 0)] * hsCount # TODO
    # Custom
    elif mode == "custom":
        hotspots = [(0, 0)] * hsCount # TODO
    
    for i in range(config["hotspotnum"]):
        hotspots.append((0, 0)) # TODO

    return hotspots

# Make workload definitions.
def makeWDs(config):
    wdList = []
    wdCount = config["wdcount"]
    hsCount = config["hotspotnum"]
    skews = makeSkews(config)
    hotspots = makeHotspots(config)
    total = wdCount + hsCount
    for i in range(total):
        wdf = WDFactory()
        wdf.setName("wd{}".format(i+1))
        wdf.set("sd", "sd*")
        wdf.set("xfersize", config["xfersize"])
        wdf.set("seekpct", config["seekpct"])
        wdf.set("rdpct", config["rdpct"])
        # Hotspot.
        if i >= wdCount:
            j = i - wdCount - 1
            wdf.set("skew", skews[j])
            wdf.addRange(hotspots[j])
        wdList.append(wdf.toString() + "\n")
    return wdList

# Make run definitions.
def makeRDs(config):
    rdList = []
    # There's only one RD per file, so the list is more for consistency.
    rdf = RDFactory()
    rdf.setName("rd1")
    rdf.set("wd", "wd*")
    rdf.set("iorate", config["iorate"])
    rdf.set("format", config["format"])
    rdf.set("elapsed", config["elapsed"])
    rdf.set("interval", config["interval"])
    rdList.append(rdf.toString() + "\n")
    return rdList

# Build the output configuration file.
def buildOutput(args, config, verbose=False):
    outPath = args.outPath
    if args.no_overwrite and os.path.exists(outPath):
        i = 0
        while os.path.exists(outPath):
            i += 1
            outPath = "{} ({})".format(args.outPath, str(i))

    with open(outPath, "w") as outFile:
        print("\nOutput saved as {}".format(outPath))

        if args.header:
            outFile.writelines(makeCommentHeader(args.header))

        # General
        lines = makeGeneral(config)
        outFile.writelines(lines)

        # SDs
        lines = makeSDs(config)
        outFile.writelines(lines)

        # WDs and distribution
        lines = makeWDs(config)
        outFile.writelines(lines)

        # RDs
        lines = makeRDs(config)
        outFile.writelines(lines)

# Main.
def main():
    verbose = False

    args = getArgs()

    if args.verbose:
        verbose = True
        print("Verbose logging enabled.\n")

    try:
        config = parseInput(args.inPath, major_del=args.major_delimiter,
            minor_del=args.minor_delimiter, verbose=verbose)
    except IOError as e:
        raise e

    try:
        buildOutput(args, config, verbose=verbose)
    except IOError as e:
        raise e

if __name__ == "__main__":
    main()