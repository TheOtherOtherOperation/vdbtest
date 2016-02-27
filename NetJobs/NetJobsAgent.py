#!/usr/bin/env python3

# ############################################################################ #
# NetJobsAgent - agent server for the NetJobs job synchronizer.                #
#                                                                              #
# Copyright (c) 2015 DeepStorage, LLC (deepstorage.net)                        # 
#     and Ramon A. Lovato (ramonalovato.com).                                  #
#                                                                              #
# See the file LICENSE for copying permission.                                 #
#                                                                              #
# Author: Ramon A. Lovato (ramonalovato.com)                                   #
# For: Deepstorage, LLC (deepstorage.net)                                      #
# Version: 2.2                                                                 #
#                                                                              #
# Usage: NetJobsAgent.py                                                       #
#                                                                              #
# Example: $ NetJobsAgent.py                                                   #
# ############################################################################ #

import socket
import select
import subprocess
import signal
import threading
import os
import time

from subprocess import PIPE

# Must match the scheduler constants of the same names, for obvious reasons.
AGENT_LISTEN_PORT = 16192
BUFFER_SIZE = 4096
SELECT_TIMEOUT = 1
SOCKET_TIMEOUT = 60
TIMEOUT_NONE = 0
SOCKET_DELIMITER = '\t'
CONNECTION_CLOSE_DELAY = 3
READY_STRING = '// READY //'
START_STRING = '// START //'
KILL_STRING = '// KILL //'
DONE_STRING = '// DONE //'
PING_STATUS_STRING = '// STATUS //'
PING_OK_STRING = 'OK'
SUCCESS_STATUS = 'SUCCESS'
ERROR_STATUS = 'ERROR'
TIMEOUT_STATUS = 'TIMEOUT'
KILLED_STATUS = 'KILLED'

# Used to track the number of active subprocesses.
processcount = 0

#
# Get run specifications from remote process.
#
# Params:
#     conn Socket connection to remote process.
#
# Return:
#     List of command strings.
#     List of timeouts.
#
def get_specs(conn):
    global name
    global ready
    global sosTimeout

    sosTimeout = TIMEOUT_NONE

    commands = []
    timeouts = []

    receiveBuffer = ''

    while not ready:
        try:
            # Since the client waits for each setup string to be echoed before
            # sending the next one, we don't need to lexify the string on newlines
            # the way we do later when listening to the socket asynchronously.
            receiveBuffer = conn.recv(BUFFER_SIZE)
            conn.sendall(receiveBuffer) # Echo test.
            receiveString = receiveBuffer.decode('UTF-8').replace('\n', '')
        except Exception as e:
            print("ERROR: an exception occurred while trying to receive specs: %s" % str(e))
            break

        print('\tReceived: "%s".' % receiveString)

        if receiveString == READY_STRING:
            ready = True
            print('\t\t--> Ready string received. Awaiting start message.')
        else:
            tokens = receiveString.replace('\n', '').split(SOCKET_DELIMITER)
            if len(tokens) < 2:
                print('\t\t--> WARNING: invalid message received -- insufficient number of tokens.')
                break
            elif tokens[0] == 'name':
                name = tokens[1]
                print('\t\t--> Registering name: %s.' % tokens[1])
            elif tokens[0] == 'command':
                command = tokens[1]
                commands.append(command)
                print('\t\t--> Registering command: "%s".' % command)
            elif tokens[0] == 'timeout':
                try:
                    timeout = int(tokens[1])
                    if timeout == TIMEOUT_NONE:
                        timeouts.append(None)
                        print('\t\t--> Registering timeout: None.')
                    else:
                        timeouts.append(timeout)
                        print('\t\t--> Registering timeout: %d second(s).' % timeout)
                        # Check if sosTimeout needs to be updated.
                        if not sosTimeout == TIMEOUT_NONE and timeout > sosTimeout:
                            sosTimeout = timeout
                except ValueError as e:
                    print('ERROR: invalid timeout.')
                    break
            else:
                print('\t\t--> WARNING: unknown message received. Breaking.')
                break

    print() # Blank line.

    return commands, timeouts

#
# Execute the main run.
#
# Params:
#     sock Socket on which we're with communicating client.
#     commands List of commands to execute.
#     timeouts List of timeouts for each command.
#
# Returns:
#     List of subprocess threads.
#
def start_run(sock, commands, timeouts):
    global subthreads
    global processcount

    results = []
    output = []
    # The lists should be the same length, but do a sanity check, just in case.
    processcount = min(len(commands), len(timeouts))

    print('\n---RESULTS---\n')

    for i in range(0, processcount):
        command = commands[i]
        timeout = timeouts[i]

        try:
            proc = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception as e:
            print('\nERROR: an exception occurred while trying to spawn the subprocess thread for "%s": %s\n'\
                  % (command, str(e)))
        thread = ProcThread(sock, command, timeout, proc)
        subthreads.append(thread)
        thread.start()

#
# Main.
#
def main():
    "main function"

    global name
    global ready
    global results
    global subthreads

    try:
        listenSock = socket.socket()
        listenPort = AGENT_LISTEN_PORT
        listenSock.bind(('', listenPort))
        listenSock.listen(1) # Only allow single connection.
    except OSError as e:
        exit('CRITICAL ERROR: NetJobsAgent failed to initialize: %s.' % str(e))

    while True:
        print('// NetJobsAgent: listening for scheduler connection on port %d.' \
              % listenPort)
        print('//     Process blocks indefinitely. Exit with ctrl-C/ctrl-break.\n')
        name = ''
        subthreads = []
        results = {}
        ready = False

        # Establish connection with client.
        try:
            sock, addr = listenSock.accept()
        except Exception as e:
            print("ERROR: socket accept failed: %s" % str(e))
            continue
     
        print('Got connection from %s. Communicating on port %s.\n' \
              % (addr, listenPort))

        # Set the socket timeout.
        sock.settimeout(SOCKET_TIMEOUT)

        # Get the run specifications.
        commands, timeouts = get_specs(sock)

        # Spawn the SOSThread.
        sosThread = SOSThread(sock, sosTimeout, commands, timeouts)

        # Listen for go command.
        sosThread.start()

        # Block until sosThread has finished starting.
        while not sosThread.started:
            time.sleep(0) # Yield.

        # Block until all subprocesses complete.
        for t in subthreads:
            t.join()

        # Stop SOSThread
        sosThread.stop()
        sosThread.join()

        # Close the connection.
        try:
            # Wait for any remaining processes.
            if processcount > 0:
                while processcount > 0:
                    time.sleep(0) # Yield.
            # Notify client to stop listener thread for this agent.
            print('\nActive processes: %d. Notifying client.\n' % (processcount))
            sock.sendall(bytes(DONE_STRING + '\n', 'UTF-8'))
            for i in range(CONNECTION_CLOSE_DELAY):
                print('Closing connection in %d...' % (CONNECTION_CLOSE_DELAY-i))
                time.sleep(1)
            sock.close()
        except Exception as e:
            print(str(e))
            pass
        print('\nConnection closed. Returning to wait mode.\n')


# ############################################################################ #
# SOSThread class for listening for client kill command while running.         #
# ############################################################################ #
class SOSThread(threading.Thread):
    "listens for kill command from client"

    def __init__(self, sock, timeout, commandsList, timeoutsList):
        threading.Thread.__init__(self)
        self.running = False
        self.sock = sock
        self.timeout = timeout
        self.commandsList = commandsList
        self.timeoutsList = timeoutsList
        self.started = False

    def run(self):
        self.running = True
        startTime = time.time()
        try:
            while self.running:
                elapsedTime = time.time() - startTime
                if not self.timeout == TIMEOUT_NONE and elapsedTime >= self.timeout:
                    self.timeout_handler()
                    break

                ready = select.select([self.sock], [], [], SELECT_TIMEOUT)
                
                if ready[0]:
                    buffer = self.sock.recv(BUFFER_SIZE)
                
                    if buffer:
                        commands = buffer.decode('UTF-8').split('\n')
                        commands = filter(None, commands)
                        for command in commands:
                            if command == START_STRING:
                                print('Start command received. Beginning run...')
                                start_run(self.sock, self.commandsList, self.timeoutsList)
                                self.started = True
                            elif command == KILL_STRING:
                                print('Run killed by remote client.')
                                self.stop_and_kill_run()
                            elif command == PING_STATUS_STRING:
                                print('Status ping received.')
                                self.sock.sendall(bytes(PING_OK_STRING + '\n', 'UTF-8'))
                            else:
                                print('Unknown command received from client:' % command)
        except:
            self.timeout_handler()

    def timeout_handler(self):
        if self.running:
            self.running = False
            print('ERROR: a global timeout occurred for this agent.')
            try:
                # Kill all subprocess threads.
                for thread in subthreads:
                    thread.stop_and_kill_subproc(TIMEOUT_STATUS + SOCKET_DELIMITER)
            except:
                pass

    def stop_and_kill_run(self):
        if self.running:
            self.running = False
            print('Agent killed by remote host.')
            try:
                # Kill all subprocess threads.
                for thread in subthreads:
                    thread.stop_and_kill_subproc(KILLED_STATUS + SOCKET_DELIMITER)
            except:
                pass

    def stop(self):
        self.running = False


# ############################################################################ #
# ProcThread class for listening for subprocess completion.                    #
# ############################################################################ #
class ProcThread(threading.Thread):
    "listens for subprocess completion"

    def __init__(self, sock, command, timeout, proc):
        threading.Thread.__init__(self)
        self.running = False
        self.sock = sock
        self.command = command
        self.timeout = timeout
        self.proc = proc
        self.result = 'NONE'

    def run(self):
        global processcount

        self.running = True
        startTime = time.time()
        try:
            while self.running and self.proc.poll() is None: # Checks returncode attribute.
                print(self.proc.stdout.readline().decode('UTF-8'), end='')
                elapsedTime = time.time() - startTime
                # If timeout exceeded and subprocess is still running. Short-circuits
                # if self.timeout is None.
                if not self.timeout == None and elapsedTime >= self.timeout:
                    self.stop_and_kill_subproc(TIMEOUT_STATUS + SOCKET_DELIMITER)
                # Yield context.
                time.sleep(0)
        except Exception as e:
            print('ERROR: during subprocess execution: %s.' % str(e))
            self.stop_and_kill_subproc(ERROR_STATUS + SOCKET_DELIMITER + str(e))

        self.send_result()
        processcount -= 1

    def send_result(self):
        global results
        
        if self.result == 'NONE':
            output, errors = self.proc.communicate()
            if self.proc.returncode > 0 or errors:
                self.result = (name + SOCKET_DELIMITER + self.command + SOCKET_DELIMITER
                    + ERROR_STATUS + SOCKET_DELIMITER + errors.decode('UTF-8'))
            else:
                self.result = (name + SOCKET_DELIMITER + self.command + SOCKET_DELIMITER
                    + SUCCESS_STATUS + SOCKET_DELIMITER + output.decode('UTF-8'))

        print('* ' + self.result)

        # Store for logging.
        results[self.command] = self.result

        # Check to make sure we're not overrunning the socket buffer.
        if len(self.result) > BUFFER_SIZE:
            self.result = self.result[:BUFFER_SIZE-2]
        # Add the terminating newline.
        if not self.result[:-1] == '\n':
            self.result = self.result + '\n'

        try:
            self.sock.sendall(bytes(self.result, 'UTF-8'))
        except Exception as e:
            print('NOTICE: an exception was caught during transmission of results: %s.'
                % str(e))

    def stop_and_kill_subproc(self, reason):
        if self.running:
            self.running = False
            print('\tCommand "%s" killed.' % self.command)
            try:
                # Kill the subprocess.
                self.proc.terminate()
            except:
                pass

            self.result = (name + SOCKET_DELIMITER + self.command + SOCKET_DELIMITER
                + reason)


# ############################################################################ #
# Execute main.                                                                #
# ############################################################################ #
if __name__ == "__main__":
    main()
