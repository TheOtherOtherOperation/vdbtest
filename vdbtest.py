#!/usr/bin/env python3

#
# vdbtest.py - Vdbench Test Script
#
# Author: Ramon A. Lovato (ramonalovato.com)
# For: DeepStorage, LLC (deepstorage.net)
#

import argparse
import os.path
import os
import re
import csv
from vdbconfig import vdbconfig
from NetJobs import NetJobs

DEFAULT_RUNS = 5
DEFAULT_TIMEOUT = 0
ARCHIVE_DIR_FORMAT = "__{content}_{testID}__"
ARCHIVE_DIR_REGEX = ARCHIVE_DIR_FORMAT.format(content="\w+", testID="\d+")
ID_SEP = "_##"
DEFAULT_SUCCESS_MULTIPLIER = 5.0
DEFAULT_FAILURE_MULTIPLIER = 0.3
DEFAULT_CONSECUTIVE_FAILURES = 2
DEFAULT_FUZZINESS = 0.0
DEFAULT_IOPS_TOLERANCE = 1.5
DEFAULT_BINARY_SEARCH_ITERATIONS = 5

# Simple data structure for storing test information. Note that run indexing
# goes from 1 to args.max_runs (for readability). Thus, run 0 data are
# initialized to None.
#
# Early builds had some problems with invisible files (such as Linux
# temp files: file.txt~) being added to TestInfo on initialization but
# not having any data associated with them since they weren't real
# run configurations. This solution isn't foolproof, but as a safeguard
# to prevent errors if there are problems, we now deliberately ignore
# lists whose length is shorter than the others.
class TestInfo:
    # Initializer.
    def __init__(self, configDir):
        self.names = [getNameOnly(f) for f in getContents(configDir)]
        self.requestedIOPS = {}
        self.achievedIOPS = {}
        self.latencies = {}

        for name in self.names:
            self.requestedIOPS[name] = [None]
            self.achievedIOPS[name] = [None]
            self.latencies[name] = [None]
        
        # self.state = 0: pre-test.
        # self.state = 1: post-test.
        self.state = 0
        self.runCount = 0
        self.ignoredNames = []
        self.allPassed = []
        self.totalRequested = []
        self.totalAchieved = []
        self.totalLatency = []
        self.averageLatency = []

    # Add requested IOPS to TestInfo.
    def updatePreTest(self, configDir):
        self.runCount += 1
        self.state = 0
        for config in getContents(configDir):
            name = getNameOnly(config)
            if not name in self.names:
                if name not in self.ignoredNames:
                    self.ignoredNames.append(name)
                    print("Warning: configuration file {} found for unregistered (new or blacklisted) target. This warning will only appear once per file.".format(
                        config))
                continue

            self.requestedIOPS[name].append(getOldIORate(config))

    # Add latency and achieved IOPS to TestInfo.
    def updatePostTest(self, outputParent):
        self.state = 1
        for folder in getContents(outputParent):
            name = os.path.basename(folder)
            if name not in self.names:
                if name not in self.ignoredNames:
                    self.ignoredNames.append(name)
                    print("Warning: output file {} found for unregistered (new or blacklisted) configuration. This warning will only appear once per file".format(
                        folder))
                continue

            try:
                results = getTestResults(folder)
            except Exception as e:
                self.blacklistTarget(name)
                print("Warning: unable to get test results for {}. Adding to blacklist. Original exception follows:\n{}".format(
                    name, str(e)))

            if name in self.names and not name in self.ignoredNames:
                self.achievedIOPS[name].append(float(results["rate"]))
                self.latencies[name].append(float(results["resp"]))
        
        # Check for targets without updated data and blacklist them.
        self.blacklistTest()

        totalRequestedIOPS = 0.0
        totalAchievedIOPS = 0.0
        totalLatency = 0.0
        for name in self.names:
            totalRequestedIOPS += self.requestedIOPS[name][-1]
            totalAchievedIOPS += self.achievedIOPS[name][-1]
            totalLatency += self.latencies[name][-1]
        averageLatency = totalLatency  / len(self.latencies.keys())
        self.totalRequested.append(totalRequestedIOPS)
        self.totalAchieved.append(totalAchievedIOPS)
        self.totalLatency.append(totalLatency)
        self.averageLatency.append(averageLatency)

    # Scan the data structure and blacklist any list whose length is shorter
    # than self.runCount + 1 (since the first element of each list is always
    # None), as this would mean its entries weren't updated properly.
    def blacklistTest(self):
        if not self.state == 1:
            raise Exception("TestInfo.blacklistTest is only valid in post-test (1) state.")

        # List index 0 is always None, since test indexing goes from 1 through
        # n, so the length is always 1 more than the run index.
        maxLength = self.runCount + 1
        testLam = lambda t: (len(self.requestedIOPS[t]) == maxLength
            and len(self.achievedIOPS[t]) == maxLength
            and len(self.latencies[t]) == maxLength)

        blacklist = [t for t in self.names if not testLam(t)]

        if len(blacklist) > 0:
            for name in blacklist:
                self.blacklistTarget(name)

            print("\nWarning: some targets did not have their data updated. "
                "This is usually due to a broken pipe, bad configuration, or "
                "erroneous files placed in the configuration directory. It "
                "can also happen if the Vdbench output directories have "
                "different base names than their configuration files. These "
                "targets will be blacklisted for the remainder of the run.")
            print("\nAffected targets:")
            for name in blacklist:
                print("    - {}".format(name))
            print()

        if len(self.names) == 0:
            raise Exception("Error: no targets remain after blacklisting. Unable to continue.")

    # Blacklist a specific target.
    def blacklistTarget(self, name):
        if name in self.names:
            self.names.remove(name)
            del(self.requestedIOPS[name])
            del(self.achievedIOPS[name])
            del(self.latencies[name])
            self.ignoredNames.append(name)

    # Append the specified result to the end of testPassed.
    def appendAllPassed(self, a):
        if not self.state == 1:
            raise Exception("TestInfo.appendAllPassed is only valid in post-test (1) state.")
        self.allPassed.append(a)

# LogWriter object for better encapsulating Python's file IO and CSV-handling.
# Tracks the CSV writer associated with the log file and auto-flushes rows.
#
# --- CSV table format ---
#
# run #    configuration    requested IOPS    achieved IOPS    latency (ms)
# 1        vdb1
#          vdb2
#          ...
#          total/average
# 2        vdb1
#          vdb2
#          ...
#          total/average
# ...      ...
class LogWriter:
    # Initializaer.
    def __init__(self, log):
        self.log = log
        self.logWriter = csv.writer(log, delimiter=',', quotechar='"',
            quoting=csv.QUOTE_MINIMAL)

    # Write the log header.
    def writeHeader(self):
        self.logWriter.writerow(["run #", "configuration", "requested IOPS",
            "achieved IOPS", "latency (ms)"])
        self.flushNow()

    # Update the log file.
    def updateLog(self, testInfo, run):
        row = LogWriter.updateLogHelper(testInfo.names[0], testInfo, run=run)
        self.logWriter.writerow(row)
        if len(testInfo.names) > 1:
            for name in testInfo.names[1:]:
                row = LogWriter.updateLogHelper(name, testInfo)
                self.logWriter.writerow(row)
        row = LogWriter.updateLogTotalsHelper(testInfo)
        self.logWriter.writerow(row)
        self.flushNow()

    # Helper for updateLog.
    def updateLogHelper(name, testInfo, run=None):
        row = ["{}".format(str(run) if run else ""),
               name,
               str(testInfo.requestedIOPS[name][-1]),
               str(testInfo.achievedIOPS[name][-1]),
               str(testInfo.latencies[name][-1])]
        return row

    def updateLogTotalsHelper(testInfo):
        # totalRequestedIOPS = 0.0
        # totalAchievedIOPS = 0.0
        # totalLatency = 0.0
        # for name in testInfo.names:
        #     totalRequestedIOPS += testInfo.requestedIOPS[name][-1]
        #     totalAchievedIOPS += testInfo.achievedIOPS[name][-1]
        #     totalLatency += testInfo.latencies[name][-1]
        # averageLatency = totalLatency  / len(testInfo.latencies.keys())
        row = ["",
               "total/average",
               str(testInfo.totalRequested),
               str(testInfo.totalAchieved),
               str(testInfo.averageLatency)]
        return row

    # Write log sign-off message on its own line, after a signel empty line.
    def logSignOff(self, message):
        self.logWriter.writerow([])
        self.logWriter.writerow([message])
        self.flushNow()

    # Force Python and the OS to immediately write the changes to disk.
    def flushNow(self):
        self.log.flush()
        os.fsync(self.log.fileno())

# Get CLI arguments.
def getArgs():
    parser = argparse.ArgumentParser(description="Run Vdbench tests to match IO response across multiple machines against target latency.")
    # Positional.
    parser.add_argument("configFile", type=str,
        help="path to the configuration file")
    parser.add_argument("configDir", type=str,
        help="directory containing Vdbench config files")
    parser.add_argument("outputParent", type=str,
        help="the parent directory of the directories containing output files")
    parser.add_argument("workFolder", type=str,
        help="path to the work folder for intermediate file storage")
    parser.add_argument("logPath", type=str,
        help="where to save the log file")
    parser.add_argument("targetLatency", type=float,
        help="target latency we're trying for (in ms)")
    
    # Optional.
    parser.add_argument("-m", "--max-runs", type=int, default=DEFAULT_RUNS,
        help="override maximum number of runs before aborting (default {})"
        .format(DEFAULT_RUNS))
    parser.add_argument("-t", "--timeout", type=int, default=DEFAULT_TIMEOUT,
        help="set a timeout in seconds for the scheduler (default {})"
        .format(DEFAULT_TIMEOUT))
    parser.add_argument("-s", "--success-multiplier", type=float,
        default=DEFAULT_SUCCESS_MULTIPLIER,
        help="override IO rate multiplier when target is below target latency (default {})"
        .format(DEFAULT_SUCCESS_MULTIPLIER))
    parser.add_argument("-f", "--failure-multiplier", type=float,
        default=DEFAULT_FAILURE_MULTIPLIER,
        help="override IO rate multiplier when target is above target latency (default {})"
        .format(DEFAULT_FAILURE_MULTIPLIER))
    parser.add_argument("-c", "--consecutive-failures", type=int,
        default=DEFAULT_CONSECUTIVE_FAILURES,
        help="terminate after this many consecutive failures (default {})"
        .format(DEFAULT_CONSECUTIVE_FAILURES))
    parser.add_argument("-z", "--fuzziness", type=float,
        default=DEFAULT_FUZZINESS,
        help="acceptable fractional skew from target latency, such that targetLatency * (1.0 - fuzziness) <= x <= targetLatency * (1.0 + fuzziness)  (default {})".format(
            DEFAULT_FUZZINESS))
    parser.add_argument("-i", "--iops-tolerance", type=float,
        default=DEFAULT_IOPS_TOLERANCE,
        help="if IOPS achieved * IOPS tolerance < IOPS requested, terminate early (default {})".format(
            DEFAULT_IOPS_TOLERANCE))
    parser.add_argument("-b", "--binary-search", action="store_true",
        help="enable binary search mode")
    parser.add_argument("-n", "--binary-search-iterations", type=int,
        default=DEFAULT_BINARY_SEARCH_ITERATIONS,
        help="maximum number of iterations to run binary search (default {}); does nothing if --binary-search is not specified".format(
            DEFAULT_BINARY_SEARCH_ITERATIONS))
    parser.add_argument("-v", "--verbose", action="store_true",
        help="enable verbose mode")

    args = parser.parse_args()

    args.configFile = os.path.realpath(args.configFile)
    args.configDir = os.path.realpath(args.configDir)
    args.outputParent = os.path.realpath(args.outputParent)
    args.workFolder = os.path.realpath(args.workFolder)

    # Verify directories exist.
    os.makedirs(args.configDir, exist_ok=True)
    os.makedirs(args.outputParent, exist_ok=True)
    os.makedirs(args.workFolder, exist_ok=True)

    if args.max_runs < 1:
        print("Warning: max_runs < 1. Using default ({}).".format(DEFAULT_RUNS))
        args.max_runs = DEFAULT_RUNS
    if 1.0 - args.fuzziness < 0:
        print("Warning: 1.0 - fuzziness < 0. Using default ({}).".format(
            DEFAULT_FUZZINESS))
        args.fuzziness = DEFAULT_FUZZINESS
    if args.iops_tolerance < 1.0:
        print("Warning: iops_tolerance < 1.0. Using default ({}).".format(
            DEFAULT_IOPS_TOLERANCE))
        args.iops_tolerance = DEFAULT_IOPS_TOLERANCE
    if args.binary_search == True and args.binary_search_iterations < 1:
        print("Warning: binary search iterations must be be a positive integer. Using default ({}).".format(
            DEFAULT_BINARY_SEARCH_ITERATIONS))
        args.binary_search_iterations = DEFAULT_BINARY_SEARCH_ITERATIONS

    return args

# Read vdbtest config file.
def readConfig(configFile):
    config = {
        "targets": [],
        "command": None,
    }

    try:
        with open(configFile, "r") as f:
            targetsReached = False

            # A simple state machine for parsing the config file.
            for realLine in f:
                line = realLine.strip()

                # Comment line or blank.
                if not line or line == "" or line.startswith("#"):
                    continue

                partials = re.split(":", line, maxsplit=1)
                key = partials[0].strip().lower()
                
                if not targetsReached:
                    if key == "targets":
                        targetsReached = True
                        continue
                    elif len(partials) < 2:
                        raise Exception(
                            "Error: configuration file {configFile} --- unrecognized line {line}.".format(
                                line=line, configFile=configFile))

                if targetsReached:
                    config["targets"].append(line)
                else:
                    value = partials[1].strip()

                    # Command string.
                    if key == "command":
                        config["command"] = value

                    # No idea.
                    else:
                        raise Exception(
                            "Error: configuration file {configFile} --- unrecognized line {line}.".format(
                                configFile=configFile, line=line))

    except Exception as e:
        raise e

    if len(config["targets"]) == 0:
        raise Exception(
            "Error: configuration file {} --- no targets specified.".format(
                configFile))
    if not config["command"]:
        raise Exception(
            "Error: configuration file {} --- no command specified.".format(
                configFile))

    return config

# Archive everything in the specified directory that isn't itself an archive
# directory.
def archiveContents(parentDir, testID):
    candidates = getContents(parentDir)
    for c in candidates:
        archiveFile(c, testID)

# Archive the specified file. Return the new archive path.
def archiveFile(oldPath, testID):
    parentDir = os.path.dirname(oldPath)
    content = os.path.split(parentDir)[-1]
    archDir = os.path.join(parentDir,
        ARCHIVE_DIR_FORMAT.format(content=content, testID=testID))
    if not os.path.isdir(archDir):
        os.makedirs(archDir)
    newPath = os.path.join(archDir, os.path.basename(oldPath))
    os.rename(oldPath, newPath)

    return newPath

# Gets a list of contents of the specified parent directory, excluding
# those that match the archive formatting. Also skips filenames that
# begin with a dot (".") or end with a tilde ("~") in order to
# filter out some issues with hidden and temp files under Linux.
def getContents(parentDir):
    names = filter(lambda d: not re.match(ARCHIVE_DIR_REGEX, d)
        and not d.startswith(".") and not d.endswith("~"),
        os.listdir(parentDir))
    return [os.path.join(parentDir, p) for p in names]

# Reads test results from totals.html in the specified directory.
def getTestResults(parentDir):
    try:
        flatFile = findFlatFile(parentDir)
    except Exception as e:
        raise e
        
    try:
        with open(flatFile, "r") as f:
            # Line for results is the last in the file, but first we need to locate the keys.
            lines = f.readlines()
            
            # Keys are the first non-comment ("*") and non-HTML tag ("<") line in file.
            keyIt = 0
            while lines[keyIt].startswith("*") or lines[keyIt].startswith("<") or not lines[keyIt].strip():
                keyIt += 1
                if keyIt >= len(lines):
                    raise Exception("Unable to locate result keys. File {} is invalid.".format(
                        flatFile))
                continue
            keys = re.split("\s+", lines[keyIt].strip())
            values = re.split("\s+", lines[-1].strip())
            results = dict(zip(keys, values))
            return results
    except Exception as e:
        raise e

# Find absolute path to flatfile.html file in specified directory.
def findFlatFile(parentDir):
    for f in os.listdir(parentDir):
        if os.path.basename(f) == "flatfile.html":
            return os.path.join(parentDir, f)
    # Didn't find.
    raise Exception(
        "Error: directory {} does not contain the file flatfile.html.".format(
            parentDir))

# Get all test results from the directories within the output directory.
def getAllTestResults(outputDir):
    allResults = {}
    for f in getContents(outputDir):
        allResults[os.path.basename(f)] = getTestResults(f)
    return allResults

# Given a results dictionary from getAllTestResults and the target latency,
# returns true if ALL test results were below the target latency, else false.
def compareResultLatencies(allResults, targetLatency, fuzziness):
    maybeDone = True
    minLat = targetLatency * (1.0 - fuzziness)
    maxLat = targetLatency * (1.0 + fuzziness)
    for r in allResults.values():
        try:
            responseTime = float(r["resp"])
        except ValueError as e:
            raise e

        if fuzziness == 0.0 and responseTime > targetLatency:
            return False, False
        elif responseTime < minLat or responseTime > maxLat:
            maybeDone = False

    return True, maybeDone

# Make a new Vdbench configuration file.
def makeNewVDBConfig(oldConfig, newConfig, newIORate):
    try:
        vdbconfig.makeNewConfig(oldConfig, newConfig, newIORate)
    except IOError as e:
        raise e

# Helper for makeNewVDBConfig that tries to remove the test ID from a config
# file name.
def stripIDFromFile(filename):
    partials = re.split(ID_SEP, os.path.splitext(os.path.basename(filename))[0])
    return partials[-2] if len(partials) > 1 else partials[-1]

# Helper for makeAllNewConfigs that extracts just the test ID from an existing
# config file.
def getTestIDFromConfig(filename):
    partials = re.split(ID_SEP, os.path.splitext(os.path.basename(filename))[0])
    return int(partials[-1]) if len(partials) > 1 else 0

# Make new configuration file for NetJobs.
def makeNetJobsConfig(workFolder, timeout, targets, command, configFile):
    identifier = os.path.splitext(os.path.basename(configFile))[0]
    fileID = 0

    nj_path = os.path.join(workFolder,
        "vdbtest_{identifier}.netjobsconfig".format(identifier=identifier))

    while os.path.exists(nj_path):
        fileID += 1
        nj_path = os.path.join(workFolder,
        "vdbtest_{identifier} ({fileID}).netjobsconfig".format(
            identifier=identifier, fileID=fileID))

    try:
        with open(nj_path, "w") as f:
            # Test label, timeout/duration.
            f.write("{}:\n".format(identifier.replace(":", "_")))
            f.write("-generaltimeout: {timeout}s\n".format(timeout=timeout))
            # Target specs.
            for t in targets:
                f.write("{target}: {command}\n".format(
                    target=t, command=command))
            f.write("end")
    except Exception as e:
        raise e

    print("\nNetJobs config saved as: {}\n".format(nj_path))

    return nj_path

# Run NetJobs once.
def startNetJobs(njconfig, verbose=False):
    if verbose:
        njargs = ("-l", "-v", njconfig)
    else:
        njargs = ("-l", njconfig)

    try:
        NetJobs.main(njargs)
    except Exception as e:
        raise e

# Calculate the new IO rate based on the given config file and allPassed.
def calculateNewIORate(configFile, args, allPassed):
    rate = getOldIORate(configFile)
    rate *= args.success_multiplier if allPassed else args.failure_multiplier
    return int(round(rate))

# Get the old IO rate based on the given config file.
def getOldIORate(configFile):
    try:
        with open(configFile, "r") as inFile:
            for line in inFile:
                if not re.match(r"[\/\#\*].*", line):
                    tokens = [t.split("=") for t in line.split(",")]
                    for i in range(len(tokens)):
                        token = tokens[i]
                        if len(token) > 1:
                            key = token[0]
                            value = token[1]

                            if key == "iorate":
                                return int(float(value))
    except (IOError, ValueError) as e:
        raise e
    except (IsADirectoryError) as e:
        print("Warning: {} is a directory, not a file.".format(configFile))
    # If we got here, the config file doesn't contain an iorate, so there's
    # something wrong.
    raise Exception("Error: config file {} malformed --- no \"iorate\" specified.".format(
        configFile))

# Update all config files and archive the old ones.
def updateAndArchiveConfigs(args, allPassed, testID):
    for f in getContents(args.configDir):
        name = os.path.join(args.configDir, f)
        oldName = name
        oldFile = archiveFile(name, testID)
        newIORate = calculateNewIORate(oldFile, args, allPassed)
        makeNewVDBConfig(oldFile, oldName, newIORate)

# Update all config files for binary search and archive the old ones.
def updateAndArchiveConfigsBS(args, testInfo, testID, lower, upper):
    allPassed = testInfo.allPassed
    if allPassed[-1]:
        lower = max(lower, testInfo.totalRequested[-1])
    else:
        upper = min(upper, testInfo.totalRequested[-1])

    # They swapped places, so we've gotten as close as possible.
    if lower >= upper:
        return lower, upper

    newTotal = (lower + ((upper - lower) / 2))
    ratio = newTotal / testInfo.totalRequested[-1]

    for f in getContents(args.configDir):
        name = os.path.join(args.configDir, f)
        oldName = name
        oldFile = archiveFile(name, testID)

        oldIORate = getOldIORate(oldFile)
        newIORate = oldIORate * ratio
        makeNewVDBConfig(oldFile, oldName, newIORate)

    return lower, upper

# Test if the achieved IOPS is acceptable (achieved * tolerance >= requested).
def testAchievedIOPS(testInfo, tolerance):
    for name in testInfo.names:
        requestedIOPS = float(testInfo.requestedIOPS[name][-1])
        achievedIOPS = float(testInfo.achievedIOPS[name][-1])

        if achievedIOPS * tolerance < requestedIOPS:
            return False

    return True

# Helper method that extracts the base filename, without extension, from a path.
def getNameOnly(path):
    return os.path.splitext(os.path.basename(path))[0]

# Test if binary search should start.
def testBSStart(testInfo):
    allPassed = testInfo.allPassed
    if len(allPassed) < 2:
        return False
    else:
        return allPassed[-1] != allPassed[-2]

# Start the main run.
def run(args, config, njconfig, testInfo, logWriter):
    print("Starting main run...")

    consecutiveFailures = 0

    run = 0
    bsRun = 0
    bsStarted = False
    finished = False
    lower = 0
    upper = 0
    while not finished:
        run += 1
        if not args.binary_search or not bsStarted and run >= args.max_runs:
            finished = True
        if args.binary_search and bsStarted:
            bsRun += 1
            if bsRun >= args.binary_search_iterations:
                finished = True

        if not args.binary_search:
            print("\n--- Run {}/{} ---".format(run, args.max_runs))
        elif not bsStarted:
            print("\n--- Run {}/{} :: Waiting to Start Binary Search ---".format(run, args.max_runs))
        else:
            print("\n--- Run {} :: Binary Search Step {}/{} ---".format(run, bsRun, args.binary_search_iterations))

        testInfo.updatePreTest(args.configDir)

        if args.verbose:
            print("\n### Begin NetJobs Output ###")

        startNetJobs(njconfig, verbose=args.verbose)

        if args.verbose:
            print("\n### End NetJobs Output ###")

        testInfo.updatePostTest(args.outputParent)

        print("\nTotal IOPS achieved/requested: {:.2f}/{:d}".format(testInfo.totalAchieved[-1], int(testInfo.totalRequested[-1])))
        print("Average latency/allowed: {:.2f}/{:.2f}".format(testInfo.averageLatency[-1], args.targetLatency))

        logWriter.updateLog(testInfo, run)

        allResults = getAllTestResults(args.outputParent)
        allPassed, isDone = compareResultLatencies(allResults,
            args.targetLatency, args.fuzziness)
        sufficientIOPS = testAchievedIOPS(testInfo, args.iops_tolerance)

        testInfo.appendAllPassed(allPassed)

        if args.verbose:
            print("\nDid all targets achieve the target latency? {}.".format(
                "Yes" if allPassed else "No"))
            print("Did all targets achieve sufficient IOPS? {}.\n".format(
                "Yes" if sufficientIOPS else "No"))
            print("Archiving output and Vdbench configurations.\n")

        if allPassed:
            consecutiveFailures = 0
        elif not bsStarted:
            consecutiveFailures += 1
            if consecutiveFailures >= args.consecutive_failures:
                message = "Vdbench failed to achieve the target latency {}/{} consecutive time(s). Aborting run.".format(
                    consecutiveFailures, args.consecutive_failures)
                print("\n--- Notice: {}\n".format(message))
                logWriter.logSignOff(message)
                finished = True
            elif args.verbose:
                print("Number of consecutive failures: {}/{}.".format(
                    consecutiveFailures, args.consecutive_failures))

        if not sufficientIOPS:
            message = "Vdbench failed to achieve requested IOPS within tolerance of {}. Requested IO rate is too high or exceeds soft cap. Aborting run.".format(
                args.iops_tolerance)
            print("\n--- Notice: {}\n".format(message))
            logWriter.logSignOff(message)
            finished = True

        archiveContents(args.outputParent, run)

        if finished:
            archiveContents(args.configDir, run)
            print("Reached maximum number of runs.")
        else:
            if args.binary_search:
                if not bsStarted and testBSStart(testInfo):
                    bsStarted = True
                    totalRequested = testInfo.totalRequested
                    if totalRequested[-1] < totalRequested[-2]:
                        lower = totalRequested[-1]
                        upper = totalRequested[-2]
                    else:
                        lower = totalRequested[-2]
                        upper = totalRequested[-1]
                    lower, upper = updateAndArchiveConfigsBS(args, testInfo, run, lower, upper)
                elif bsStarted:
                    lower, upper = updateAndArchiveConfigsBS(args, testInfo, run, lower, upper)
                    if lower >= upper:
                        archiveContents(args.configDir, run)
                        print("Binary search converged to {} IOPS.".format(lower))
                        finished = True
                elif finished:
                    print("Reached maximum number of runs without starting binary search.")
                else:
                    updateAndArchiveConfigs(args, allPassed, run)
            else:
                updateAndArchiveConfigs(args, allPassed, run)

        # Finish if sweet spot found.
        if isDone:
            message = "Desired latency (targetLatency * (1.0 - fuzziness) <= x <= targetLatency * (1.0 + fuzziness) --> {min} <= x <= {max}) found. Run complete.".format(
            min=args.targetLatency * (1.0 - args.fuzziness),
            max=args.targetLatency * (1.0 + args.fuzziness))
            print("\n--- Notice: {}\n".format(message))
            logWriter.logSignOff(message)
            finished = True

    # Max runs reached.
    message = "Max runs ({}) reached. Run complete.".format(args.max_runs)
    print("\n--- Notice: {}\n".format(message))
    logWriter.logSignOff(message)

# Main.
def main():
    args = getArgs()

    if args.verbose:
        print("\n--- DeepStorage vdbtest ---")
        print("Verbose mode enabled.")
        print("> Configuration: {}".format(args.configFile))
        print("> Directory for Vdbench configurations: {}".format(
            args.configDir))
        print("> Output directory: {}".format(args.outputParent))
        print("> NetJobs work folder: {}".format(args.workFolder))
        print("> Log file: {}".format(args.logPath))
        print("> Target latency: {}ms".format(args.targetLatency))
        print("> Fuzziness: {}".format(args.fuzziness))
        print("> Maximum runs: {}".format(args.max_runs))
        print("> Success multiplier: {}".format(args.success_multiplier))
        print("> Failure multiplier: {}".format(args.failure_multiplier))
        print("> NetJobs timeout: {}s".format(args.timeout))
        print("> Aborting after {} consecutive failures".format(
            args.consecutive_failures))

    config = readConfig(args.configFile)

    if args.verbose:
        print("> Command: {}".format(config["command"]))
        print("> Target list: ")
        for t in config["targets"]:
            print("    {}".format(t))
        print()

    njconfig = makeNetJobsConfig(args.workFolder, args.timeout,
        config["targets"], config["command"], args.configFile)

    testInfo = TestInfo(args.configDir)

    try:
        with open(args.logPath, "w", newline="") as log:
            logWriter = LogWriter(log)
            logWriter.writeHeader()
            print("Log file saved as: {}\n".format(args.logPath))
            # Done with setup.
            run(args, config, njconfig, testInfo, logWriter)
    except IOError as e:
        raise e

if __name__ == "__main__":
    main()
