####################################
#
# copyright 2015 trustees of Columbia University in the City of New York
#
# coded by Chia-Hao Liu, Simon Billinge and Dan Allan
#
# this code is in the public domain.  Use at your own risk.
#
#####################################
'''Module of helper functions for running experiments at the XPD instrument at NSLS-II

For instructions how to use these functions, please see the help tutorial online.
Instructions for reaching it are at the XPD beamline

Code is currently hosted at gitHub.com/chiahaoliu/xpdAcquireFuncs
'''
import os
import time
import copy
import datetime
import numpy as np
import pandas as pd
import bluesky.scans
from bluesky.broker_callbacks import LiveImage
from bluesky.callbacks import CallbackBase, LiveTable, LivePlot

from ophyd.commands import *
from ophyd.controls import *

from dataportal import DataBroker as db
from dataportal import get_events, get_table, get_images
from metadatastore.commands import find_run_starts
from tifffile import *

from bluesky.broker_callbacks import LiveImage

pd.set_option('max_colwidth',50)
pd.set_option('colheader_justify','left')

default_keys = ['owner', 'beamline_id', 'group', 'config', 'scan_id'] # required by dataBroker
feature_keys = ['sample_name','experimenters'] # required by XPD, time_stub and uid will be automatically added up as well

# These are the default directory paths on the XPD data acquisition computer.  Change if needed here
W_DIR = '/home/xf28id1/xpdUser/tif_base'                # where the user-requested tif's go.  Local drive
R_DIR = '/home/xf28id1/xpdUser/config_base'             # where the xPDFsuite generated config files go.  Local drive
D_DIR = '/home/xf28id1/xpdUser/dark_base'               # where the tifs from dark-field collections go. Local drive
S_DIR = '/home/xf28id1/xpdUser/script_base'             # where the user scripts go. Local drive

def _feature_gen(header):
    ''' generate a human readable file name. It is made of time + uid + sample_name + user

    field will be skipped if it doesn't exist
    '''
    uid = header.start.uid
    time_stub = _timestampstr(header.start.time)

    dummy_list = []
    for key in feature_keys:
        try:
            # truncate length
            if len(header.start[key])>12:
                value = header.start[key][:12]
            else:
                value = header.start[key]
            # clear space
            dummy = [ ch for ch in list(value) if ch!=' ']
            dummy_list.append(''.join(dummy))  # feature list elements is at the first level, as it should be
        except KeyError:
            pass

    inter_list = []
    for el in dummy_list:
        if isinstance(el, list): # if element is a list
            join_list = "_".join(el)
            inter_list.append(join_list)
        else:
            inter_list.append(el)
    feature = "_".join(inter_list)
    return feature

def _timestampstr(timestamp):
    time = str(datetime.datetime.fromtimestamp(timestamp))
    date = time[:10]
    hour = time[11:16]
    timestampstring = '_'.join([date,hour])
    return timestampstring

def _MD_template():
    ''' use to generate idealized metadata structure, for pictorial memory and
    also for data cleaning.
    '''
    gs = _bluesky_global_state()
    _clean_metadata()
    gs.RE.md['iscalib'] = 0
    gs.RE.md['isdark'] = 0
    gs.RE.md['isbackground'] = 0 # back ground image
    gs.RE.md['experimenters'] = []
    gs.RE.md['sample_name'] = ''
    gs.RE.md['calibrant'] = '' # transient, only for calibration set
    gs.RE.md['user_supply'] = {}
    gs.RE.md['commenets'] = ''
    gs.RE.md['SAF_number'] = ''

    gs.RE.md['sample'] = {}
    gs.RE.md['sample']['composition'] = {}

    gs.RE.md['dark_scan_info'] = {}
    gs.RE.md['scan_info'] = {}

    gs.RE.md['calibration_scan_info'] = {}
    gs.RE.md['calibration_scan_info']['calibration_information'] = {}

    return gs.RE.md

def scan_info():
    ''' hard coded scan information. Aiming for our standardized metadata
    dictionary'''
    gs = _bluesky_global_state()
    all_scan_info = []
    try:
        all_scan_info.append(gs.RE.md['scan_info']['scan_exposure_time'])
    except KeyError:
        all_scan_info.append('')
    try:
        all_scan_info.append(gs.RE.md['calibration_scan_info']['calibration_exposure_time'])
    except KeyError:
        all_scan_info.append('')
    try:
        all_scan_info.append(gs.RE.md['dark_scan_info']['dark_exposure_time'])
    except KeyError:
        all_scan_info.append('')
    print('scan exposure time is %s, calibration exposure time is %s, dark scan exposure time is %s' % (all_scan_info[0], all_scan_info[1], all_scan_info[2]))

def meta_gen(fields, values):
    '''generate metadata dictionary used in your run engines

        arguments:
        fields - list of strings - user defined metadata fields that will be dictionary keys
        values - list of strings - key values metadata values corresponding to fields your defined.

    returns:
        dictionary of fields and values
    '''
    metadata_dict = {}
    for i in range(len(fields)):
        metadata_dict[fields[i]] = values[i]
    return metadata_dict

def _dig_dict(d):
    '''completely unpack a nested dictionary'''
    emp_dict = {}
    # temporarily solution, need to fixed later on
    for k,v in d.items():
        emp_dict[k] = v
    return emp_dict

def write_config(d, config_f_name):
    '''reproduce information stored in config file and save it as a config file

    argument:
    d - dict - a dictionary that stores config data
    f_name - str - name of your config_file, usually is 'config+tif_file_name.cfg'
'''
    # temporarily solution, need a more robust one later on
    import configparser
    config = configparser.ConfigParser()
    for k,v in _dig_dict(d).items():
        config[k] = {}
        config[k] = v # temporarily use
    with open(config_f_name+'.cfg', 'w') as configfile:
        config.write(configfile)

def _filename_gen(header):
    '''generate a file name of tif file. It contains time_stub, uid and feature
    of your header'''

    uid = header.start.uid[:5]
    try:
        time_stub = _timestampstr(header.start.time)
    except KeyError:
        tim_stub = 'Imcomplete_Scan'
    feature = _feature_gen(header)
    file_name = '_'.join([time_stub, uid, feature])
    return file_name


def get_dark_images(num=300, dark_scan_exposure_time=0.2):
    ''' Manually acquire stacks of dark images that will be used for dark subtraction later

    This module runs scans with the shutter closed (dark images) and saves them tagged
    as such.  You shouldn't have to look at these, they will be automatically used later
    for doing dark subtraction when you collect actual images.

    The default settings are to collect 1 minute worth of dark scans in increments
    of 0.2 seconds.  This default behavior can be overridden by providing optional
    values for num (number of frames) and dark_scan_exposure_time.

    Arguments:
       num - int - Optional. Number of dark frames to take.  Default = 300
       cnt_time - float - Optional. exposure time for each frame. Default = 0.2
    '''
    gs = _bluesky_global_state()
    # set up scan
    gs = _bluesky_global_state()
    gs.RE.md['isdark'] = True
    dark_cnt_hold = copy.copy(pe1.acquire_time)
    pe1.acquire_time = dark_scan_exposure_time
    try:
        gs.RE.md['dark_scan_info']
    except KeyError:
        gs.RE.md['dark_scan_info'] = {}
    gs.RE.md['dark_scan_info'] = {'dark_scan_exposure_time':dark_scan_exposure_time}

    try:
        sh1.closer = 1  # close shutter
        ctscan = bluesky.scans.Count([pe1],num)
        ctscan.subs = LiveTable(['pe1_image_lightfield'])
        gs.RE(ctscan)

        gs.RE.md['isdark'] = False
        #del(gs.RE.md['dark_scan_info'])
        pe1.acquire_time = dark_cnt_hold
        # fixme code to to set filter/shutter back to initial state
    except:
        gs.RE.md['isdark'] = False
        #del(gs.RE.md['dark_scan_info'])
        pe1.acquire_time = dark_cnt_hold
        # fixme code to to set filter/shutter back to initial state

    # write images to tif file, only save 3 images in the middle as a hook and data interrogation
    dark_base_header = db[-1]
    uid = dark_base_header.start.uid[:6]
    time_stub = _timestampstr(dark_base_header.stop.time)
    imgs = np.array(get_images(dark_base_header,'pe1_image_lightfield'))
    #mid = round(num/2)
    for i in range(num-4, num):
        f_name = '_'.join([time_stub, uid, 'dark','00'+str(i)+'.tif'])
        w_name = os.path.join(D_DIR,f_name)
        img = imgs[i]
        imsave(w_name, img) # overwrite mode
        print('%ith images of dark scans have been saved to %s' % (i+1, W_DIR))
        if not os.path.isfile(w_name):
            print('Error: dark image tif file not written')
            print('Investigate and re-run')
            return
    global LAST_DARK_UID
    LAST_DARK_UID = dark_base_header.start.uid

def get_calibration_images (calibrant, wavelength, calibration_scan_exposure_time=0.2 , num=10, composition = False, **kwargs):
    '''Runs a calibration dataset

    Arguments:
        calibrant - string - name of your calibrant, for example, Ni.
        wavelength - float - wavelength in nm, which is obtained from verify_wavelength function
        calibration_exposure_time - float - count-time in seconds.  Default = 0.2 s
        num - int - number of exposures to take. Default = 10
        composition - list - chemical composition of your sample, it is described by phases and elements.
            For example, ['phase1':{'Na',1},'phase2':{'Cl':1}] for NaCl
        **kwargs - dictionary - User specified info about the calibration. Only use it to add information about the calibration
            It gets stored in the 'user_supplied' dictionary.
    '''
    gs = _bluesky_global_state()
    # Prepare hold state
    try:
        #composition_hold = copy.copy(gs.RE.md['sample']['composition']) as sample dictionary contains all information
        sample_name_hold = copy.copy(gs.RE.md['sample_name'])
        sample_hold = copy.copy(gs.RE.md['sample'])
        cnt_hold = copy.copy(pe1.acquire_time)
    except KeyError:
        composition_hold = []
        sample_name_hold = {}
    try:
        gs.RE.md['calibration_scan_info']
    except KeyError:
        gs.RE.md['calibration_scan_info'] = {}
        gs.RE.md['calibration_scan_info']['calibration_information']={}

    cnt_hold = copy.copy(pe1.acquire_time)
    gs.RE.md['iscalibration'] = True
    gs.RE.md['calibrant'] = calibrant
    gs.RE.md['sample_name'] = calibrant
    if not composition:
        gs.RE.md['sample']['composition'] = calibrant
        # fixme, in the future, this should be a parsed field:
        # [{'phase1':{'Na',1},'phase2':{'Cl':1}}]
    else:
        gs.RE.md['sample']['composition'] = composition
    gs.RE.md['calibration_scan_info']['calibration_scan_exposure_time']=calibration_scan_exposure_time
    gs.RE.md['calibration_scan_info']['num_calib_exposures']=num
    gs.RE.md['calibration_scan_info']['wavelength']=wavelength

    # extra fields, user defined fields
    extra_key = kwargs.keys()
    for key, value in kwargs.items():
        gs.RE.md['user_supply'][key] = value

    try:
        ctscan = bluesky.scans.Count([pe1], num=num)
        pe1.acquire_time = calibration_scan_exposure_time
        print('collecting calibration data. %s acquisitions of %s s will be collected' % (str(num),str(calibration_scan_exposure_time)))
        ctscan.subs = [LiveTable(['pe1_image_lightfield']), LiveImage('pe1_image_lightfield')]
        gs.RE(ctscan)

        # recover to previous state, set to values before calibration
        pe1.acquire_time = cnt_hold
        gs.RE.md['iscalibration'] = False
        del(gs.RE.md['calibrant'])
        gs.RE.md['sample_name'] = sample_name_hold
        gs.RE.md['sample'] = sample_hold
        #gs.RE.md['sample']['composition'] = composition_hold
    except KeyError:
        # recover to previous state, set to values before calibration
        pe1.acquire_time = cnt_hold
        gs.RE.md['iscalibration'] = False
        del(gs.RE.md['calibrant'])
        gs.RE.md['sample_name'] = sample_name_hold
        gs.RE.md['sample'] = sample_hold
        #gs.RE.md['sample']['composition'] = composition_hold
        print('scan failed. metadata dictionary reset to starting values.')
        print('To debug, try running some scans using ctscan=bluesky.scans.Count([pe1])')
        print('then do gs.RE(ctscan).  When it is working, run get_calibration_images() again')
        return

    # construct calibration tif file name
    calib_scan_header = db[-1]
    f_name = '_'.join(['calib', _filename_gen(calib_scan_header) +'.tif'])
    w_name = os.path.join(W_DIR, f_name)
    save_tif(calib_scan_header, w_name, sum_frames=True)

    global LAST_CALIB_UID
    LAST_CALIB_UID = calib_scan_header.start.uid


def get_count_scan(scan_time=1.0, scan_exposure_time=0.5, comments={}):
    '''function for getting a light image

    Arguments:
        scan_time - float - optional. data collection time for the scan. default = 1.0 seconds
        scan_exposure_time - float - optional. exposure time per frame. number of exposures will be
            set to int(scan_time/exposure_time) (round off)
        comments - dictionary - optional. dictionary of user defined key:value pairs.
        scan_mode - int - mode of your scan. if scan_mode = 0, this function
        will do count scan and if scan_mode = 1, this function will do a
        temperature
    '''
    gs = _bluesky_global_state()
    if comments:
        extra_key = comments.keys()
        for key, value in comments.items():
            gs.RE.md['user_supply'][key] = value
    # test if parent layers exitst
    try:
        gs.RE.md['scan_info']
        gs.RE.md['sample']
    except KeyError:
        gs.RE.md['scan_info']={}
        gs.RE.md['sample'] = {}
    # Prpare hold values, KeyError means blanck state, just pass it
    try:
        scan_type_hold = copy.copy(gs.RE.md['scan_info']['scan_type'])
    except KeyError:
        scan_type_hold =''
        pass
    try:
        scan_steps_hold = gs.RE.md['scan_info']['number_of_exposures']
    except KeyError:
        scan_steps_hold =''
        pass
    try:
        total_scan_duration_hold = gs.RE.md['scan_info']['total_scan_duration']
    except KeyError:
        total_scan_duration_hold =''
        pass
    try:
        temp_hold = gs.RE.md['sample']['temperature']  # fixme: temporarily use
    except:
        temp_hold =''
        pass

    # don't expose the PE for more than 5 seconds max, set it to 1 seconds if you go beyond limit
    if scan_exposure_time > 5.0:
        print('Your exposure time is larger than 5 seconds. This can damage detector')
        print('Exposure time is set to 4 seconds')
        print('Number of exposures will be recalculated so that scan time is the same....')
        scan_exposure_time = 4.0
        num = int(scan_time/scan_exposure_time)
        print('Number of exposures is now %s' % num)
    else:
        num = int(scan_time/scan_exposure_time)

    if num == 0: num = 1 # at least one scan


    # assign values to current scan
    scan_exposure_time_hold = copy.copy(pe1.acquire_time)
    pe1.acquisition_time = scan_exposure_time

    gs.RE.md['scan_info']['scan_exposure_time'] = scan_exposure_time
    gs.RE.md['scan_info']['number_of_exposures'] = num
    gs.RE.md['scan_info']['total_scan_duration'] = num*scan_exposure_time
    gs.RE.md['scan_info']['scan_type'] = 'count_scan'
    gs.RE.md['sample']['temp'] = str(cs700.value[1])+'k'

    # fixme: code to check the filter/shutter is open
    try:
    #sh1.open = 1 # force it to open
        scan = bluesky.scans.Count([pe1],num)
        scan.subs = [LiveTable(['pe1_image_lightfield']),LiveImage('pe1_image_lightfield')]
        gs.RE(scan)
        header = db[-1]
        #feature = _feature_gen(header)
        filename = _filename_gen(header)
        save_tif(header, sum_frames=True)
        #deconstruct the metadata
        gs.RE.md['scan_info'] ={'scan_exposure_time': scan_exposure_time_hold,'number_of_exposures': scan_steps_hold, 'total_scan_duration':total_scan_duration_hold, 'scan_type': scan_type_hold}
        gs.RE.md['user_supply'] = {}
        gs.RE.md['sample']['temperature'] = temp_hold
    except:
        # deconstruct the metadata
        gs.RE.md['scan_info'] = {
                'scan_exposure_time' : scan_exposure_time_hold,
                'number_of_exposures' : scan_steps_hold,
                'total_scan_duration' : total_scan_duration_hold,
                'scan_type' : scan_type_hold
                }
        gs.RE.md['user_supply'] = {}
        gs.RE.md['sample']['temperature'] = temp_hold
        print('image collection failed. Check why gs.RE(scan) is not working and rerun')
        return

def get_temp_scan(start_temperature, final_temperature, temperature_step, scan_exposure_time=0.5, comments={}):
    '''Running a temperature delta scan and save dark-corrected file

    Arguments:
        start_temperature - float - starting temperature
        final_temperature - float - final temperature
        temperature_step - int - step size of your temeprature scan.
        scan_exposure_time - float - optional. exposure time per frame, default value is 0.5 s
        comments - dictionary - optional. dictionary of user defined key:value pairs.
    '''
    gs = _bluesky_global_state()
    if comments:
        extra_key = comments.keys()
        for key, value in comments.items():
            gs.RE.md['user_supply'][key] = value
    # test if even parents layers exitst
    try:
        gs.RE.md['scan_info']
        gs.RE.md['sample']
    except KeyError:
        gs.RE.md['scan_info']={}
        gs.RE.md['sample'] = {}
    # Prepare hold values, KeyError means blanck state, just pass it
    try:
        scan_type_hold = copy.copy(gs.RE.md['scan_info']['scan_type'])
    except KeyError:
        scan_type_hold = ''
        pass
    try:
        scan_exposure_time_hold = copy.copy(gs.RE.md['scan_info']['scan_exposure_time'])
    except KeyError:
        scan_exposure_time_hold = ''
        pass
    try:
        scan_steps_hold = gs.RE.md['scan_info']['number_of_exposures']
    except KeyError:
        scan_steps_hold = ''
        pass
    try:
        total_scan_duration_hold = gs.RE.md['scan_info']['total_scan_duration']
    except KeyError:
        total_scan_duration_hold = ''
        pass

    # don't expose the PE for more than 5 seconds max, set it to 1 seconds if you go beyond limit
    if scan_exposure_time > 5.0:
        print('Your exposure time is larger than 5 seconds. This can damage detector')
        print('Exposure time is set to 4 seconds')
        scan_exposure_time = 4.0
    if temperature_step == 0: temperature_step==1 # at least one scan
    scan_steps = int((final_temperature - start_temperature)/temperature_step)

    try:
    # assign values from current scan
        scan_cnt_time_hold = copy.copy(pe1.acquire_time)
        pe1.acquisition_time = scan_exposure_time
        gs.RE.md['scan_info']['scan_exposure_time'] = scan_exposure_time
        gs.RE.md['scan_info']['number_of_exposures'] = scan_steps
        gs.RE.md['scan_info']['total_scan_duration'] = scan_steps*scan_exposure_time
        gs.RE.md['scan_info']['scan_type'] = 'temp_scan'

        # fixme: code to check the filter/shutter is open
        #tscan = bluesky.scans.DeltaScan(cs700, [pe1], start_temperature, final_temperature, scan_steps)
        tscan = bluesky.scans.AbsScan( [pe1], cs700, start_temperature, final_temperature, scan_steps)
        tscan.subs = [LiveTable(['pe1_image_lightfield']),LiveImage('pe1_image_lightfield')]

        gs.RE(tscan)
        header = db[-1]
        #feature = _feature_gen(header)
        filename = _filename_gen(header)
        temps = get_temp(header)
        save_tif(header, sum_frames = False, motor_series=temps)
    # note, do not close the shutter again afterwards, we will do it manually outside of this function

    # deconstruct the metadata
        gs.RE.md['scan_info'] ={'scan_exposure_time': scan_exposure_time_hold,'number_of_exposures': scan_steps_hold,'total_scan_duration': total_scan_duration_hold, 'scan_type': scan_type_hold}
        gs.RE.md['user_supplied'] = {}
    except:
        # deconstruct the metadata
        gs.RE.md['scan_info'] ={'scan_exposure_time': scan_exposure_time_hold,'number_of_exposures': scan_steps_hold,'total_scan_duration': total_scan_duration_hold, 'scan_type': scan_type_hold}
        gs.RE.md['user_supplied'] = {}
        print('image collection failed. Check why gs.RE(scan) is not working and rerun')
        return

# no it's not gonna work
#def get_temp_scan_test(t0, tf, t_space):
#    '''default value:
#        scan_time = 1.0, scan_exposure_time = 0.5, commments={}
#    '''
#    tscan = bluesky.scan.DeltaScan([pe1], cs700, t0, tf, tspace)
#    scan_type = 'temp_scan'
#    get_my_scan(tscan, scan_type)


def get_my_scan(scan_def, scan_type, scan_time=1.0, scan_exposure_time=0.5, comments={}):
    '''function for getting a light image

    Arguments:
        scan_def - bluesky scan object - user defined scan and pass it.
            Please refer to http://nsls-ii.github.io/bluesky/scans.html for syntax and further information.
        scan_type - str - scan type of user defined scan
        scan_time - float - optional. data collection time for the scan. default = 1.0 seconds
        scan_exposure_time - float - optional. exposure time per frame. number of exposures will be
            set to int(scan_time/exposure_time) (round off)
        comments - dictionary - optional. dictionary of user defined key:value pairs.
    '''
    gs = _bluesky_global_state()
    if comments:
        extra_key = comments.keys()
        for key, value in comments.items():
            gs.RE.md['user_supplied'][key] = value
    # test if parent layers exitst
    try:
        gs.RE.md['scan_info']
        gs.RE.md['sample']
        pass
    except KeyError:
        gs.RE.md['scan_info']={}
        gs.RE.md['sample'] = {}
    # Prpare hold values, KeyError means blanck state, just pass it
    try:
        scan_type_hold = copy.copy(gs.RE.md['scan_info']['scan_type'])
    except KeyError:
        scan_type_hold =''
        pass
    try:
        scan_steps_hold = gs.RE.md['scan_info']['number_of_exposures']
    except KeyError:
        scan_steps_hold =''
        pass
    try:
        total_scan_duration_hold = gs.RE.md['scan_info']['total_scan_duration']
    except KeyError:
        total_scan_duration_hold =''
        pass
    try:
        temp_hold = gs.RE.md['sample']['temperature']  # fixme: temporarily use
    except:
        temp_hold =''
        pass

    # don't expose the PE for more than 5 seconds max, set it to 1 seconds if you go beyond limit
    if scan_exposure_time > 5.0:
        print('Your exposure time is larger than 5 seconds. This can damage detector')
        print('Exposure time is set to 4 seconds')
        print('Number of exposures will be recalculated so that scan time is the same....')
        scan_exposure_time = 4.0
        num = int(scan_time/scan_exposure_time)
        print('Number of exposures is now %s' % num)
    else:
        num = int(scan_time/scan_exposure_time)

    if num == 0: num = 1 # at least one scan


    #gs.RE.md['scan_info']['detector'] = pe1  # pe1 is not a simple object, call it directly causes I/O Error

    try:
        # fixme: code to check the filter/shutter is open
        # assign values from current scan
        scan_exposure_time_hold = copy.copy(pe1.acquire_time)
        pe1.acquisition_time = scan_exposure_time

        gs.RE.md['scan_info']['scan_exposure_time'] = scan_exposure_time
        gs.RE.md['scan_info']['number_of_exposures'] = num
        gs.RE.md['scan_info']['total_scan_duration'] = num*scan_exposure_time
        gs.RE.md['scan_info']['scan_type'] = scan_type
        gs.RE.md['sample']['temp'] = str(cs700.value[1])+'k'
        scan = scan_def
        scan.subs = LiveTable(['pe1_image_lightfield'])
        gs.RE(scan)
        header = db[-1]
        #feature = _feature_gen(header)
        filename = _filename_gen(header)
        save_tif(header, sum_frames=True)
        #deconstruct the metadata
        gs.RE.md['scan_info'] ={'scan_exposure_time':
                scan_exposure_time_hold,'number_of_exposures': scan_steps_hold, 'total_scan_duration':total_scan_duration_hold, 'scan_type': scan_type_hold}
        gs.RE.md['user_supplied'] = {}
        gs.RE.md['sample']['temperature'] = temp_hold
    except:
        # deconstruct the metadata
        gs.RE.md['scan_info'] ={'scan_exposure_time':
                scan_exposure_time_hold,'number_of_exposures': scan_steps_hold,'total_scan_duration': total_scan_duration_hold, 'scan_type': scan_type_hold}
        gs.RE.md['user_supplied'] = {}
        gs.RE.md['sample']['temperature'] = temp_hold
        print('image collection failed. Check why gs.RE(scan) is not working and rerun')
        return


def load_calibration(config_file = False, config_dir = False):
    '''Function loads calibration values as metadata to save with scans

    takes calibration values from a SrXplanar config file and
    loads them in the bluesky global state run engine metadata dictionary.
    They will all automatically be saved with every run.

    An example workflow is the following:
    1) get_calibration_images('Ni',wavelength=0.1234)
    2) open xPDFsuite and run the calibration in the SrXplanar module (green button
           in xPDFsuite).  See SrXplanar help documentation for more info.
    3) write the calibration data to an xPDFsuite config file in config_base directory

    Arguments:
    config_file -str - optional. name of your desired config file. If unspecified, the most recent one will be used
    config_dir - str - optional. directory where your config files are located. If not specified, default directory is used
    normal usage is not to use change these defaults.
    '''
    gs = _bluesky_global_state()
    from configparser import ConfigParser
    # figure out directory to read from
    if not config_dir:
        read_dir = R_DIR
    else:
        read_dir = str(config_dir)

    if not config_file:
        # if not specified file, read the most recent config file in read_dir
        f_list = [ f for f in os.listdir(read_dir) if f.endswith('.cfg')]
        if len(f_list) ==0:
            print('There is no config file in %s. Please make sure you have at least created one config file' % read_dir)
            return
        f_dummy = []
        for f in f_list:
            f_dummy.append(os.path.join(read_dir,f))
        f_sort = sorted(f_dummy, key = os.path.getmtime)
        f_recent = f_sort[-1]
        f_time = _timestampstr(os.path.getmtime(f_recent))  # time of config file
        config_file_stub = str(f_recent)
        f_name = os.path.join(read_dir, config_file_stub)
        if len(f_sort) >0:
            print('Using %s, the most recent config file that was found' % config_file_stub)
        else:
            print('There is no .cfg file in '+ read_dir)
            print('make sure the config file has been written in that directory and has extension ".cfg"')
            return
    else:
        f_name = os.path.join(read_dir,config_file)
        if os.path.isfile(f_name):
            config_file_stub = config_file # name of config file
            f_time = _timestampstr(os.path.getmtime(f_name)) # time of config file
            print('Using user-supplied config file: %s located at %s' % (config_file, read_dir))
        else:
            print('Your config file "%s" is not found at "%s" Please check again your directory and filename' % (config_file, read_dir))
            return

    # read config file into a dirctionary
    config = ConfigParser()
    config.read(f_name)
    sections = config.sections()

    config_dict = {}
    for section in sections:
        config_dict[section] = {} # write down header
        options = config.options(section)
        for option in options:
            try:
                config_dict[section][option] = config.get(section, option)
                #if config_dict[option] == -1:
                #    DebugPrint("skip: %s" % option)
            except:
                print("exception on %s!" % option)
                config_dict[option] = None
    gs.RE.md['calibration_scan_info']['calibration_information'] = {'from_calibration_file':str(config_file_stub),'calib_file_creation_date':f_time, 'config_data':config_dict}

    print('Calibration metadata will be saved in dictionary "calibration_information" with subsequent scans')
    print('Type gs.RE.md to check if config data has been stored properly')
    print('Run load_calibration() again to update/switch your config file')

def new_experimenters(experimenters):
    ''' This function sets up experimenter name(s). This function can be run at anytime to change experimenter global setting
    Argument:
        experimenters - str or list - name of current experimenters
    '''
    gs = _bluesky_global_state()
    gs.RE.md['experimenters'] = experimenters
    print('Current experimenters is/are %s' % experimenters)
    print('To update metadata dictionary, re-run new_sample() or new_experimenters(), with desired information as the argument')


def new_sample(sample_name, composition, experimenters=[], comments={}, verbose = 1):
    '''set up metadata fields for your runengine

    This function sets up persistent metadata that will be saved with subsequent scans,
    including a list of experimenters and the sample composition, as well as other user
    defined comments.  It can be rerun multiple times until you are happy with the settings,
    then these settings will be applied to scan metadata when the scans are run later.

    Arguments:

    sample_name - str - current sample name, for example, dppa2 or Ni
    composition - list - chemical composition of your sample, it is described by phases and elements.
        For example, [{'phase1':{'Na',1}},{'phase2':{'Cl':1}}] for NaCl
    experimenters - list - optional. list of current experimenter(s). reuse current value if not given
    comments - dict - optional. user supplied comments that relate to the current sample. Default = ''
    verbose - bool - optional. set to false to suppress printed output.
    '''
    gs = _bluesky_global_state()
    if verbose: print('Setting up global run engines(gs.RE) with your metadata.......')

    if not experimenters:
        try:
            experimenters = gs.RE.md['experimenters']
        except TypeError:
            experimenters = ''
        print('Current experimenters is/are "%s"' % experimenters)
    else:
        new_exp = experimenters
        gs.RE.md['experimenters'] = new_exp
        print('"Experimenters" has been updated as "%s"' % experimenters)

    if not comments:
        try:
            comments = gs.RE.md['comments']
        except KeyError:
            comments = ''
        print('Current comments to this experiment is "%s"' % comments)
    else:
        new_comments = comments
        gs.RE.md['comments'] = comments
        print('"Comments" has been updated as "%s"' % comments)
    if not composition:
        try:
            gs.RE.md['sample']['composition']
        except KeyError:
            composition = []
        print('Current sample composition is %s' % composition)
    else:
        gs.RE.md['sample']['composition'] = composition
        print('Current sample composition is %s' % composition)
    print('To change experimenters or sample, rerun new_user() or new_sample() respectively, with desired experimenter list as the argument')
    
    gs.RE.md['sample_name'] = sample_name
    time_stub = _timestampstr(time.time())

    # try to set up parent layer
    try:
        gs.RE.md['sample']
    except KeyError:
        gs.RE.md['sample'] = {}
    gs.RE.md['sample_name'] = sample_name
    print('Current sample name is %s' % sample_name)
    gs.RE.md['sample']['composition'] = composition
    print('Current sample composition is "%s"' % composition)
    time_stub = _timestampstr(time.time())
    gs.RE.md['sample']['sample_load_time'] = time_stub
    if verbose: print('sample_load_time has been recorded: %s' % time_stub)
    print('To update metadata dictionary, re-run new_sample() or new_experimenters(), with desired information as the argument')
   # if verbose: print('Sample and experimenter metadata have been set')
    if verbose: print('To check what will be saved with your scans, type "gs.RE.md"')

#### block of search functions ####
def get_keys(fuzzy_key, d=None, verbose=0):
    ''' fuzzy search on key names contains in a nested dictionary.
    Return all possible key names starting with fuzzy_key
:
    Arguments:

    fuzzy_key - str - possible key name, can be fuzzy like 'exp', 'sca' or nearly complete like 'experiment'
    d        -- dictionary you want to search.  Use bluesky metadata store
                when not specified.
    '''
    if d is None:
        d = _bluesky_metadata_store()
    if hasattr(d,'items'):
        rv = [f for f in d.keys() if f.startswith(fuzzy_key)]
        if not verbose: print('Possible key(s) to your search is %s' % rv)
        return rv
        get_keys(fuzzy_key, d.values())

def get_keychain(wanted_key, d=None):
    ''' Return keychian(s) of specific key(s) in a nested dictionary

    argumets:
    wanted_key - str - name of key you want to search for
    d        -- dictionary you want to search.  Use bluesky metadata store
                when not specified.
    '''
    if d is None:
        d = _bluesky_metadata_store()
    for k, v in d.items():
        if isinstance(v, dict):
            result = get_keychain(wanted_key, v) # dig in nested element
            if result:
                return [k]+ result
        elif k == wanted_key:
            return [k]


def set_value(key, d=None):
    ''' Return the last parent dictionary of key. It is convenient to set metadata value

    arguments:
    key - str - name of key you want to search for
    d        -- dictionary you want to search.  Use bluesky metadata store
                when not specified.
    '''
    if d is None:
        d = _bluesky_metadata_store()
    keychain = get_keychain(key)
    keychain.remove(key)
    d0 = {} # copy information
    for k, v in d.items():
        d0[k]=v
    out = {}
    while True:
        if keychain:
            #keychain = get_keychain(key)
            keychain.reverse()
            try:
                key_pop = keychain.pop()
                out.update(d0[key_pop])
            except IndexError:
                out.update(d0)
        else:
            break
    return out


def build_keychain_list(key_list, d=None, verbose = 1):
    ''' Return a keychain list that yields all parent keys for every key in key_list
        E.g. d = {'layer1':{'layer2':{'mykey':'value'}}}
            build_keychain_list([layer2, mykey],d) = ['layer1', 'layer1.layer2']
    argumets:
    key_list - str or list - name of key(s) you want to search for
    d        -- dictionary you want to search.  Use bluesky metadata store
                when not specified.
    '''
    if d is None:
        d = _bluesky_metadata_store()
    result = []
    if isinstance(key_list, str):
        key_list_operate = []
        key_list_operate.append(key_list)
    elif isinstance(key_list, list):
        key_list_operate = key_list

    for key in key_list_operate:
        dummy = get_keychain(key)
        if dummy:
            if len(dummy) > 1:
                path = '.'.join(dummy)
                result.append(path)
            elif len(dummy) == 1: # key at first level
                path = dummy[0]
                result.append(path)
        else:  # find an empty dictionary
            path = key
            result.append(path)
        if verbose:
            print('keychain to your desired key %s is "%s"' % (key, path))
        else:
            pass
    return result

def search(desired_value, *args, **kwargs):
    '''Return all possible header(s) that satisfy your searching criteria

    this function operates in two logics:
    1) When desired_value and args are both given. It will search on all headers matches args = desired_value.
        args can be incomplete and in this case, this function yields multiple searches

    example:
    desired_value = 'TiO2'
    search(desired_value, *'sa') will return all headers that has keys starting with 'sa' and its corresponding
    values is 'TiO2' in metadata dictionary. Nanmely, it yields searchs on headers with sample = TiO2, sadness = TiO2 ...

    2) When desired_value is not given. It implies you already knew your searching criteria and are ready to type them explicitly,
        even with additional constrains.

    example:
    desired_value = 'TiO2'
    search (False, **{'sample_name':desired_value, 'additonal_field': 'additional_value ....}) will return
    headers that have exactly key pairs **{'sample_name':desired_value, 'additonal_field': 'additional_value ....}

    General stratege is to use the first logic to figure out what is your desired key.
    Then user the second logic to restrain your search

    arguments:
    desired_value - str - desired value you are looking for
    args - str - key name you want to search for. It can be fuzzy or complete. If it is fuzzy, all possibility will be listed.
    kwargs - dict - an dictionary that contains exact key-value pairs you want to search for

    '''
    if desired_value and args:
        possible_keys = get_keys(args)
        keychain_list = build_keychain_list(possible_keys, verbose =0)
        search_header_list = []
        for i in range(len(keychain_list)):
            dummy_search_dict = {}
            dummy_search_dict[keychain_list[i]] = desired_value
            dummy_search_dict['group'] = 'XPD' # create an anchor as mongoDB and_search needs at least 2 key-value pairs
            search_header = db(**dummy_search_dict)
            search_header_list.append(search_header)
            print('Your %ith search "%s=%s" yields %i headers' % (i,
                keychain_list[i], desired_value, len(search_header)))
            return search_header_list
    elif not desired_value and kwars:
        if len(kwargs)>1:
            search_header = db(**kwargs)
        elif len(kwargs) == 1:
            kwargs['group'] = 'XPD'
            search_header = db(**kwargs)
        else:
            print('You gave empty search criteria. Please try again')
            return
        return search_header
    else:
        print('Sorry, your search is somehow unrecongnizable. Please make sure you are putting values to right fields')


def table_gen(headers):
    ''' Takes in a header list generated by search functions and return a table
    with metadata information

    Argument:
    headers - list - a list of bluesky header objects

    '''
    plt_list = list()
    feature_list = list()
    comment_list = list()
    uid_list = list()

    if type(list(headers)[1]) == str:
        header_list = []
        header_list.append(headers)
    else:
        header_list = headers

    for header in header_list:
        #feature = _feature_gen(header)
        #time_stub = _timestampstr(header.stop.time)
        #header_uid = header.start.uid
        #uid_list.append(header_uid[:5])
        #f_name = "_".join([time_stub, feature])
        f_name =_filename_gen(header)
        feature_list.append(f_name)

        try:
            comment_list.append(header.start['comments'])
        except KeyError:
            comment_list.append('None')
        try:
            uid_list.append(header.start['uid'][:5])
        except KeyError:
            # jsut in case, it should never happen
            print('Some of your data do not even have a uid, it is very dangerous, please contact beamline scientist immediately')
    plt_list = [feature_list, comment_list] # u_id for ultimate search
    inter_tab = pd.DataFrame(plt_list)
    tab = inter_tab.transpose()
    tab.columns=['Features', 'Comments' ]

    return tab


def time_search(startTime,stopTime=False,exp_day1=False,exp_day2=False):
    '''return list of experiments run in the interval startTime to stopTime

    this function will return a set of events from dataBroker that happened
    between startTime and stopTime on exp_day

    arguments:
    startTime - datetime time object or string or integer - time a the beginning of the
                period that you want to pull data from.  The format could be an integer
                between 0 and 24 to set it at a  whole hour, or a datetime object to do
                it more precisely, e.g., datetime.datetime(13,17,53) for 53 seconds after
                1:17 pm, or a string in the time form, e.g., '13:17:53' in the example above
    stopTime -  datetime object or string or integer - as starTime but the latest time
                that you want to pull data from
    exp_day - str or datetime.date object - the day of the experiment.
    '''
    # date part
    if exp_day1:
        if exp_day2:
            d0 = exp_day1
            d1 = exp_day2
        else:
            d0 = exp_day1
            d1 = d0
    else:
        d0 = datetime.datetime.today().date()
        d1 = d0

    # time part
    if stopTime:

        t0 = datetime.time(startTime)
        t1 = datetime.time(stopTime)

    else:
        now = datetime.datetime.now()
        hr = now.hour
        minu = now.minute
        sec = now.second
        stopTime = datetime.time(hr,minu,sec) # if stopTime is not specified, set current time as stopTime

        t0 = datetime.time(startTime)
        t1 = stopTime

    timeHead = str(d0)+' '+str(t0)
    timeTail = str(d1)+' '+str(t1)

    header_time=db(start_time=timeHead,
                   stop_time=timeTail)

    event_time = get_events(header_time, fill=False)
    event_time = list(event_time)

    print('||You assign a time search in the period:\n'+str(timeHead)+' and '+str(timeTail)+'||' )
    print('||Your search gives out '+str(len(header_time))+' results||')

    return header_time


def sanity_check():
    gs = _bluesky_global_state()
    user = gs.RE.md['experimenters']
    print('Current experimenter(s) are: %s' % user)
    try:
        sample_name = gs.RE.md['sample_name']
    except KeyError:
        sample_name =''
    try:
        gs.RE.md['calibration_scan_info']['from_calibration_file']
    except KeyError:
        calib_file =''
    print('Calibration file being used is %s' % calib_file)

    try:
        compo = gs.RE.md['sample']['composition']
        print('Current sample_name is %s, composition is %s' % (sample_name, compo))
    except KeyError:
        print('Current sample_name is %s, composition is %s' % (sample_name,''))
    try:
        calib_file = gs.RE.md['calibration_scan_info']['calibration_information']['from_calibration_file']
        print('Current calibration file being used is %s' % calib_file)
    except KeyError:
        pass

    scan_info()

def print_dict(d, ident = '', braces=1):
    ''' Recursively print nested dictionary, give a easy to read form

    argument:
        d - dict - nested dictionary you want to print
    '''

    for key, value in d.items():
        if isinstance(value, dict):
            print ('%s%s%s%s' %(ident,braces*'[', key , braces*']'))
            print_dict(value, ident+'  ', braces+1)
        else:
            print (ident+'%s = %s' %(key, value))

def _timestampstr(timestamp):
    time= str(datetime.datetime.fromtimestamp(timestamp))
    date = time[:10]
    hour = time[11:16]
    timestampstring = '_'.join([date, hour])
    return timestampstring
def _clean_metadata():
    '''
    reserve for completely cleaning metadata dictionary
    return nothing
    '''
    gs = _bluesky_global_state()
    extra_key_list = [ f for f in gs.RE.md.keys() if f not in default_keys]
    for key in extra_key_list:
        del(gs.RE.md[key])
    gs.RE.md['sample'] = {}

def save_tif(headers, tif_name = False, sum_frames = True, dark_uid=False, motor_series = False):
    ''' save images obtained from dataBroker as tiff format files. It returns nothing.

    arguments:
        headers - list - a list of header objects obtained from a query to dataBroker
        file_name - str - optional. File name of tif file being saved. default setting yields a name made of time, uid, feature of your header
        sum_frames - bool - optional. when it is set to True, image frames contained in header will be summed as one file
        dark_uid - str - optional. The uid of dark_image you wish to use. If unspecified, the most recent dark stack in dark_base will beused.
        motor_series -list - optional. series of motor values. Use it when doing motor scan, like temperature scan, tth_scan or so.

    '''
    if type(list(headers)[1]) == str:
        header_list = list()
        header_list.append(headers)
    else:
        header_list = headers

    # iterate over header(s)
    for header in header_list:
        print('Plotting and saving your dark-corrected image(s) now....')
        try:
            comment = header.start['comments']
        except KeyError:
            pass
        # get images and exposure time from headers
        try:
            light_imgs = np.array(get_images(header,'pe1_image_lightfield'))
        except IndexError:
            uid = header.start.uid
            print('This header with uid = %s does not contain any image' % uid)
            print('Was area detector correctly mounted then?')
            print('Stop saving')
            return
        header_events = list(get_events(header))
        cnt_time = header_events[0]['data']['pe1_acquire_time']
            #print('scan exposure time in your header can not be found, use default 0.5 secs for dark image correction.')
            #print('Dont worry, a slightly off correction will not significantly degrade quality of your data') # fixme: comfort user??

        # Identify the latest dark stack
        '''dummy = [ f for f in os.listdir(D_DIR) ]
        d_list = list()
        for el in dummy:
            d_list.append(os.path.join(D_DIR, el))
        sorted(d_list, key = os.path.getmtime)
        d_last = d_list[-1]
        d_last_uid = dummy[:5]
        #d_last_uid = dark_last[17:22] ... for future use if f_name = (time_stub)_uid_feature
        print(d_last_uid)
        d_header = db[d_last_uid]
        '''
        if not dark_uid:
            try:
                LAST_DARK_UID # see if LAST_DARK_UID global variable exits
                dark_header = db[str(LAST_DARK_UID)]
            except NameError:
                #uid_list = [] # get uid from dark_base
                pass
            f_d = [ f for f in os.listdir(D_DIR) ]
            if not f_d:
                print('You do not have any dark image in dark_base, please at least do one dark scan before all scans')
            else:
                pass
            uid_list = []
            for f in f_d:
                uid_list.append(f[17:22])
            uid_unique = np.unique(uid_list)
            dark_header_list = []
            for d_uid in uid_unique:
                dark_header_list.append(db[d_uid])
            dark_time_list = []
            for dark_header in dark_header_list:
                dark_time_list.append(header.stop.time)
            ind = np.argsort(dark_time_list)
            dark_header = dark_header_list[ind[-1]]
        else:
            dark_header = db[str(dark_uid)]

        print('Use dark images of uid = %s' % dark_header.start.uid)
        dark_events = list(get_events(dark_header))
        dark_cnt_time = dark_events[0]['data']['pe1_acquire_time']
            #print('Could not find dark_exposure_time in header with uid= %s; using default 0.5 seconds now...' % dark_header.start.uid)
            #print('Dont worry, a slightly off correction will not significantly degrade quality of your data')
            #dark_cnt_time = 0.5 # default value

        # dark correction
        dark_num = int(np.round(cnt_time / dark_cnt_time)) # how many dark frames needed for single light image
        print('Number of dark images applied to correction your image(s) is: %i....' % dark_num)
        dark_img_list = np.array(get_images(dark_header,'pe1_image_lightfield')) # confirmed that it comes with reverse order
        dark_len = dark_img_list.shape[0]
        correct_imgs = []
        for i in range(light_imgs.shape[0]):
            correct_imgs.append(light_imgs[i]-np.sum(dark_img_list[dark_len-dark_num:dark_len],0)) # use last d_num dark images

        if sum_frames:
            if not tif_name:
                header_uid = header.start.uid[:5]
                time_stub = _timestampstr(header.stop.time)
                feature = _feature_gen(header)
                f_name ='_'.join([time_stub, header_uid, feature+ '.tif'])
            else:
                f_name = tif_name

            w_name = os.path.join(W_DIR,f_name)
            img = np.sum(correct_imgs,0)
            try:
                fig = plt.figure(f_name)
                plt.imshow(img)
                plt.show()
            except TypeError:
                print('This is a squashed tif')
            imsave(w_name, img) # overwrite mode now !!!!
            if os.path.isfile(w_name):
                print('dark corrected image "%s" has been saved at "%s"' % (f_name, W_DIR))
            else:
                print('Sorry, something went wrong with your tif saving')
                return

        else: # not in summing mode but have to tell if we are dealing with motor series
            if not motor_series:
                events = list(get_events(header))
                for i in range(len(events)):
                    if not tif_name:
                        header_uid = header.start.uid[:5]
                        time_stub = _timestampstr(events[i]['timestamps']['pe1_image_lightfield'])
                        feature = _feature_gen(header)
                        f_name ='_'.join([time_stub, header_uid, feature, '00'+str(i)+'.tif'])
                        #f_name = '_'.join([_filename_gen(header),'00'+str(i)+'.tif'])
                        #f_name = '_'.join(header_filename, '00'+str(i)+'.tif')
                    else:
                        f_name = tif_name + '_00' + str(i) +'.tif'
                    #print(f_name)
                    w_name = os.path.join(W_DIR,f_name)
                    img = correct_imgs[i]
                    try:
                        fig = plt.figure(f_name)
                        plt.imshow(img)
                        plt.show()
                    except TypeError:
                        pass
                    imsave(w_name, img) # overwrite mode now !!!!
                    if os.path.isfile(w_name):
                        print('dark corrected %s has been saved at %s' % (f_name, W_DIR))
                    else:
                        print('Sorry, something went wrong with your tif saving')
                        return
            else:
                # require input of motor series!!!
                events = list(get_events(header))
                for i in range(len(events)): # length of light images should be as long as temp series
                    if not tif_name:
                        header_uid = header.start.uid[:5]
                        time_stub = _timestampstr(events[i]['timestamps']['pe1_image_lightfield'])
                        feature = _feature_gen(header)
                        temp = str(motor_series[i])+'k'
                        f_name ='_'.join([time_stub, header_uid, feature, temp, '00'+str(i)+'.tif'])
                        #f_name = '_'.join([_filename_gen(header),'00'+str(i)+'.tif'])
                        #f_name = '_'.join(header_filename, '00'+str(i)+'.tif')
                    else:
                        f_name ='_'.join([tif_name, '00'+str(i)+'.tif'])
                    #print(f_name)
                    w_name = os.path.join(W_DIR,f_name)
                    img = correct_imgs[i]
                    try:
                        fig = plt.figure(f_name)
                        plt.imshow(img)
                        plt.show()
                    except TypeError:
                        pass
                    imsave(w_name, img) # overwrite mode now !!!!
                    if os.path.isfile(w_name):
                        print('dark corrected %s has been saved at %s' % (f_name, W_DIR))
                    else:
                        print('Sorry, something went wrong with your tif saving')
                        return

        '''
        # write config data
        f_name = None # clear value and re-assign it as we don't need to save multiple files
        #f_name = '_'.join([time_stub, uid, feature+'.cfg'])
        f_name = _filename_gen(header) + '.cfg'
        config_f_name = '_'.join(['config', f_name])
        w_config_name = os.path.join(W_DIR, config_f_name)
        if set_value('config_data', header.start):
            #w_name =None
            config_dict = set_value('config_data',header.start)['config_data']
            write_config(config_dict, w_config_name)
            if os.path.isfile(w_config_name):
                print('%s has been saved at %s' % (config_f_name, W_DIR))
            # write the rest metadata as a file:
            #metadata_dict = []
            #for k,v in header.start.items():
            #    if k == 'calibration_information':
            #        pass
            #    else:
            #        metadata_dict[k]=v
            #else:
            #    print('Sorry, something went wrong when saving your config data. Please use write_config() function to try again')
            # very unlikely to happen but still leave it here


        #fixme: write!!!
        else:
            print('Can not find your calibration config data in current metadata dictionary. Did you save it at all?')
            print('if you want to save your config data later, use write_config() function')
            pass
        #if isinstance(config_dict, dict):
            #pass
        #else:
            #print('your config data is not a dictionary. Writting stop')
            #return
        '''


def get_temp(header):
    ''' Return temperatue serises in a header
    argument:
    header - obj - a blusky header object
    '''
    img_len = np.array(get_images(header,'pe1_image_lightfield')).shape[0]
    events = list(get_events(header))
    temp_len = len(events)
    if img_len == temp_len:
        pass
    else:
        print('Something went wrong. Number of images you collected is not equal to the number of temeprature recorded')
        print('Maybe some points are missing or unable to pull out from filestore. Please ask beamlinescientist what to do')
        return
    try:
        temp_series = list()
        for event in events:
            temp = event['data']['cs700']
            temp_series.append(temp)
        return temp_series
    except KeyError:
        print('There is no temperature information in this header, please check if you are looking at the correct data')
        return

def run_script(script_name):
    ''' Run user script in script base

    argument:
    script_name - str - name of script user wants to run. It must be sit under script_base to avoid confusion when asking Python to run script.
    '''
    module = script_name
    m_name = os.path.join('S_DIR', module)
    #%run -i $m_name


def _bluesky_global_state():
    '''Import and return the global state from bluesky.
    '''
    from bluesky.standard_config import gs
    return gs


def _bluesky_metadata_store():
    '''Return the dictionary of bluesky global metadata.
    '''
    gs = _bluesky_global_state()
    return gs.RE.md
# Holding place
    #print(str(check_output(['ls', '-1t', '|', 'head', '-n', '10'], shell=True)).replace('\\n', '\n'))
    #gs.RE.md.past({'field':'value'})
#    if not sample_temperature:
#        temp = cs700.value[1]