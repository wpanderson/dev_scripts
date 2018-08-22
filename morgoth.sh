#!/bin/bash

#Simple bash script created by Weston Anderson to zip up log files in a directory.
# Args:
#   -p Package log files found in directory.
#   -x Extract log files found in tar file.

if [[ $# -eq 0 ]]; then
    echo "No arguemnts were found. Please use -p to package logs, or -x to extract them."
    exit 1
fi

if [ ! -d logs/ ]; then
    echo "Creating logs/ directory"
    mkdir logs
fi

if [ "$1" == "-p" ]; then
    echo "Packing up logs."
    
    for file in *.log
    do
        cp ${file} logs
    done

    tar -czvf logs.tar.gz logs/
fi


if [ "$1" == "-x" ]; then
    tar -xzvf logs.tar.gz
fi


echo "Ready for Valrog parsing!"
