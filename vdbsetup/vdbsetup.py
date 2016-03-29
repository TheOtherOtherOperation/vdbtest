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
import statistics
import textwrap
import random
import numpy as np
import scipy as sp
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.mlab as mlab
import pylab
from collections import OrderedDict

DEFAULT_MAJOR_DELIMITER = " *= *"
DEFAULT_MINOR_DELIMITER = " *, *"
DEFAULT_MONTE_CARLO_SAMPLES = 200000
DEFAULT_SAMPLE_SCALE = 10000
MAX_RANGE_RETRIES = 10

INPUT_TEMPLATE_CONTENT = """#
# vdbsetup input file example
#

#
# General
#
dedupratio=2
dedupunit=4k
compratio=1.5

#
# SDs
#
luns=lun1,lun2,lun3
# Optional: o_direct provided by default
# openflags=

#
# WDs
#
wdcount=1
xfersize=4k
seekpct=100
rdpct=75
percentdisk=100.0

#
# RDs
#
iorate=1000
format=yes
elapsed=60
interval=1
threads=2

#
# Distribution
#
hotspotnum=10
hotspotcap=25
hotspotiopct=10
disttype=gaussian
# Note: only required if disttype=gaussian
distribution=0.75,0.5
"""

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
    "percentdisk": lambda v: 0 <= float(v) <= 100,
    "iorate": lambda v: float(v) > 0,
    "format": lambda v: re.match("(yes)|(no)", v.lower()),
    "threads": lambda v: int(v) > 0,
    "elapsed": lambda v: int(v) > 0,
    "interval": lambda v: int(v) > 0,
    "hotspotnum": lambda v: int(v) >= 0,
    "hotspotcap": lambda v: 0 <= float(v) <= 100,
    "hotspotiopct": lambda v: 0 <= float(v) <= 100,
    "disttype": lambda v: re.match("(even)|(gaussian)|(uniform)", v.lower())
}
# Dictionary of processing lambdas.
processors = {
    "dedupratio": lambda v: float(v),
    "compratio": lambda v: float(v),
    "wdcount": lambda v: int(v),
    "seekpct": lambda v: float(v),
    "rdpct": lambda v: float(v),
    "percentdisk": lambda v: float(v),
    "iorate": lambda v: float(v),
    "format": lambda v: v.lower(),
    "threads": lambda v: int(v),
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
    "percentdisk": 'Key "percentdisk" requires single percentage in range [0, 100].',
    "iorate": 'Key "iorate" requires positive IOPS value.',
    "format": 'Key "format" must be one of [yes, no].',
    "threads": 'Key "threads" requires positive integer queue depth.',
    "elapsed": 'Key "elapsed" requires positive integer number of seconds.',
    "interval": 'Key "interval" requires positive integer number of seconds.',
    "hotspotnum": 'Key "hotspotnum" requires nonnegative integer number of hotspots.',
    "hotspotcap": 'Key "hotspotcap" requires percentage in range [0, 100].',
    "hotspotiopct": 'Key "hotspotiopct" requires percentage in range [0, 100].',
    "disttype": 'Key "disttype" must be one of "even", "gaussian", "uniform".'
}
multiValidators = {
    "luns": lambda v: len(v) > 0,
    "openflags": lambda v: len(v) > 0,
    "distribution": lambda v:
        config["disttype"] == "gaussian" and
        len(v) == 2 and
        len(list(filter(lambda w: float(w) >= 0, v))) == 2
}
multiProcessors = {
    "luns": lambda v: v,
    "openflags": lambda v: v,
    "distribution": lambda v: list(map(float, v))
}
multiMessages = {
    "luns": 'Key "luns" requires at least one LUN',
    "openflags": 'Key "openflags" requires at least one flag.',
                  '"min,max", such that 0 <= min <= max <= 100.'
    "distribution": 'Key "distribution" is only valid for Gaussian '
                    'distributions, and keys "hotspotnum" and "disttype" must '
                    'be set first. Values must be of form '
                    '"SKEW_STD_DEV,RANGE_STD_DEV", where both standard '
                    'deviations are nonnegative floating point values.'
}

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
    "percentdisk": None,         # How much of the total disk to use

    # RDs
    "iorate": None,              # IOPS
    "format": None,              # Pre-format lun
    "threads": None,             # Qeueue depth
    "elapsed": None,             # Duration
    "interval": None,            # Update frequency

    # Distribution
    "hotspotnum": None,          # Number of hotspots
    "hotspotcap": None,          # Total capacity percent for all hotspots
    "hotspotiopct": None,        # Percent of IO for ALL hotspots
    "disttype": None             # Distribution type: even, gaussian

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
    #     - gaussian  | STANDARD_DEVIATION_SKEW, STANDARD_DEVIATION_RANGE
})

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
            raise ValueError('Error: no values passed for key "{}".'.format(
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
                raise Exception('Error: key "{}" not assigned (value None).'.format(k))
            if isinstance(v, list) or isinstance(v, tuple):
                if len(v) == 0:
                    raise Exception('Error: key {} has length 0.'.format(k))
                if len(v) == 1:
                    partial = "{}={}".format(k, truncate(v[0]))
                else:
                    partial = "{}=({})".format(
                        k, ",".join([str(truncate(w)) for w in v]))
            else:
                partial = "{}={}".format(k, truncate(v))
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
            "rdpct"
        ])

    def addRange(self, r):
        self.set("range", r)

class RDFactory(Factory):
    def __init__(self):
        super().__init__(name_type="rd", keys=[
            "wd",
            "iorate",
            "format",
            "threads",
            "elapsed",
            "interval"
        ])

#
# Functions.
#

# Get CLI arguments.
def getArgs(customArgs=None):
    parser = argparse.ArgumentParser(
        description="create VDbench hotspot-distribution configuration files")

    # Positional.
    parser.add_argument("inPath", type=str, nargs="?",
        default=None,
        help="where to find the input file")
    parser.add_argument("outPath", type=str, nargs="?",
        default=None,
        help="where to output the configuration file")

    # Optional.
    parser.add_argument("--make-template", action="store_true",
        help="create an example input file and exit")
    parser.add_argument("-v", "--verbose", action="store_true",
        help="enable verbose mode")
    parser.add_argument("-gs", "--graph-skews", action="store_true",
        help="enable graph display of the hotspot skews")
    parser.add_argument("-gr", "--graph-ranges", action="store_true",
        help="enale graph display of the hotspots ranges")
    parser.add_argument("--no-overwrite", action="store_true",
        help="don't overwrite output file if it already exists")
    parser.add_argument("--no-shuffle", action="store_true",
        help="disable random hotspot permutation")
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
    parser.add_argument("-c", "--sample-count", type=int,
        default=DEFAULT_MONTE_CARLO_SAMPLES,
        help="number of samples to generate when using Monte Carlo method "
        "to compute distributions (default {}); setting sample size < 10000 "
        "is strongly discourage".format(
            DEFAULT_MONTE_CARLO_SAMPLES))

    if customArgs:
        args = parser.parse_args(customArgs)
    else:
        args = parser.parse_args()

    # If make_template is set, we can just return without the extra checks,
    # since we won't need any of them.
    if args.make_template:
        return args

    # Otherwise, make sure the inPath and outPath were actually set.
    if not args.inPath or args.inPath == "" or not args.outPath or args.outPath == "":
        parser.print_help()
        exit()

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
    # Check sample count.
    if args.sample_count < 10000:
        print("Warning: setting sample size < 10000 is strongly discouraged. "
            "Errors and unspecified behavior may occur.")

    return args

# Parse the input file.
def parseInput(inPath, major_del=DEFAULT_MAJOR_DELIMITER,
    minor_del=DEFAULT_MINOR_DELIMITER, verbose=False):

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
        if (k == "disttype" and v == "gaussian"
            and not "distribution" in config.keys()):
            incompletes.append("distribution required when disttype is "
                "gaussian")
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
    # Keys for which lists are valid.
    if key in multiValidators.keys():
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
        # Short-circuits if key is unchecked.
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

    # Validate the key according to its specific criteria.
    try:
        # Short-circuits if key is unchecked.
        if key in multiValidators.keys() and not multiValidators[key](values):
            printBadLine(line, custom=multiMessages[key])
    except ValueError as e:
        printBadLine(line, custom=multiMessages[key])

    config[key] = (multiProcessors[key](values) if key in multiProcessors.keys() else values)

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
        genList.append("{}={}\n".format(k, truncate(config[k])))
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
def makeSkews(args, config, graph=False):
    skews = []
    mode = config["disttype"]
    hsCount = config["hotspotnum"]
    wdCount = config["wdcount"]
    totalCount = hsCount + wdCount
    ioPct = config["hotspotiopct"]

    # Even.
    if mode == "even":
        skews = [ioPct / totalCount] * hsCount
        # Graph if requested.
        graphSkews(config, mode, skews)

    # Gaussian
    elif mode == "gaussian":
        sigma = config["distribution"][0]
        skews = makeGaussianSkews(sigma, args.sample_count, hsCount, ioPct)
         # Graph if requested.
        graphSkews(config, mode, skews, sigma=sigma)

    # Uniform
    elif mode == "uniform":
        skews = [random.random() for i in range(hsCount)]
        skewSum = sum(skews)
        skews = [ioPct * s / skewSum for s in skews]
        # Graph if requested.
        graphSkews(config, mode, skews)

    # Shuffle.
    if not args.no_shuffle:
        random.shuffle(skews)

    return skews

# Use Monte Carlo method to determine the skews for the hotspots by generating
# sampleCount samples in the Gaussian distribution f(X | mu, sigma^2) and
# determining what the probability is of a sample ending up in each bucket.
#
# @param dev Standard deviation for the normal distribution.
# @param sampleCount Number of samples to generate.
# @param hSCount Number of hotspots to generate.
# @param ioPct Percentage of total IOs to split among skews (ioPct * skew).
def makeGaussianSkews(sigma, sampleCount, hsCount, ioPct):
    # Generate many samples sorted by natural ordering.
    samples = getGaussianSamples(0.0, sigma, sampleCount)

    # Calculate the hotspot bucket boundaries.
    hsRanges = []

    # Determine number of samples in each bucket.
    buckets = getBucketCounts(samples, -1.0, 1.0, hsCount)

    # Determine skews.
    bucketSum = sum(buckets)
    skews = [ioPct * (b / bucketSum) for b in buckets]

    return skews

# Helper function for the Gaussian sampling procedures that returns the buckets
# for a given *sorted* collection of samples.
#
# @param samples Sorted list of samples to count for the buckets.
# @param distMin Minimum sample value we care about. Samples < distMin are
#                ignored.
# @param distMax Maximum sample value we care about. Samples >= distMax are
#                ignored.
# @param bucketCount Number of buckets to generate.
# @return List of buckets containing the number of samples in each.
def getBucketCounts(samples, distMin, distMax, bucketCount):
    distRange = abs(distMax - distMin)
    assert distRange > 0, "distRange = 0"
    assert bucketCount > 0, "bucketCount = 0"
    distStride = float(distRange) / bucketCount
    # Calculate bucket boundaries. We do it this way instead of using
    # np.arrange because we care more about the list being the right length
    # than about small floating point errors.
    bucketBounds = [distMin + (distStride * i) for i in range(bucketCount)]

    # Sanity check to make sure we generated the right number of buckets.
    assert len(bucketBounds) == bucketCount, "Generated wrong number of buckets"

    # Determine number of samples in each bucket.
    buckets = []

    for bucketIt in range(len(bucketBounds)):
        buckets.append(0)
        bucketMin = bucketBounds[bucketIt]
        bucketMax = distMax if bucketIt >= len(bucketBounds)-1 else bucketBounds[bucketIt + 1]
        # Slow but reliable.
        buckets[bucketIt] = len(list(filter(lambda s: bucketMin <= s < bucketMax,
            samples)))

    return buckets

# Helper function for generating a sorted list of samples from a Gaussian
# distribution.
def getGaussianSamples(mu, sigma, sampleCount):
    samples = np.random.normal(mu, sigma, sampleCount)
    samples.sort()
    return samples

# Graph Gaussian skews histogram using matplotlib.
#
# @param skews Skews to graph.
# @param binCount Number of bins for the histogram.
# @param mu Mean of the distribution. If None, will be determined automatically
#           from the mean of samples.
# @param sigma Standard deviation of the distribution. If None, will be
#           determined automatically from the standard deviation of samples.
def graphGaussianSkews(skews, binCount, sigma=None):
    barX = np.arange(len(skews))
    barY = np.array(skews)

    plt.bar(barX, barY, 1, color="blue")
    plt.draw()

# Graph a bar chart of skews using matplotlib.
#
# @param skews Skews to graph.
# @param yLim Max value for y-axis.
def graphSkewBars(skews, yLim):
    x = range(len(skews))
    y = np.array(skews)
    width = 1
    plt.bar(x, y, width, color="blue")
    plt.draw()

# Graph the skews distribution using matplotlib.
#
# @param config Configuration dictionary.
# @param mode Distribution type: "gaussian" or "even".
# @param skews Skews distribution.
# @param sigma Standard deviation of the distribution.
def graphSkews(config, mode, skews, sigma=None):
    plt.figure(1)
    fig = plt.figure(1)
    fig.suptitle("Skews - mode: {}".format(mode))
    plt.xlabel("Hotspot number")
    plt.ylabel("Percentage of IOs")
    graphSkewBars(skews, config['hotspotiopct'])

# Graph the ranges distribution histogram using matplotlib.
#
# @param config Configuration dictionary.
# @param ranges Range distribution.
# @param skews Skews distribution.
def graphRanges(config, ranges, skews):
    plt.figure(2)
    fig = plt.figure(2)
    fig.suptitle("Ranges - mode: {}".format(config["disttype"]))
    plt.xlabel("Disk location")
    plt.ylabel("Percentage of IOs")

    count = config["hotspotnum"]
    ioPct = config["hotspotiopct"]
    
    # Sanity check.
    assert count == len(ranges) == len(skews), "The number of ranges or skews is incorrect."

    triplets = []
    for i in range(count):
        x = ranges[i][0]
        y = skews[i]
        w = ranges[i][1]-x
        triplets.append((x, y, w))
    triplets.sort(key=lambda t: t[0])

    x = np.array([triplets[i][0] for i in range(count)])
    y = np.array([triplets[i][1] for i in range(count)])
    widths = np.array([triplets[i][2] for i in range(count)])

    plt.bar(x, y, widths, color="blue")
    plt.draw()
    pylab.xlim([0, 100])


# Use Monte Carlo method to determine the ranges for the hotspots by generating
# 2 * sampleCount samples in the Gaussian distribution f(X | mu, sigma^2) and
# counting the samples that sit above the mean.
#
# @param dev Standard deviation for the normal distribution.
# @param halfCount One-half the number of samples to generate. This number
#                  will be doubled so that 2 * halfCount samples are generated.
# @param hSCount Number of hotspots to generate.
# @param capacity Percentage of total capacity to split among all hotspots.
def getGaussianRangeComponents(sigma, halfCount, hsCount, capacity, percentDisk):  
    # Calculate sizes via uniform-random sampling.
    sizes = [random.random() for i in range(hsCount)]
    partSum = sum(sizes)
    for i in range(len(sizes)):
        sizes[i] = capacity * (sizes[i] / partSum)

    # Calculate positions from a Gaussian distribution. In order to skew
    # the positions near the beginning of the disk, we generate double the
    # number of input samples and only count those that are above the mean.
    sampleCount = 2 * halfCount

    # Generate many samples sorted by natural ordering.
    samples = getGaussianSamples(0.0, sigma, sampleCount)

    buckets = getBucketCounts(samples, 0.0, 1.0, hsCount)
    buckets.reverse()

    # Determine start positions.
    bucketSum = sum(buckets)
    positions = []
    for i in range(hsCount):
        b = percentDisk * buckets[i] / bucketSum
        if i > 0:
            b += positions[i-1]
        if b < 0.0:
            b = 0.0
        elif b > percentDisk:
            b = percentDisk
        positions.append(b)

    # Sanity check to make sure we generated the same number of sizes and
    # positions.
    assert len(sizes) == len(positions) == hsCount, "Generated an unequal number of sizes and positions."

    return sizes, positions

# Helper function for assembling ranges from sizes and positions.
def assembleRanges(sizes, positions, hsCount, capacity, percentDisk,
    noShuffle=False):
    ranges = []
    hsSum = 0

    # We deliberately don't break out of the loop early in the event of
    # overflow. We could do that, but it would result in our generating the
    # wrong number of ranges, which would cause problems later. Instead,
    # we let the loop continue, which will generate ranges of size 0 for all
    # those after the overflow occurred.
    for i in range(hsCount):
        r = assembleRangesHelper(ranges, positions[i], sizes[i], capacity,
            percentDisk, hsSum)
        ranges.append(r)
        hsSum += r[1] - r[0]
        # Need to resort the ranges after each iteration in case we added one
        # out of order.
        ranges.sort(key=lambda r: r[0])

    if not noShuffle:
        random.shuffle(ranges)

    return ranges

# Helper for assembleRanges that tries to construct a new range according to
# specifications.
#
# @param ranges Currently allotted ranges.
# @param size Size of the range to generate.
# @param capacity Maximum size of sum of all hotspots.
# @param percentDisk Maximum percent of disk we're allowed to use.
# @param hsSum The current sum of all hotspot sizes.
def assembleRangesHelper(ranges, position, size, capacity, percentDisk, hsSum):
    if hsSum + size > capacity:
        size = capacity - hsSum
    hsSize = formatRangeVal(size)

    assert hsSize > 0.0, "Size 0 hotspot generated."

    hsStart = formatRangeVal(position)
    hsEnd = formatRangeVal(hsStart + size)

    if checkRangeConflicts(ranges, hsStart, hsEnd):
        hsStart = ranges[-1][1]
        hsEnd = formatRangeVal(hsStart + size)

    # We exceeded the capacity. Try to insert it at a (uniform) random position.
    if not checkRangeVals(hsStart, hsEnd, percentDisk):
        tries = 0
        while True:
            hsStart = formatRangeVal(random.uniform(0.0, percentDisk))
            hsEnd = formatRangeVal(hsStart + size)
            if (checkRangeVals(hsStart, hsEnd, percentDisk) and not
                checkRangeConflicts(ranges, hsStart, hsEnd)):
                break
            tries += 1
            if tries >= MAX_RANGE_RETRIES:
                raise Exception("Error: unable to generate random non-overlapping range within {} tries.".format(
                    MAX_RANGE_RETRIES))

    # Sanity check.
    assert checkRangeVals(hsStart, hsEnd, percentDisk), "Generated an invalid range: ({},{}). Allowed percentage of disk: {}.".format(
        hsStart, hsEnd, percentDisk)

    return (hsStart, hsEnd)

# Format a range value by truncating it to two decimal places.
def formatRangeVal(val):
    return float(truncate(val))

# Check if range is valid stand-alone, but does not check for conflicts.
def checkRangeVals(start, end, percentDisk):
    return 0.0 <= start < end <= percentDisk

# Check for range conflict.
#
# @param ranges Currently allotted ranges.
# @param start Start of range.
# @param end End of range.
def checkRangeConflicts(ranges, start, end):
    for r in ranges:
        if r[0] <= start < r[1]:
            return True
    return False

# Make uniform random ranges.
def makeUniformRanges(hsCount, hsSpace, percentDisk):
    sizes = []
    positions = []
    for i in range(hsCount):
        sizes.append(random.random())
        positions.append(random.uniform(0.0, percentDisk))
    positions.sort()
    sizeSum = sum(sizes)
    sizes = [hsSpace * s / sizeSum for s in sizes]
    return assembleRanges(sizes, positions, hsCount, hsSpace, percentDisk)

# Create hotspot range distribution.
def makeRanges(args, config):
    ranges = []
    mode = config["disttype"]
    hsCount = config["hotspotnum"]
    wdCount = config["wdcount"]
    totalCount = hsCount + wdCount
    hsSpace = config["hotspotcap"]
    percentDisk = config["percentdisk"]

    # Even
    if mode == "even":
        width = hsSpace / hsCount
        freeSpace = percentDisk - hsSpace
        gapCount = hsCount + 1
        gapWidth = freeSpace / gapCount
        stride = width + gapWidth

        for i in range(hsCount):
            start = (i * stride) + gapWidth
            end = start + width
            ranges.append((start, end))

    # Gaussian
    elif mode == "gaussian":
        sigma = config["distribution"][1]
        sizes, positions = getGaussianRangeComponents(sigma, args.sample_count,
            hsCount, hsSpace, percentDisk)
        ranges = assembleRanges(sizes, positions, hsCount,
            hsSpace, config["percentdisk"], noShuffle=args.no_shuffle)

    # Uniform random
    elif mode == "uniform":
        ranges = makeUniformRanges(hsCount, hsSpace, percentDisk)

    return ranges

# Make workload definitions.
def makeWDs(args, config):
    wdList = []
    wdCount = config["wdcount"]
    hsCount = config["hotspotnum"]
    percentDisk = config["percentdisk"]
    skews = makeSkews(args, config)
    ranges = makeRanges(args, config)

    # Setup range graph if requested.
    if args.graph_ranges:
        graphRanges(config, ranges, skews)
    total = wdCount + hsCount
    
    for i in range(total):
        wdf = WDFactory()
        wdf.setName("wd{}".format(i+1))
        wdf.set("sd", "sd*")
        wdf.set("xfersize", config["xfersize"])
        wdf.set("seekpct", config["seekpct"])
        wdf.set("rdpct", config["rdpct"])
        if percentDisk != 100.0:
            wdf.addRange((0, percentDisk))
        # Hotspot.
        if i >= wdCount:
            j = i - wdCount - 1
            wdf.set("skew", skews[j])
            wdf.addRange(ranges[j])
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
    rdf.set("threads", config["threads"])
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
        lines = makeWDs(args, config)
        outFile.writelines(lines)

        # RDs
        lines = makeRDs(config)
        outFile.writelines(lines)

# If the input is a floating point number, truncate it to three decimal places.
# If it's an integer (its fractional portion is 0), return it as an integer.
# Else return it unchanged.
def truncate(f):
    if isinstance(f, float):
        if f.is_integer():
            return int(f)
        return "{0:.2f}".format(f)
    return f

# Create an input file template.
def makeTemplate():
    templatePath = "vdbsetup_input_template.txt"
    with open(templatePath, "w") as f:
        f.write(INPUT_TEMPLATE_CONTENT)
    print('Input file example saved as "{}".'.format(templatePath))

# Main.
def main():
    args = getArgs()

    if args.verbose:
        print("Verbose logging enabled.\n")

    if args.make_template:
        try:
            makeTemplate()
        except IOError as e:
            raise e
        finally:
            return

    try:
        config = parseInput(args.inPath, major_del=args.major_delimiter,
            minor_del=args.minor_delimiter, verbose=args.verbose)
    except IOError as e:
        raise e

    try:
        buildOutput(args, config, verbose=args.verbose)
    except IOError as e:
        raise e

    if args.graph_skews or args.graph_ranges:
        plt.show()

if __name__ == "__main__":
    main()