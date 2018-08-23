#! /usr/bin/python

__author__ = 'wpanderson'

"""
CGI script which takes a 'directory_name', 'file_name', and 'contents' as input, then creates project directories and 
files within those directories which contain system bios settings. Useful as a template for writing an appache CGI file.

For error output see /var/log/httpd/error_log
"""

import cgi
import os
# Allow traceback logging in the /root/apache_logs/ directory. Supress displaying these in the browser.
import cgitb; cgitb.enable(display=0, logdir="/root/apache_logs")

# Grab each field from a post request and store into variables. 'getfirst()' is just a shorthand instead of using bracket notation.
form = cgi.FieldStorage()
directory = form.getfirst('directory_name')
file_name = form.getfirst('file_name')
content = form.getfirst('contents')

if directory and file_name and content:
    try:
        with open('SUM_BIOS_configs/{0}/{1}'.format(directory, file_name), 'wb') as fh:
            fh.write(content)
    except (OSError, IOError) as e:
        os.mkdir('SUM_BIOS_configs/{0}'.format(directory))
        with open('SUM_BIOS_configs/{0}/{1}'.format(directory, file_name), 'wb') as fh:
            fh.write(content)

else:
    # Print the HTML header so apache stops complaining that it's malformed
    print("Content-Type: text/plain\r\n")
    print("Unable to write to Jarvis. Missing necessary information.")
    # For further debug info in case something goes wrong.
    print("Directory: " + directory)
    print("File Name: " + file_name)
    print("Content length: " + str(len(content)))
