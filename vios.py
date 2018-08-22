#!/usr/bin/python
__author__ = 'Weston Anderson'
version = '1.1.1'

"""
Description:
Vios is a utility for configuring and setting bios settings on Supermicro and Intel baseboard systems. This is done by
utilizing the binary 'SUM' for Supermicro systems and the binary 'syscfg' for Intel systems. Vios will then call 
'syscheck' and other system gathering utilities to identify a system, after which vios will enter one of many features
to either update, configure, or compare system BIOS settings.
"""

import sys
import argparse
from json import loads
import subprocess
from enum import Enum
from simech_common import simech_common as sm
import os
import requests
import time
import re

# cElementTree and ElementTree differ in that cElementTree using C as a base so it's a bit faster.
try:
    import xml.etree.cElementTree as ET
except:
    import xml.etree.ElementTree as ET


# Binaries used by vios to gather bios settings
sum_binary = 'sum'
intel_binary = 'syscfg'

# Directories for storing saved bios files
bios_settings_dir = os.path.expanduser('~/bios_settings/')

# Links for gathering Golden Template data from Jarvis
jarvis_bios_settings = 'http://jarvis.wpanderson.com/production_automation/SUM_BIOS_configs/'

# Color codes for text formatting.
RED = '\033[31m'
GREEN = '\033[32m'
YELLOW = '\033[33m'
BOLD = '\033[1m'
END = '\033[0m'


class Baseboard(Enum):
    """
    A simple enum class for determining what the baseboard of a system is. At this time the important enums are:
        - INTEL: enum for intel baseboards. Indicates that syscfg must be used.
        - SUPERMICRO: enum for supermicro baseboards. Indicates taht sum must be used.
        - OTHER: enum for anything else. These boards are not supported by sum or syscfg.

    This allows for quick comparisons based on what type of baseboard the system is using.
    """
    INTEL = 'intel'
    SUPERMICRO = 'supermicro'
    OTHER = 'other'


class SystemInfo:
    """
    Class for storing system information gathered from the various utilities in automation.
    """

    def __init__(self):
        """
        Initialize important system variables for storing system information. The majority of these variables are used
        for stamping the Golden_Template when that is uploaded... Information is gathered as part of the:
        gather_system_info() function as program starts.

        :param p_number:     Project number associated with the system. (Used in file naming)
        :param sm_number:    Used as a serial number for the system
        :param customer:     Customer associated with the system. (Used in file naming)
        :param order:        Inidcates order number of project. Stamps to uploaded Golden Templates.
        :param date:         Creates a date stamp for used in file naming and stamping.
        :param baseboard:    Type of motherboard in the system. (Used to determine binaries to execute)
        :param binary:       Binary to be used to gather bios config files.
        :param model:        Model of the baseboard used in the system.
        :param ipmi_version: Version of IPMI used by the baseboard.
        :param m_serial:     Serial number of the motherboard of the system.
        :param bios:         Version of bios the system is using. Stamps to uploaded Golden Templates.
        :param binary:       Binary used by the system. This is either 'syscfg' or 'sum' based on baseboard.
        """
        # Trogdor Information
        self.p_number = ''
        self.sm_number = ''
        self.customer = ''
        self.order = ''
        self.date = time.strftime('%Y-%m-%d-%H-%M-%S')

        # Motherboard Information
        self.baseboard = None
        self.model = ''
        self.ipmi_version = ''
        self.m_serial = ''
        self.bios = ''
        self.binary = ''

    def validate_system(self):
        """
        *Only required on Supermicro systems*

        Validate the system to ensure that it is activated and able to view and configure bios settings. If vios is
        unable to validate a system it should not continue past this section. Vios should report this to the user
        and exit.

        called by:
            - gather_system_info()
        """
        try:
            output = subprocess.check_output(sum_binary + ' -c CheckOOBSupport', shell=True)
            if not re.search('Node Product Key Activated\.*OOB', output) \
                    and not re.search('Feature Toggled On\.*Yes', output):
                sm.error('System has not been activated, please activate the system before continuing.', output)
                exit()
        except subprocess.CalledProcessError or OSError as e:
            sm.error('Failed to check activation status. Error was:', str(e))
            exit()

    def to_string(self):
        """
        To string function to print formatted output for Trogdor and BIOS information. Displayed using the --display
        flag during program execution.
        """

        print(BOLD + ' Project Number: {0}\n SM Number:      {1}\n Customer:       {2}\n Order Number:   {3}\n'
                     ' ==========Baseboard Information==========\n'
                     ' Baseboard type: {4}\n Bios Version:   {5}\n Model Number:   {6}\n IPMI:           {7}\n'
                     ' Serial:         {8}\n'
                     ''.format(self.p_number, self.sm_number, self.customer, self.order, self.baseboard.name,
                        self.bios, self.model, self.ipmi_version, self.m_serial)) + END


class Bios:
    """
    A class for performing operations on a system. These operations are:
        - Comparing the current bios settings to golden template settings.
        - Applying latest/supplied golden template settings.
        - Uploading current bios settings as the Golden Template for this system.
    """

    def __init__(self, system_info):
        """
        :param system_info:         SystemInfo object for direct access to the system information variables.
        :param gt_file:             Name of the Golden Template for the system.
        :param current_bios_file:   Name of the current bios file for the system.
        """
        self.system_info = system_info
        self.gt_file = ''
        self.current_bios_file = ''

    def upload_gt(self):
        """
        Upload the current bios settings as a golden_template for the system. This means the current settings are
        completely correct and should be used as a template to set bios settings in the future. Ask the user if this
        is okay before beginning the upload process. This mostly follows the original upload process from sumthing.

        Steps:
            - Ask for comfirmation to continue.
            - Remove existing Golden_Template files from the bios_settings directory if any.
            - Using Trogdor info and current date and time create a Golden_Template file in memory.
            - Prefix file with trogdor information.
            - Upload file to jarvis.

        Called by:
            --auto
            --upload
        """
        response = raw_input(BOLD + 'Would you like to set the current bios settings as the Golden Template for this '
                                    'system? This means the current BIOS settings are 100% correct... Continue? (y/n):'
                                    '' + END)

        if 'y' not in response.lower():
            print('Exiting Vios configuration...')
            exit()

        # Remove all Golden Template files in the ~/bios_settings/ folder.
        try:
            gt_files = os.listdir(bios_settings_dir)
            for gt in gt_files:
                if re.search('golden_template', gt.lower()):
                    os.remove(os.path.join(bios_settings_dir, gt))
        except (IOError, OSError) as e:
            sm.error('Unable to remove previous Golden_Template files')

        if not self.system_info.p_number or not self.system_info.customer:
            sm.error('Not enough Trogdor information to generate a Golden Template... Missing project or customer info.')
            exit()

        gt_name = 'GOLDEN_TEMPLATE_{0}_{1}_{2}'.format(self.system_info.p_number, self.system_info.customer,
                                                       self.system_info.date)
        if self.system_info.baseboard == Baseboard.SUPERMICRO:
            gt_name = gt_name + '.bios'
            try:
                output = subprocess.check_output(sum_binary +' -c getcurrentbioscfg --file ' + bios_settings_dir
                                                 + gt_name, shell=True)
                self.gt_file = os.path.join(bios_settings_dir, gt_name)
            except subprocess.CalledProcessError or OSError as e:
                sm.error('Vios failed to generate the current BIOS settings for the Golden Template... Error was:',
                         str(output))
                exit()
        elif self.system_info.baseboard == Baseboard.INTEL:
            gt_name = gt_name + '.INI'
            try:
                output = subprocess.check_output('syscfg /s {0} /b'.format(bios_settings_dir + gt_name),
                                                 shell=True)
                if 'Successfully Completed' in output:
                    self.gt_file = os.path.join(bios_settings_dir, gt_name)
                else:
                    sm.error('Vios could not ')
            except (subprocess.CalledProcessError, IOError, OSError) as e:
                sm.error('Unable to get current bios settings for syscfg. Error was:', str(e))
                exit()

        # Determine the type of BIOS file generated, XML or Plain text, and write to the file Trogdor info.
        try:
            with open(self.gt_file, mode='r+') as fh:
                content = fh.read()
                cp = ''
                cs = ''

                if re.search('^#', content):
                    cp = '\n#'
                elif re.search('^<', content):
                    cp = '\n<!--'
                    cs = '-->'
                elif re.search('^;', content):
                    cp = '\n; '
                else:
                    sm.error('Unable to identify Golden Template as plain or XML type.')
                    exit()

                stamp = cp.strip('\n') + " " + self.system_info.date + cs
                stamp += cp + " File Name:  " + gt_name + cs
                stamp += cp + " Customer:  " + self.system_info.customer + cs
                stamp += cp + " Project:  " + self.system_info.p_number + cs
                stamp += cp + " Order Number:  " + self.system_info.order + cs
                stamp += cp + " Template generated on SM Number:  " + self.system_info.sm_number + cs
                stamp += cp + " Motherboard Model:  " + self.system_info.model + cs
                stamp += cp + " BIOS / IPMI:  " + self.system_info.bios + " / " + self.system_info.ipmi_version + cs
                stamp += cp + " Motherboard Serial:  " + self.system_info.m_serial + cs
                stamp += cp + " VIOS version " + version + cs + "\n"
                # If a Unicode Error is found while modifying the text, i.e. A Unicode character is found, normalize
                # the text and write that content to the file.
                try:
                    content = stamp + content
                except UnicodeDecodeError:
                    content = stamp.decode('latin-1') + content.decode('latin-1')
                fh.seek(0)
                try:
                    fh.write(content)
                except UnicodeEncodeError:
                    content = content.encode('latin-1')
                    fh.write(content)
        except (IOError, OSError) as e:
            sm.error('Unable to load and stamp {0}. Error Was:'.format(gt_name), str(e))
            exit()

        up_dict = {'directory_name': '{0}'.format(self.system_info.p_number + '_' + self.system_info.customer),
                   'file_name':gt_name, 'contents':content}

        jarvis_directory = 'http://jarvis.wpanderson.com/production_automation/SUM_BIOS_configs/{0}/{1}'.format(
            up_dict['directory_name'], up_dict['file_name'])

        try:
            r = requests.post('http://jarvis.wpanderson.com/production_automation/test_bios_settings_writer.py',
                              up_dict)
            print(GREEN + 'Success! {0} was uploaded to Jarvis as {1}.'.format(gt_name, jarvis_directory) + END)
        except requests.RequestException as e:
            sm.error('Vios failed to upload a Golden Template... Error was:', str(e))
            exit()

    def get_gt(self, gt_url=None):
        """
        Acquire the latest Golden_Template for a system and write it to memory.
        This is overridden if a gt_url is specified, witch downloads a specific GT from a URL that is supplied.
        If no data can be gathered get_gt will ask the user if they would like to upload the current settings as the
        Golden Template.

        Called by:
            --auto
            --compare
            --url

        Steps:
            - Check if gt_url is present.
                - Download from gt_url
                - Write GT to memory.
            - Determine the latest golden_template on Jarvis and download it.
                - Write it to memory
            - Continue
        """
        gt_data = None
        try:
            if gt_url:
                if self.system_info.baseboard == Baseboard.INTEL and re.search('.bios\Z', gt_url):
                    sm.error('Invalid URL. Intel systems are not compatible with Supermicro bios settings.')
                    exit()
                elif self.system_info.baseboard == Baseboard.SUPERMICRO and re.search('.INI\Z', gt_url):
                    sm.error('Invalid URL. Supermicro systems are not compatible with Intel bios settings.')
                    exit()
                r = requests.get(gt_url)
                gt_data = r.text
                self.gt_file = os.path.join(bios_settings_dir, re.search('(GOLDEN_TEMPLATE.*(\.bios|\.INI))', gt_url,
                                                                          re.IGNORECASE).group(1))
            else:
                data = requests.get(jarvis_bios_settings + system.p_number + '_' + system.customer + '/')
                gt_list = re.findall('href="\.?\/?(GOLDEN_TEMPLATE.*(\.bios|\.INI))"', data.text, re.IGNORECASE)
                if gt_list:
                    latest = sorted(gt_list, reverse=True)
                    r = requests.get(jarvis_bios_settings + system.p_number + '_' + system.customer + '/' +
                                           latest[0][0])
                    gt_data = r.text
                    self.gt_file = os.path.join(bios_settings_dir, latest[0][0])
            if not gt_data:
                print('No Golden Template could be found for the system...')
                print('If you would like to upload the current BIOS settings as the Golden Template please run '
                      '<vios --upload>.')
                exit()
        except requests.RequestException as e:
            sm.error('Vios could not get the latest Golden Template from Jarvis... Error was:', str(e))
            exit()
        except AttributeError as e:
            sm.error('Vios was unable to parse Golden Template file. Error Was:', str(e))
            exit()

        try:
            file_list = os.listdir(bios_settings_dir)
        except (IOError, OSError):
            os.mkdir(bios_settings_dir)
            file_list = os.listdir(bios_settings_dir)

        if gt_data:
            try:
                # Remove any existing Golden Template files then write the latest or specified GT to the system.
                for gt in file_list:
                    if re.search('(GOLDEN_TEMPLATE.*(\.bios|\.INI))', gt):
                        os.remove(os.path.join(bios_settings_dir + gt))
                with open(self.gt_file, 'w') as fw:
                    try:
                        fw.write(gt_data)
                    except (UnicodeEncodeError, UnicodeDecodeError):
                        #Added support for unicode characters.
                        gt_data = unicode(gt_data)
                        gt_data = gt_data.replace(u'\ufffd', u'\u00ae')
                        gt_data = gt_data.encode('ISO-8859-1')
                        fw.write(gt_data)
            except (IOError, OSError) as e:
                sm.error('Vios could not save {0} to {0}... Error was:'.format(self.gt_file, bios_settings_dir), str(e))
                exit()
        elif not gt_data and not self.gt_file:
            sm.error('Vios could not get the latest Golden Template data... Exiting.')
            exit()

    def get_bios_settings(self):
        """
        Attempt to acquire the current bios settings, and save them to the system. On a Supermicro system this is done
        with sum and on an Intel system this is done with Syscfg. Once settings have been gathered write them to a file
        in the bios_settings_dir for reference by the user, and remove any old current_bios_settings present in the
        directory.

        Called by:
            --compare
            --upload

        Steps:
            - Remove previous settings files that exist on the system.
            - Generate new bios current bios settings file
            - Save file in bios_settings_dir

        current bios settings syntax: sum -c getcurrentbioscfg --file current_bios_settings_YYYY-MM-DD-HH-MM-SS.bios
        """
        try:
            bios_files = os.listdir(bios_settings_dir)
        except (IOError, OSError):
            os.mkdir(bios_settings_dir)
            bios_files = os.listdir(bios_settings_dir)
        bios_file_name = time.strftime('current_bios_settings_%Y-%m-%d-%H-%M-%S')
        for x in bios_files:
            if re.search('current_bios', x, re.IGNORECASE):
                os.remove(bios_settings_dir + x)

        try:
            if self.system_info.baseboard == Baseboard.SUPERMICRO:
                try:
                    output = subprocess.check_output('sum -c getcurrentbioscfg --file {0}'.format(bios_settings_dir +
                                                                                       bios_file_name +
                                                                                       '.bios'), shell=True)
                    if 'created' in output.lower():
                        self.current_bios_file = bios_settings_dir + bios_file_name + '.bios'
                    else:
                        raise OSError
                except OSError as e:
                    sm.error('Unable to get current bios settings from sum. error was:', str(e))
                    exit()

            elif self.system_info.baseboard == Baseboard.INTEL:
                try:
                    # Intel bios files have to be saved as .INI to be recognized by syscfg
                    output = subprocess.check_output('syscfg /s {0} /b'.format(bios_settings_dir + bios_file_name + '.INI'),
                                          shell=True)

                    if 'successfully completed' in output.lower():
                        self.current_bios_file = bios_settings_dir + bios_file_name + '.INI'
                    else:
                        raise OSError
                except OSError as e:
                    sm.error('Unable to get current bios settings for syscfg. Error was:', str(e))
                    exit()
        except subprocess.CalledProcessError as e:
            sm.error('Vios was unable to acquire current BIOS settings... Error was:', str(e))
            exit()

    def parse_xml_tree(self, bios_data, path, tree):
        """
        A recursive function for gathering menus and settings from a tree generated from an XML bios file. Designed to output
        the same data structure as the the plain_text parsing section, gather_children takes a dictionary bios_data, the
        current path, and the current node of the tree structure and dives into tree recursively until all menus have been
        explored and added to the settings dictionary which is then added to bios_data with a key value of the path.

        Called by:
            --compare

        :param bios_data: dictionary to store bios file settings
        :param path: The current path to the settings. As the function dives into the tree this will change with menus
                    separated by '|'
        :param tree: Tree structure of xml attributes (Menus, Settings, Text, etc...). This function only cares about Menus
                    and Settings.
        :return bios_data: Modified dictionary with key values of the different menus and values which are dictionaries of the
                    settings.
        """
        settings = {}

        for element in tree:
            if element.tag == 'Setting':
                try:
                    settings[element.attrib['name']] = element.attrib['selectedOption']
                except KeyError:
                    try:
                        settings[element.attrib['name']] = element.attrib['checkedStatus']
                    except KeyError:
                        try:
                            settings[element.attrib['name']] = element.attrib['settingValue']
                        except KeyError:
                            try:
                                # For 'Password' and 'String' settings:
                                # You must dive into the element tree for each setting to get a value.
                                if element.attrib['type'] == 'Password':
                                    settings[element.attrib['name']] = element[0].find('HasPassword').text
                                elif element.attrib['type'] == 'String':
                                    settings[element.attrib['name']] = element.find('StringValue').text
                            except KeyError:
                                settings[element.attrib['name']] = None
                                sm.error('Encountered an unknown setting of type {0}. Setting was:'
                                         ''.format(element.attrib['type']), '{0}'.format(element.attrib['name']))

            if element.tag == 'Menu':
                bios_data = self.parse_xml_tree(bios_data, path + '|' + element.attrib['name'], element.getchildren())

        if settings != {}:
            bios_data[path] = settings

        return bios_data

    def get_bios_data(self, path):
        """
        A gathering function for getting bios setting information from a file saved to the bios_settings directory.
        This is done by determining the format of the file and gathering the various settings set by the bios. This is
        loaded into a dictionary and returned.

        Called by:
            --compare

        :param path: file path and name to gather bios settings from.

        Sample bios data: {'BIOS::Main': {'Quiet Boot': 'Enabled', 'Post Error Pause': 'Disabled'} 'BIOS::Advanced': {}}

        :return: bios_data : Dictionary containing bios settings information
        """

        if not path:
            sm.error('No file was specified in get_bios_data, unable to compare bios settings... Exiting.')
            exit()

        try:
            with open(path) as fh:
                file_data = fh.read()
        except IOError as e:
            sm.error('Unable to read data from {0} error was:'.format(path), str(e))
            exit()

        bios_data = {}

        # XML bios file logic.
        if re.search('<?xml version.*>', file_data):
            file_data = re.sub('<!--.*-->\n', '', file_data)
            file_data = re.sub('^\n', '', file_data)

            try:
                xml_root = ET.fromstring(file_data)
            except ET.ParseError as e:
                sm.error('Unable to parse xml in {0}. Error was:'.format(path), str(e))
                exit()

            for element in xml_root:
                if element.tag == 'Menu' and element.attrib['name'] != 'Main':
                    bios_data = self.parse_xml_tree(bios_data, element.attrib['name'], element)

        # Plain bios file logic
        else:
            if self.system_info.baseboard == Baseboard.SUPERMICRO:
                file_data = re.sub('(#.*)', '', file_data)
                file_data = re.sub('(//.*)', '', file_data)
            elif self.system_info.baseboard == Baseboard.INTEL:
                file_data = re.sub('(;.*)', '', file_data)

            menu_list = re.split(r"\n\n", file_data)
            for menu in menu_list:
                menu_name = ''
                try:
                    menu_name = re.search('\[(.*)\]', menu).group(1)
                except AttributeError:
                    if menu:
                        sm.error('Unable to acquire menu name for settings. Error occurred with:', menu)

                if menu_name:
                    bios_data[menu_name] = {}

                setting_list = re.findall('(.*)=(.*)', menu)

                for setting in setting_list:
                    bios_data[menu_name][setting[0]] = re.sub('\s\s+', '', setting[1])

        return bios_data

    def compare_settings(self, cb_data, gt_data, path='', diff=''):
        """
        Given two Dictionaries of bios settings, determine whether the settings are the same. If they are, indicate this
        to the user. If they are not indicate which settings differ and which files they belong to.

        Called by:
            --compare

        :param cb_data: Current bios settings configured on the system.
        :param gt_data: Golden template bios settings configured on the system.
        :param path: Path to the setting. (Menus)
        :param diff: String for recording differences between current and golden template bios files.
        """
        if len(cb_data) != len(gt_data):
            sm.error('Current BIOS settings and the Golden Template settings do not match... Are you sure the'
                     'Golden Template is for this system?')
            exit()

        for key in cb_data.keys():
            if key not in gt_data.keys():
                sm.error('Menu: {0} was not found in the Golden Template BIOS settings. Please double check this.')
            else:
                if type(cb_data[key]) is dict:
                    path = key
                    diff = self.compare_settings(cb_data[key], gt_data[key], path, diff)
                else:
                    if cb_data[key] != gt_data[key]:
                        diff += BOLD + path + ' -> ' + key + '\n' + END + \
                               '\t Curent Bios Setting: ' + RED + cb_data[key] + END + '\n' + \
                                '\t Golden Template Setting: ' + GREEN + gt_data[key] + END + '\n\n'

        return diff

    def compare_bios(self):
        """
        Compare current bios settings to that of the golden template settings and report any differences to the user.
        This is the primary driver for the --compare flag.

        Called by:
            --compare

        To compare bios settings the following must occur:
            - Generate current bios settings on the system and save into a specified directory.
            - See if a Golden Template file exists, if it does, download it and put it in the specified directory.
                - If it does not, indicate this to the user. (Ask if they would like to upload the current settings?)
                - Exit
            - Parse each bios file and compare the settings to the other.
            - Report any and all differences between the two files.
            - Exit
        """
        self.get_bios_settings()
        self.get_gt()

        cb_data = self.get_bios_data(self.current_bios_file)
        gt_data = self.get_bios_data(self.gt_file)

        diff = self.compare_settings(cb_data, gt_data)

        if diff == '':
            print(GREEN + 'No differences were found between the two files!' + END)
        else:
            print(RED + 'Vios found differences between the Current BIOS settings and the Golden Template!\n'
                  'Differences are:\n\n' + END)
            print(diff)

    def apply_bios(self, gt_url=None):
        """
        Apply bios settings supplied by a golden template to the system. This can be either supplied to Vios by the
        user or downloaded from Jarvis automatically.

        Called by:
            --auto

        To apply bios settings the following must occur:
            - Determine if a Golden Template exists on Jarvis and download the latest, or if a url is supplied download
                from URL by calling get_gt with the gt_url.
            - Using the downloaded Golden Template utilize either syscfg or sum to apply bios settings to the system.
            - Indicate to the user the settings have succeeded or failed. (reboot)
            - Exit

        :param gt_url: Web url specifying the Golden_Template to download and configure the system with.
        """

        self.get_gt(gt_url)
        print('Applying Golden Template settings from {0}... Please wait.'.format(self.gt_file))
        try:
            if self.system_info.baseboard == Baseboard.INTEL:
                subprocess.check_call('syscfg /r {0} /b'.format(self.gt_file), shell=True)

                print(GREEN + 'BIOS settings successfully updated from Golden Template!' + END)
                print(BOLD + 'Grabbing current bios settings.' + END)
                self.get_bios_settings()
                print(GREEN + 'Done.' + ' Please reboot the system for the changes to take effect.' + END)

            elif self.system_info.baseboard == Baseboard.SUPERMICRO:
                subprocess.check_call('sum -c ChangeBiosCfg --file {0}'.format(self.gt_file), shell=True)

                print(GREEN + 'BIOS settings successfully updated from Golden Template!' + END)
                print(BOLD + 'Grabbing current bios settings.' + END)
                self.get_bios_settings()
                print(GREEN + 'Done.' + ' Please reboot the system for changes to take effect.' + END)

            else:
                sm.error('Unable to apply bios settings, Baseboard is not supported.')

        except subprocess.CalledProcessError or OSError as e:
            sm.error('Something went wrong while applying Golden Template settings, if using a url please make sure the'
                     ' Golden Tempate is for the current system. Error was:', str(e))


def gather_system_info():
    """
    Query Syscheck for information on the system. syscheck should return a json structure containing any and
    all information from trogdor for the system. Function also queries dmidecode for the motherboard manufacturer and
    validates the activation status of a system if it is Supermicro.

    :return system: A SystemInfo object which contains all important system information.
    """
    system = SystemInfo()

    try:
        print(YELLOW + 'Gathering system information... This may take a minute.' + END)
        info = subprocess.check_output('syscheck -t --json', shell=True)
        json_data = loads(info)
    except subprocess.CalledProcessError:
        sm.error('Syscheck failed to run, please ensure syscheck is installed and configured on the system.')
        exit()
    except Exception as e:
        sm.error('Failed to acquire syscheck information. Error was:', str(e))
        exit()

    try:
        if json_data['Components']['Motherboard']['Manufacturer'] == 'Supermicro':
            system.baseboard = Baseboard.SUPERMICRO
            system.binary = sum_binary
            system.validate_system() # Supermicro systems require activation to work
        elif json_data['Components']['Motherboard']['Manufacturer'] == 'Intel':
            system.baseboard = Baseboard.INTEL
            system.binary = intel_binary
        else:
            system.baseboard = Baseboard.OTHER

        system.p_number = json_data['Project Number']
        system.sm_number = json_data['SM Number']
        system.customer = json_data['Customer Name']
        system.order = json_data['Trogdor']['Order']
        system.serial = json_data['Trogdor']['Serial']

        try:
            m_output = subprocess.check_output('dmidecode -t baseboard', shell=True)
            b_output = subprocess.check_output('dmidecode -t bios', shell=True)
            ipmi_output = subprocess.check_output('ipmicfg -ver', shell=True)
        except subprocess.CalledProcessError or OSError as e:
            sm.error('Something happened while gathering motherboard information... Error was:', str(e))
            exit()

        try:
            # double check baseboard in case Trogdor didn't have info on the motherboard.
            if system.baseboard == Baseboard.OTHER:
                if 'intel' in m_output.lower():
                    system.baseboard = Baseboard.INTEL
                elif 'supermicro' in m_output.lower():
                    system.baseboard = Baseboard.SUPERMICRO


            system.model = re.search('Product Name:\s+(.*)', m_output).group(1)
            system.m_serial = re.search('Serial Number:\s+(.*)', m_output).group(1)
            system.bios = re.search('Version:\s+(.*)', b_output).group(1)
            system.ipmi_version = re.search('Firmware Version:\s+(.*)', ipmi_output).group(1)
        except AttributeError as e:
            sm.error('Could not gather information system for Golden Template. Error was:', str(e))
            exit()

    except KeyError as e:
        sm.error('Failed to access information returned by syscheck. Error was:', str(e))
        exit()

    return system


def parse_arguments():
    """
    Initialize arguments to be used in the program and determine which ones the user has selected. The arguments
    include:

        --version: Prints the Version number of the program and exits.
        --auto: Automatically configure the system. Through applying the latest Golden Template to the system, or
            uploading a new one.
        --compare: Compare the current bios settings to that of the Golden Template settings and display differences.
        --url: Given a supplied url to a Golden_Template apply the template to the system.
        --upload: Attempt to take the current bios settings and upload them to Jarvis as the Golden Template.

    :return: a list of arguments which have been selected by the user.
    """

    parser = argparse.ArgumentParser(description='vios is a utility for configuring and setting bios settings in '
                                                 'Supermicro and Intel basedboard systems. This is done by running sum'
                                                 ' in Supermicro systems and Syscfg in Intel based systems.')

    parser.add_argument('-v', '--version', action='store_true', dest='version',
                        help='Display the current version of vios.')
    parser.add_argument('-a', '--auto', action='store_true', dest='auto',
                        help='Automatically configure the system by taking the latest Golden Template and applying '
                             'it to the system.')
    parser.add_argument('-c', '--compare', action='store_true', dest='compare',
                        help='Compare current bios settings with those of the golden template. '
                             'Outputs the differences, if any, to the user.')
    parser.add_argument('-u', '--url', dest='url',
                        help='Given the supplied Golden_Template URL, Vios will fetch and apply the settings of this'
                             'file.')
    parser.add_argument('-up', '--upload', action='store_true', dest='upload',
                        help='Attempt to upload the current bios settings as the Golden Template for this system.')
    parser.add_argument('-d', '--display', action='store_true', dest='display',
                        help='Display Trogdor and BIOS information about the system.')
    args = parser.parse_args()

    return args


if __name__ == '__main__':
    """
    Start of application. Parse arguments and kick off functions based on these arguments.
    
    Program steps:
        - Determine arguments
        - Gather relevant system information
        - Determine board and bios type
        - Initialize system object
        - Execute based on arguments
    """

    args = parse_arguments()

    if args.version:
        print('Vios version: ' + version)
        exit()

    try:
        os.mkdir(bios_settings_dir)
    except (IOError, OSError):
        pass

    system = gather_system_info()

    # Default argument
    if args.display or len(sys.argv) == 1:
        print(GREEN + 'Vios version: ' + version + END)
        system.to_string()

    if args.compare:
        print(GREEN + 'Vios version: ' + version + END)
        print('Beginning BIOS comparison...')
        Bios(system).compare_bios()

    if args.auto:
        print(GREEN + 'Vios version: ' + version + END)
        print('Starting auto features...')
        Bios(system).apply_bios()

    if args.url:
        print(GREEN + 'Vios version: ' + version + END)
        print('Applying {0} to system...'.format(args.url))
        Bios(system).apply_bios(args.url)

    if args.upload:
        print(GREEN + 'Vios version: ' + version + END)
        print('Starting upload procedures...')
        Bios(system).upload_gt()
