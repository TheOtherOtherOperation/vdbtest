# Instructions for setting up CentOS VMs for Vdbench and VDBTest

Create CentOS VMs according to the procedure for whichever hypervisor you're using. As of this writing, the preferred version/disk image to use is the CentOS 7 x86_64 "everything" ISO. Make sure to include the Gnome desktop environment and development tools packages (needed to build Python 3).

For the rest of this document, we assume the NFS server's IP address is 172.17.1.234 and the CIDR address for the subnet is 172.17.0.0/16.

## Initial steps

If not already logged in as root, open a terminal and enter persistent super-user mode:
    sudo su

To save us from having to write UDEV rules for the storage devices, we want to always be root on the VMs. Open the file /etc/gdm/custom.conf in a text editor and, under the [daemon] header, add the following:
    AutomaticLoginEnable=true
    AutomaticLogin=root

Disable and stop the system firewall:
    systemctl disable firewalld
    systemctl stop firewalld

Reboot the VM. It should automatically boot to the root user's desktop.

We want to set up a few optional things for convenience. First, we want to create a symbolic link to the terminal on the root user's Desktop:
    ln -s /usr/bin/gnome-terminal /root/Desktop/Terminal

While we're here, we can disable the root user password so we're not pestered for it on the lock screen:
    passwd -d root

Finally, I like to create a keybind, Ctrl-Alt-T, to access the terminal, which will be familiar to users of Ubuntu. Click on the Applications menu in the menubar and select System Tools --> Settings. Click on Keyboard, then switch to the Shortcuts tab. Click the plus (+) button and enter the following:
    Name: Terminal
    Command: gnome-terminal
    
Once that's done, find the shortcut in the list and click on the "Disabled" label. Press the desired key command (Ctrl-Alt-T), and the "Disabled" label should be replaced by the command.

## Installing prerequisites

Make sure the system is up-to-date:
    yum update && yum upgrade -y

Install the NFS utilities package:
    yum install nfs-utils -y

If you forgot to select the development tools package in the installer, install it now:
    yum groupinstall 'Development Tools' -y

Download, build, and install Python 3.5.0 (or newer):
    wget https://www.python.org/ftp/python/3.5.0/Python-3.5.0.tgz
    tar xf Python-3.*
    cd Python-3.*
    ./configure
    make
    make install

This will place the python3 executable and associated links in /usr/local/bin, which is not in the system path. Since we're editing the PATH anyway, we'll also set it up for Vdbench later. Open /etc/bashrc in a text editor and add the following line at the end:
    export PATH=$PATH:/usr/local/bin:/vdbench

Reload the file:
    source /etc/bashrc

Create the directory for the NFS share:
    mkdir -p /nfsshare

For convenience, create a Desktop shortcut to the NFS directory:
    ln -s /nfsshare /root/Desktop/
    
## Installing the tools

Download Vdbench from Oracle's website or SourceForge and put it somewhere accessible. For example:
    mv vdbench50403 /vdbench

We can install NetJobsAgent anywhere, but it's easiest just to put it in the Vdbench folder:
    mv NetJobsAgent.py /vdbench

Switch to the Vdbench directory and make Vdbench and NetJobsAgent executable:
    cd /vdbench
    chmod +x vdbench
    chmod +x NetJobsAgent.py

If you didn't do it earlier, edit the system path to include /usr/local/bin (for Python 3) and /vdbench (for Vdbench and NetJobsAgent.py). Add the following line to the end of the /etc/bashrc file:
    export PATH=$PATH:/usr/local/bin:/vdbench

Reload the file:
    source /etc/bashrc

### The NFS server

Start the NFS server and rpcbind:
    systemctl start rpcbind nfs-server
    systemctl enable rpcbind nfs-server
    systemctl start nfs-server
    systemctl enable nfs-server

Set the NFS directory access rights:
    chmod 777 /nfsshare

Using a text editor, open the file /etc/exports and add the following line, where 172.17.0.0/16 is the subnet's CIDR address:
    /nfsshare    172.17.0.0/16(rw,sync,no_root_squash,no_all_squash)

Update the export table:
    exportfs -a

### The NFS client

Verify the NFS share exists and is accessible, where 172.17.1.234 is the IP address of the NFS server:
    showmount -e 172.17.1.234

Mount the remote share to the NFS directory:
    mount 172.17.1.234:/nfsshare /nfsshare

Since we want the NFS share to be mounted automatically on reboot, open the file /etc/fstab in a text editor and add the following line:
    172.17.1.234:/nfsshare /nfsshare nfs    rw,hard,intr    0 0

## Cloning
Clone the NFS client VM as many times as you want. The VMs can be identical except that each must provide a unique identifier to JetTest, such as vdb1, vdb2, etc. (see the JetTest README for full details).

## Setting up for VDBTest

Create the template for your test script (e.g. vdbtest.sh), and place it somewhere accessible. If using the NFS server as a test machine, it will also need a test script. When using VDBTest, the test script must have the same name and path on each target machine, but each machine must provide a unique identifier.

A typical test script might look like this:

```
#!/bin/bash
#
# Directions:
#
# Fill in the right values for NAME, SHARE, and LUN.
#
# Make sure SHARE has the following directory structure:
# SHARE
# -- config # Contains VDbench config files named after NAME.
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
```

Here, the unique identifier for the machine is entered as the NAME variable. Both the -f (input) and -o (output) paths then end with a dereferenced NAME variable. This is consistent with the VDBTest requirement that the input and output paths end with the same basename. See the VDBTest README for more details.

Create the necessary folders on the NFS share:
    mkdir /nfsshare/config /nfsshare/output /nfsshare/work

Place the config files --- e.g. vdb1, vdb2, ..., vdbN --- in /nfsshare/config. Make sure the test script on each VM has the right identifier.

Remove any extraneous files, old Vdbench output directories, etc. from the test tree.

Start NetJobsAgent.py on each client.

Follow the instructions in the VDBTest README.

## Setting up for Vdbench's built-in multi-host processing

On each VM, run the following command:
    vdbench rsh

Follow the instructions in the Vdbench documentation.

## Note on running Vdbench

Vdbench requires an input and output path or the output won't be saved:
    vdbench -f "path/to/input" -o "path/to/output"
    
## Optional: setting network aliases

The Linux VMs can be configured to use a restricted network. The recommended DeepStorage configuration is to assign aliased IP addresses in the following subnets: 192.168.236.0/24 and 192.168.237.0/24. We utilize the 192.168.237.0/24 subnet for internal VM-to-VM test traffic and NFS *only* and should probably not be routable from the rest of your network. The 192.168.236.0/24 subnet can be opened to the outside if desired, but unless you do so, making these changes will prevent the VMs from connecting to the internet, so do this step only after downloading everything else you need.

In CentOS 7, network configurations are handled by NetworkManager. The easiest way to update the network settings is to utilize the NetworkManager TUI:
    nmtui
    
This will bring up a graphical interface from which the interfaces can be configured. Go to "Edit a connection", select the appropriate Ethernet interface, and choose "<Edit...>". Set the IPv4 configuration to "<Manual>", and then add the IP addresses 192.168.236.1/24 and 192.168.237.1/24. These will be the IP addresses for the NFS server. You will need to change the final byte when configuring the client(s). Leave the Gateway field blank and delete the DNS servers.

If deploying the VM from a template, rather than building from scratch, the hypervisor will most likely change the MAC address of the network interface. This will most likely break the connection to the 192.168.236.0/24 and 192.168.237.0/24 subnets. To prevent this from happening, we need to remove all device-specific identifying information from the network configuration.

Open the network-scripts folder and display the desired configuration files:
    cd /etc/sysconfig/network-scripts/
    ls ifcfg-*
    
This should display one or more ifcfg files whose names will vary based on the system. They will probably be either of the form ifcfg-ethN or ifcfg-Wired connection N, where N is an integer. There may also be others, such as ifcfg-lo, which is most likely a local loopback (127.0.0.1). You can use ifconfig to determine which configuration is assigned to each IP address.

Use a text editor to open the ifcfg- file for the interface you want to update (probably ifcfg-eth0 or ifcfg-Wired connection 1) and delete the lines for HWADDR and UUID.

Save the changes and restart the VM.

Note that your NFS settings will need to be configured properly. The server will need to be exporting "/nfsshare 192.168.237.0/24", and the clients will need to be mounting "192.168.237.1:/nfsshare /nfsshare nfs    rw,hard,intr    0 0" in /etc/fstab