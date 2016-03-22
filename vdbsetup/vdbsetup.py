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
from collections import OrderedDict

DEFAULT_MAJOR_DELIMITER = " *= *"
DEFAULT_MINOR_DELIMITER = " *, *"
DEFAULT_MONTE_CARLO_SAMPLES = 200000

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
    "disttype": lambda v: re.match("(even)|(gaussian)", v.lower())
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
    "disttype": 'Key "disttype" must be one of [even, gaussian].'
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
    parser.add_argument("-c", "--sample-count", type=int,
        default=DEFAULT_MONTE_CARLO_SAMPLES,
        help="number of samples to generate when using Monte Carlo method "
        "to compute distributions (default {}); setting sample size < 10000 "
        "is strongly discourage".format(
            DEFAULT_MONTE_CARLO_SAMPLES))

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
    # Check sample count.
    if args.sample_count < 10000:
        print("Warning: setting sample size < 10000 is strongly discouraged. "
            "Errors and unspecified behavior may occur.")

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
        #     - gaussian  | MEAN, STANDARD_DEVIATION
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

    # Gaussian
    elif mode == "gaussian":
        sigma = config["distribution"][0]
        skews = getGaussianSkews(0, sigma, args.sample_count, hsCount, ioPct)

    # Graph if requested.
    if args.graph:
        if mode == "gaussian":
            graphGaussianSkews(skews, 1000)

    return skews

# Use Monte Carlo method to determine the skews for the hotspots by generating
# sampleCount samples in the Gaussian distribution f(X | mu, sigma^2) and
# determining what the probability is of a sample ending up in each bucket.
#
# @param mean Mean average value we want for samples in the normal distribution.
# @param dev Standard deviation for the normal distribution.
# @param sampleCount Number of samples to generate.
# @param hSCount Number of hotspots to generate.
# @param ioPct Percentage of total IOs to split among skews (ioPct * skew).
# @param stdDevs Maximum distance from the mean we want to use in calculating
#        our hotspot buckets. If None, the maximum distance will be calculated
#        programatically by splitting the range between the smallest and
#        largest samples.
#            - Set to 3.0 by default since for a random variable with a
#              standard normal distribution, 99.7% of samples fall within
#              3 standard deviations of the mean, via the 68-95-99.7 rule.
def getGaussianSkews(mu, sigma, sampleCount, hsCount, ioPct, stdDevs=3.0):
    # Generate many samples sorted by natural ordering.
    samples = getGaussianSamples(mu, sigma, sampleCount)

    # Calculate the hotspot bucket boundaries.
    hsRanges = []
    
    # If stdDevs is None or <= 0, calculate based on the range between the
    # smallest and largest samples.
    if stdDevs == None or stdDevs <= 0.0:
        distMin = min(samples)
        distMax = max(samples)
    else:
        distMin = mu - (stdDevs * sigma)
        distMax = mu + (stdDevs * sigma)

    # Determine number of samples in each bucket.
    buckets = getBucketCounts(samples, distMin, distMax, hsCount)

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
    # Calculate bucket boundaries.
    bucketBounds = list(np.arange(distMin, distMax, distStride))

    # Sanity check to make sure we generated the right number of buckets.
    assert len(bucketBounds) == bucketCount, "Generated wrong number of buckets."

    # Determine number of samples in each bucket.
    buckets = []
    sampleIt = 0

    for bucketIt in range(len(bucketBounds)):
        buckets.append(0)
        bucketMin = bucketBounds[bucketIt]
        bucketMax = distMax if bucketIt >= len(bucketBounds)-1 else bucketBounds[bucketIt + 1]

        # Advance past samples below the current range.
        while samples[sampleIt] < bucketMin and sampleIt < len(samples):
            sampleIt += 1

        # Since the samples should already be sorted, we only need to consider
        # these in order.
        while samples[sampleIt] < bucketMax:
            buckets[bucketIt] += 1
            sampleIt += 1

    return buckets

# Helper function for generating a sorted list of samples from a Gaussian distribution.
def getGaussianSamples(mu, sigma, sampleCount):
    samples = np.random.normal(mu, sigma, sampleCount)
    samples.sort()
    return samples

# Graph a distribution using matplotlib.
#
# @param samples Samples from the distribution.
# @param binCount Number of bins for the histogram.
# @param mu Mean of the distribution. If None, will be determined automatically
#           from the mean of samples.
# @param sigma Standard deviation of the distribution. If None, will be
#           determined automatically from the standard deviation of samples.
# @param normed Whether or not to normalize the output.
def graphGaussianDistribution(samples, binCount, mu=None, sigma=None, normed=True):
    if not mu:
        mu = statistics.mean(samples)
    if not sigma:
        sigma = statistics.stdev(samples)

    count, bins, ignored = plt.hist(samples, binCount, normed=normed)
    gaussianPDF = (lambda mu, sigma: 1/(sigma * np.sqrt(2 * np.pi)) *
        np.exp( - (bins - mu)**2 / (2 * sigma**2) ) )
    plt.plot(bins, gaussianPDF(mu, sigma), linewidth=2, color='r')
    plt.draw()

# Graph the skews distribution histrogram using matplotlib.
#
# @param skews Skews distribution.
# @param sampleScale Amount by which to scale skews values.
# @param lineFunc Function of the secondary line to draw.
# @param normed Whether or not to normalize the output.
def graphGaussianSkews(skews, sampleScale, lineFunc=None, normed=True):
    samples = []
    for i in range(len(skews)):
        for j in range(int(skews[i] * sampleScale)):
            samples.append(i)
    graphGaussianDistribution(samples, len(skews))

# Use Monte Carlo method to determine the ranges for the hotspots by generating
# 2 * sampleCount samples in the Gaussian distribution f(X | mu, sigma^2) and
# counting the samples that sit above the mean.
#
# @param mean Mean average value we want for samples in the normal distribution.
# @param dev Standard deviation for the normal distribution.
# @param halfCount One-half the number of samples to generate. This number
#                  will be doubled so that 2 * halfCount samples are generated.
# @param hSCount Number of hotspots to generate.
# @param capacity Percentage of total capacity to split among all hotspots.
# @param stdDevs Maximum distance from the mean we want to use in calculating
#        our hotspot buckets. If None, the maximum distance will be calculated
#        programatically by splitting the range between the smallest and
#        largest samples.
#            - Set to 3.0 by default since for a random variable with a
#              standard normal distribution, 99.7% of samples fall within
#              3 standard deviations of the mean, via the 68-95-99.7 rule.
def getGaussianHotspotRanges(mu, sigma, halfCount, hsCount, capacity, stdDevs=3.0):  
    # Calculate sizes via uniform-random sampling.
    sizes = [random.random() for i in range(hsCount)]
    random.shuffle(sizes)
    partSum = sum(sizes)
    for i in range(len(sizes)):
        sizes[i] = capacity * (sizes[i] / partSum)

    # Calculate positions from a Gaussian distribution. In order to skew
    # the positions near the beginning of the disk, we generate double the
    # number of input samples and only count those that are above the mean.
    sampleCount = 2 * halfCount

    # Generate many samples sorted by natural ordering.
    samples = getGaussianSamples(mu, sigma, sampleCount)

    # Calculate bucket boundaries. Only consider samples that are above the
    # mean.
    distMin = min(filter(lambda s: s >= mu, samples))
    if stdDevs == None or stdDevs <= 0.0:
        distMax = max(samples)
    else:
        distMax = mu + (stdDevs * sigma)

    buckets = getBucketCounts(samples, distMin, distMax, hsCount)
    random.shuffle(buckets)

    # Determine start positions.
    bucketSum = sum(buckets)
    positions = [100 *(b / bucketSum) for b in buckets]

    # Sanity check to make sure we generated the same number of sizes and
    # positions.
    assert len(sizes) == len(positions), "Generated an unequal number of sizes and positions."
    
    # Make hotspots.
    hotspots = []
    hsSum = 0
    for i in range(len(sizes)):
        hsSize = sizes[i] if hsSum + sizes[i] <= capacity else capacity - hsSum
        hsStart = positions[i]
        # Check for overlap. If there is, we just push the hotspot forward to
        # make them adjacent.
        if i > 0 and hsStart < hotspots[i-1][1]:
            hsStart = hotspots[i-1][1]
        hsEnd = hsStart + hsSize
        # Check to make sure hsEnd isn't out of bounds.
        if hsEnd > 100:
            hsEnd = 100
        hotspots.append((hsStart, hsEnd))
        hsSum += hsEnd - hsStart
        if hsEnd == 100:
            break

    return hotspots

# Create hotspot distribution -- ranges for each hotspot such that the sum
# of their sizes eq
def makeHotspots(args, config):
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
        sigma = config["distribution"][0]
        hotspots = getGaussianHotspotRanges(0, sigma, args.sample_count, hsCount, hsSpace)

    return hotspots

# Make workload definitions.
def makeWDs(args, config):
    wdList = []
    wdCount = config["wdcount"]
    hsCount = config["hotspotnum"]
    skews = makeSkews(args, config)
    hotspots = makeHotspots(args, config)
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
        lines = makeWDs(args, config)
        outFile.writelines(lines)

        # RDs
        lines = makeRDs(config)
        outFile.writelines(lines)

# Main.
def main():
    args = getArgs()

    if args.verbose:
        print("Verbose logging enabled.\n")

    try:
        config = parseInput(args.inPath, major_del=args.major_delimiter,
            minor_del=args.minor_delimiter, verbose=args.verbose)
    except IOError as e:
        raise e

    try:
        buildOutput(args, config, verbose=args.verbose)
    except IOError as e:
        raise e

    if args.graph:
        plt.show()

if __name__ == "__main__":
    main()