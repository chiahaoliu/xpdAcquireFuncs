####################################
#
# copyright 2015 trustees of Columbia University in the City of New York
#
# coded by Chia-Hao Liu, Simon Billinge, Pavol Juhas and Dan Allan
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
import matplotlib.pyplot as plt
import matplotlib as mpl
import numpy as np
import pandas as pd
import json

import bluesky
from bluesky.scans import *
from bluesky.broker_callbacks import LiveImage
from bluesky.callbacks import CallbackBase, LiveTable, LivePlot
from bluesky import Msg

from ophyd.commands import *
from ophyd.controls import *

from dataportal import DataBroker as db
from dataportal import get_events, get_table, get_images
from metadatastore.commands import find_run_starts

from xpdacquire.config import datapath
from xpdacquire.utils import composition_analysis
from xpdacquire.xpd_search import *
from tifffile import *


pd.set_option('max_colwidth',50)
pd.set_option('colheader_justify','left')

default_keys = ['owner', 'beamline_id', 'group', 'config', 'scan_id'] # required by dataBroker
feature_keys = ['sample_name','experimenters'] # required by XPD, time_stub and uid will be automatically added up as well

# These are the default directory paths on the XPD data acquisition computer.  Change if needed here
W_DIR = datapath.tif                # where the user-requested tif's go.  Local drive
R_DIR = datapath.config             # where the xPDFsuite generated config files go.  Local drive
D_DIR = datapath.dark               # where the tifs from dark-field collections go. Local drive
S_DIR = datapath.script             # where the user scripts go. Local drive

# Instanciate bluesky objects

def _bluesky_global_state():
    '''Import and return the global state from bluesky.'''

    from bluesky.standard_config import gs
    return gs

def _bluesky_metadata_store():
    '''Return the dictionary of bluesky global metadata.'''

    gs = _bluesky_global_state()
    return gs.RE.md

def _bluesky_RE():
    import bluesky
    from bluesky.run_engine import RunEngine
    from bluesky.run_engine import DocumentNames
    RE = RunEngine()
    bluesky.register_mds.register_mds(RE)
    return RE

def _bluesky_metadata_store():
    '''Return the dictionary of bluesky global metadata.
    '''
    gs = _bluesky_global_state()
    return gs.RE.md


ipshell = get_ipython()
gs = ipshell.user_ns['gs']
RE = _bluesky_RE()
pe1 = ipshell.user_ns['pe1']
cs700 = ipshell.user_ns['cs700']
sh1 = ipshell.user_ns['sh1']
gs.TEMP_CONTROLLER = cs700
tth_cal = ipshell.user_ns['tth_cal']
th_cal = ipshell.user_ns['th_cal']
photon_shutter = ipshell.user_ns['photon_shutter']

def feature_gen(header):
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
    m_hour = hour.replace(':','-')
    timestampstring = '_'.join([date,hour])
    #corrected_timestampstring = timestampstring.replace(':','-')
    return timestampstring

def _MD_template():
    ''' use to generate idealized metadata structure, for pictorial memory and
    also for data cleaning.
    '''
    #gs = _bluesky_global_state()
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
    #gs = _bluesky_global_state()
    all_scan_info = []
    try:
        all_scan_info.append(gs.RE.md['scan_info']['scan_exposure_time'])
    except KeyError:
        all_scan_info.append('')
    try:
        all_scan_info.append(gs.RE.md['calibration_scan_info']['calibration_scan_exposure_time'])
    except KeyError:
        all_scan_info.append('')
    try:
        all_scan_info.append(gs.RE.md['dark_scan_info']['dark_scan_exposure_time'])
    except KeyError:
        all_scan_info.append('')
    print('scan exposure time is %s, calibration exposure time is %s, dark scan exposure time is %s' % (all_scan_info[0], all_scan_info[1], all_scan_info[2]))


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

def filename_gen(header):
    '''generate a file name of tif file. It contains time_stub, uid and feature
    of your header'''

    uid = header.start.uid[:5]
    try:
        time_stub = _timestampstr(header.start.time)
    except KeyError:
        tim_stub = 'Imcomplete_Scan'
    feature = feature_gen(header)
    file_name = '_'.join([time_stub, uid, feature])
    return file_name



def run_script(script_name):
    ''' Run user script in script base

    argument:
    script_name - str - name of script user wants to run. It must be sit under script_base to avoid confusion when asking Python to run script.
    '''
    module = script_name
    m_name = os.path.join('S_DIR', module)
    #%run -i $m_name


##################### common functions  #####################

def sum_int(header=db[-1]):
    ''' sum intensity of last scan. Unused function
    '''
    int_value = list()
    imgs = np.array(get_images(header,'pe1_image_lightfield'))
    for i in range(imgs.shape[0]):
        int_value.append(np.sum(imgs[i]))
    plt.figure()
    plt.plot(int_value)
    plt.show()


def get_calibration_images (calibrant, wavelength, calibration_scan_exposure_time=0.1, num=10, comments = ''):
    '''Runs a calibration dataset

    Arguments:
        calibrant - string - name of your calibrant, for example, Ni.
        wavelength - float - wavelength in nm, which is obtained from verify_wavelength function
        calibration_exposure_time - float - count-time in seconds.  Default = 0.2 s
        num - int - number of exposures to take. Default = 10
        comments- str - User specified info about the calibration. Only use it to add information about the calibration
            It gets stored in the 'comments' field.
    '''
    #gs = _bluesky_global_state()
    #pe1 = _bluesky_pe1()
    #RE = _bluesky_RE()

    # FIXME my_md = md_gen()
    '''
    # Prepare hold state
    try:
        sample_hold = copy.copy(gs.RE.md['sample']) #as sample dictionary contains all information
    except KeyError:
        sample_hold = {}
    try:
        composition_hold = copy.copy(gs.RE.md['sample']['composition']) 
    except KeyError:
        composition_hold = []
    try:
        sample_name_hold = copy.copy(gs.RE.md['sample_name'])
    except KeyError:
        sample_name_hold = ''
    

    try:
        gs.RE.md['calibration_scan_info']
    except KeyError:
        gs.RE.md['calibration_scan_info'] = {}
        gs.RE.md['calibration_scan_info']['calibration_information']={}

    cnt_hold = copy.copy(pe1.acquire_time)
    gs.RE.md['iscalibration'] = True
    gs.RE.md['calibrant'] = calibrant
    gs.RE.md['sample_name'] = calibrant
    #if not composition:
        #gs.RE.md['sample']['composition'] = calibrant
        ## fixme, in the future, this should be a parsed field:
        ## [{'phase1':{'Na',1},'phase2':{'Cl':1}}]
    #else:
        #gs.RE.md['sample']['composition'] = composition

    gs.RE.md['calibration_scan_info']['calibration_scan_exposure_time']=calibration_scan_exposure_time
    gs.RE.md['calibration_scan_info']['num_calib_exposures']=num
    gs.RE.md['calibration_scan_info']['wavelength']=wavelength

    # extra fields, user defined fields
    gs.RE.md['comments'] = comments
    '''

     _open_shutter()
 
    try:
        pe1.acquire_time = calibration_scan_exposure_time
        ctscan = bluesky.scans.Count([pe1], num=num)
        print('collecting calibration data. %s acquisitions of %s s will be collected' % (str(num),str(calibration_scan_exposure_time)))
        ctscan.subs = LiveTable(['pe1_image_lightfield'])
        gs.RE(ctscan, sample = my_md)

        _close_shutter()
        
        #FIXME recover md
        # _recover_md()
        ''' 
        # recover to previous state, set to values before calibration
        pe1.acquire_time = cnt_hold
        gs.RE.md['iscalibration'] = False
        del(gs.RE.md['calibrant'])
        gs.RE.md['sample_name'] = sample_name_hold
        gs.RE.md['sample'] = sample_hold
        gs.RE.md['sample']['composition'] = composition_hold
        '''

    except:
        _close_shutter()
        # FIXME _revocer_md()
        ''''
        pe1.acquire_time = cnt_hold
        gs.RE.md['iscalibration'] = False
        del(gs.RE.md['calibrant'])
        gs.RE.md['sample_name'] = sample_name_hold
        gs.RE.md['sample'] = sample_hold
        gs.RE.md['sample']['composition'] = composition_hold
        '''
        print('scan failed. metadata dictionary reset to starting values.')
        print('To debug, try running some scans using ctscan=bluesky.scans.Count([pe1])')
        print('then do gs.RE(ctscan).  When it is working, run get_calibration_images() again')
        return

    # construct calibration tif file name
    calib_scan_header = db[-1]
    f_name = '_'.join(['calib', filename_gen(calib_scan_header) +'.tif'])
    w_name = os.path.join(W_DIR, f_name)
    save_tif(calib_scan_header, w_name, sum_frames=True)
    if os.path.isfile(w_name):
        print('%s has been saved at %s' % (f_name, W_DIR))
        print('Please open XPDFSuite and perform calibration')

    global LAST_CALIB_UID
    LAST_CALIB_UID = calib_scan_header.start.uid


def get_light_images(scan_time=1.0, scan_exposure_time=0.2):
    '''function for getting a light image

    Arguments:
        scan_time - float - optional. data collection time for the scan. default = 1.0 seconds
        scan_exposure_time - float - optional. exposure time per frame. number of exposures will be set to int(scan_time/exposure_time) (round off)
        comments - dictionary - optional. dictionary of user defined key:value pairs.
        scan_def - object - optional. bluesky scan object defined by user. Default is a count scan
    '''
    #FIXME we need a method to create metadata dictionary
    # my_md = _md_gen()
    
    #gs = _bluesky_global_state()
    #RE = _bluesky_RE()
    #pe1 = _bluesky_pe1()
    #cs700 = _bluesky_cs700()
    '''
    if comments:
        #extra_key = comments.keys()
        #for value in comments:
        try:
            gs.RE.md['comments']
            comments_hold = copy.copy(gs.RE.md['comments'])
        except KeyError:
            gs.RE.md['comments'] = {}
        
        gs.RE.md['comments']['light'] = comments
    
    # test if parent layers exitst
    try:
        gs.RE.md['scan_info']
        gs.RE.md['sample']
    except KeyError:
        gs.RE.md['scan_info']={}
        gs.RE.md['sample'] = {}
    # Prpare hold values, KeyError means blanck state, just pass it
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
    '''

    # don't expose the PE for more than 5 seconds max, set it to 1 seconds if you go beyond limit
    if scan_exposure_time > 5.0:
        print('Your exposure time is larger than 5 seconds. This can damage detector')
        print('Exposure time is set to 5 seconds')
        print('Number of exposures will be recalculated so that scan time is the same....')
        scan_exposure_time = 5.0
        num = int(np.rint(scan_time/scan_exposure_time))
    else:
        num = int(np.rint(scan_time/scan_exposure_time))
    print('Number of exposures is now %s' % num)
    if num == 0: num = 1 # at least one scan
    
    #configure pe1:
    scan_exposure_time_hold = copy.copy(pe1.acquire_time)
    pe1.acquire_time = scan_exposure_time

    # set up scan definition
    scan = bluesky.scans.Count([pe1],num)

    '''
    # assign values to current scan
    #scan_type = scan.logdict()['scn_cls']
    gs.RE.md['scan_info']['scan_exposure_time'] = pe1.acquire_time
    gs.RE.md['scan_info']['number_of_exposures'] = num
    gs.RE.md['scan_info']['total_scan_duration'] = num*pe1.acquire_time
    #gs.RE.md['scan_info']['scan_type'] = scan_type
    gs.RE.md['sample']['temp'] = str(cs700.value[1])+'k'
    '''
      
    
    try:
        # open_shutter, dump md to scan and close shutter

        # FIXME: we need a method to create md.
        # my_md = md_gen(inputs)

        _open_shutter()
        gs.RE(scan, sample = my_md)
        _close_shutter()
        
    except:
        # if scan fails. close shutter and recover metadata
        
        # FIXME: we need a method to store md in parallel so that we can recover anytime
        #_recover_md()
        
        _close_shutter()
        #_recover_md()
        print('image collection failed. Check why run engine is not working and rerun')

        '''
        gs.RE.md['scan_info'] = {'scan_exposure_time' : scan_exposure_time_hold,'number_of_exposures' : scan_steps_hold, 'total_scan_duration' : total_scan_duration_hold }
        gs.RE.md['comments'] = {}
        gs.RE.md['sample']['temperature'] = temp_hold
        '''
        
        return

def _nstep(start, stop, step_size):
    ''' helper function to define motor series
    '''
    step = np.arange(start, stop, step_size)
    return np.append(step, stop)

def tseries(start_temp, stop_temp, step_size = 5.0, total_exposure_time_per_point =1.0, exposure_time_per_frame = 0.2, t_device = cs700, comments = ''):
    ''' run a temperature series scan.

    argument:
    start_temp - float - start point of your temperature scan
    stop_temp - float - end point of your temperature scan
    step_size - flot - optional. step size of each temeprature scan
    total_scan_time_per_point - float - optional. total scan time at each temepratrue step
    exposure_time_per_point - flot - optional. exposure time per frame.
    comments - list - optional. comments to current experiment. It should be a list of strings
    '''
    import uuid

    temp_series = _nstep(start_temp, stop_temp, step_size) 
    print('Temperature series will cover these points %s' % str(temp_series))
    print('Ctrl + c to exit if it is incorrect')
    print('To view data from intermidate scans, open a new ipython session')
    print('type "from xpdacquire.xpdacquirefuncs import *"')
    print('type "save_tif(db[-1])"')
    print('then use xPDFsuite or program of choice to investigate')
    print('DO NOT PASS ANY MOTOR COMMANDS IN NEW IPYTHON SESSION, that will ruin your scan')

    md_hold = copy.deepcopy(gs.RE.md)
    try:
        # FIXME we need a method to create md rubustly
        # my_md = md_gen(inputs)
        '''
        gs.RE.md['istseries'] = True
        tseries_uid = str(uuid.uuid4())
        gs.RE.md['tseries'] = {}
        gs.RE.md['tseries']['start_time'] = time.time()
        gs.RE.md['tseries']['uid'] = tseries_uid
        gs.RE.md['tseries']['start'] = start_temp
        gs.RE.md['tseries']['stop'] = stop_temp
        gs.RE.md['tseries']['step_size'] = step_size
        gs.RE.md['tseries']['device'] = str(t_device)
        '''

        for temp in temp_series:
            mov(t_device, temp)
            actual_temp = t_device.value[1] # real temperature
            #gs.RE.md['sample']['temp'] = actual_temp
            get_light_images(total_exposure_time_per_point, exposure_time_per_frame)
            header = db[-1]
            # take care of file name in temperature scan
            #header = db[-1]
            #f_name = '_'.join(feature_gen(header), str(temp)+'K')
            #save_tif(db[-1], tif_name = f_name, dark_correction = correction_option)
        # FIXME: we need a method to reover md
        # _recover_md()
        print('Temperature scan finished...')

    except:
        print('Error or keybord interupt. Please try again')
        #_recover_md()
    return


def myMotorscan(start, stop, step_size, motor, det, exposure_time_per_point = 1.0, exposure_time_per_frame = 0.2):
    ''' define a general motor scan with advanced msg method
    '''    

    step_series = _nstep(start, stop, step_size)
    # don't expose PE1 more than 5 secs
    if exposure_time_per_point > 5:
        print('Your exposure time exceeds 5 secs which could damage detector')
        print('Recalculating exposure time per frame while still maintain your total exposre time....')
        exposure_time_per_point = 5
    
    exposure_num = np.rint(exposure_time_per_point/exposure_time_per_frame)    
    pe1.acquire_time = exposure_time_per_frame
    yield Msg('open_run')
    yield Msg('configure',det)
    for step in step_series:
        yield Msg('create')
        yield Msg('set', motor, step, block_group = 'A')
        yield Msg('wait', None, 'A')
        yield Msg('read', motor)
        num = 0
        while num < exposure_num:
            yield Msg('trigger', det)
            yield Msg('read', det)
            num +=1
        yield Msg('save')
    yield Msg('deconfigure',det)
    yield Msg('close_run')


def Tseries(start_temp, stop_temp, step_size, motor = cs700, det = pe1, exposure_time_per_point = 1.0, exposure_time_per_frame = 0.2):
    ''' run a temperature series scan.

    argument:
    start_temp - float - start point of your temperature scan
    stop_temp - float - end point of your temperature scan
    step_size - flot - optional. step size of each temeprature scan
    total_scan_time_per_point - float - optional. total scan time at each temepratrue step
    exposure_time_per_point - flot - optional. exposure time per frame.
    comments - list - optional. comments to current experiment. It should be a list of strings
    '''
    Tscan = myMotorscan(start_temp, stop_temp, step_size, exposure_time_per_point,exposure_time_per_frame, motor, det)
    
    temp_series = _nstep(start_temp, stop_temp, step_size) 
    print('Temperature series will cover these points %s' % str(temp_series))
    print('Ctrl + c to exit if it is incorrect')
    print('To view data from intermidate scans, open a new icollection session')
    print('type "from xpdacquire.xpdacquirefuncs import *"')
    print('type "save_tif(db[-1])"')
    print('then use xPDFsuite or program of choice to investigate')
    print('DO NOT ENTER ANY MOTOR COMMANDS IN NEW IPYTHON SESSION, that will ruin your scan')

    #md_hold = copy.copy(gs.RE.md)
    try:
        # FIXME we need a method to create md robustly
        # my_md = md_gen()
        '''
        gs.RE.md['istseries'] = True
        #tseries_uid = str(uuid.uuid4())
        gs.RE.md['tseries'] = {}
        gs.RE.md['tseries']['start_time'] = time.time()
        #gs.RE.md['tseries']['uid'] = tseries_uid
        gs.RE.md['tseries']['start'] = start_temp
        gs.RE.md['tseries']['stop'] = stop_temp
        gs.RE.md['tseries']['step_size'] = step_size
        gs.RE.md['tseries']['device'] = str(motor.name)
        '''
        _open_shutter()
        gs.RE(Tscan, LiveTable([str(motor),str(det)+'_image_lightfield']), sample=my_md)
        _close_shutter()
        
        # FIXME: we need a method to recover md
        # _md_recover()

    except:
        print('Error or keybord interupt. Please try again')
        # FIXME: we need a method to recover md
        # _md_recover()
        return

def view_image(headers=False):
    if not headers:
        header_list = []
        header_list.append(db[-1])
    else:
        if type(list(headers)[0]) == str:
            header_list = []
            header_list.append(headers)
        else:
            header_list = headers
    for header in header_list:
        img_len = np.array(get_images(header,'pe1_image_lightfield')).shape[0]
        sum_img = np.sum(np.array(get_images(header,'pe1_image_lightfield')),0) / img_len
        imshow(sum_img)

def sanity_check():
    #gs = _bluesky_global_state()
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

def print_metadata():
    print_dict(gs.RE.md)


def _clean_metadata():
    '''
    reserve for completely cleaning metadata dictionary
    return nothing
    '''
    #gs = _bluesky_global_state()
    extra_key_list = [ f for f in gs.RE.md.keys() if f not in default_keys]
    for key in extra_key_list:
        del(gs.RE.md[key])
    gs.RE.md['sample'] = {}

def get_motor(header, motor_name):
    ''' Return motor serises in a header
    argument:
    header - obj - a blusky header object
    motor_name - str - name of motor in your scan
    '''
    img_field =[el for el in header.descriptors[0]['data_keys'] if el.endswith('_image_lightfield')][0]
    img_len = np.array(get_images(header,img_field)).shape[0]
    events = list(get_events(header))
    motor_len = len(events)
    if img_len == motor_len:
        pass
    else:
        print('Something went wrong. Number of images you collected is not equal to the number of motor steps')
        #print('Maybe some points are missing or unable to pull out from filestore. Please ask beamline scientist for what to do')
        return
    try:
        motor_series = list()
        for event in events:
            motor_step = event['data'][motor_name]
            motor_series.append(motor_step)
        return motor_series
    except KeyError:
        print('There is no motor information to %s in this header, please check if you are looking at the correct data' % motor_name)
        return

def find_dark(light_cnt_time):
    '''find desired cnt_time in dark_base'''

    f_d = [ f for f in os.listdir(D_DIR) ]
    if not f_d:
            print('You do not have any dark image in dark_base, please at least do one dark scan before all scans')
            return
    else:
        pass

    uid_list = []
    for f in f_d:
        uid_list.append(f[17:22])
    uid_unique = np.unique(uid_list)
    
    dark_header_list = []
    for d_uid in uid_unique:
        dark_header_list.append(db[d_uid])

    dark_list = [ h for h in dark_header_list if find_cnt_time(h) == light_cnt_time ]
    
    if dark_list:
        #for h in dark_list:
            #print('cnt_time in dark_header_list are: %s' % str(find_cnt_time(h)))
        dark_time_list = []
        for dark_header in dark_list:
            dark_time_list.append(dark_header.stop.time)

        ind = np.argsort(dark_time_list)
        dark_header = dark_list[ind[-1]]
        #dark_header = dark_list[ind[0]]
        #print('cnt_time after sorting is: %s' % str(find_cnt_time(dark_header)))
        return dark_header
    else:
        print('Could not find desired cnt_time in your dark_base. Please rerun get_dark_images with correct arugment to complete dark_base')
        return


def find_cnt_time(header):
    ''' find cnt_time of header given'''

    events = list(get_events(header))
    cnt_time_field = [ el for el in events[0]['data'] if el.endswith('acquire_time') ][0]
    cnt_time = events[0]['data'][cnt_time_field]
    return cnt_time

def get_dark_images(dark_scan_exposure_time = False):
    ''' Manually acquire stacks of dark images that will be used for dark subtraction later

    This module runs scans with the shutter closed (dark images) and saves them tagged
    as such.  You shouldn't have to look at these, they will be automatically used later
    for doing dark subtraction when you collect actual images.

    The default settings are to collect 1 minute worth of dark scans in increments
    of 0.2 seconds.  This default behavior can be overridden by providing optional
    values for num (number of frames) and dark_scan_exposure_time.

    Arguments:
       dark_scan_exposure_time - float- optional. exposure time of dark frames .
    '''
    # set up scan
    #gs = _bluesky_global_state()
    #RE = _bluesky_RE()
    #pe1 = _bluesky_pe1()
    dark_cnt_hold = copy.copy(pe1.acquire_time)

    if not dark_scan_exposure_time:
        # FIXME my_md = md_gen()
        '''
        try:
            gs.RE.md['dark_scan_info']
        except KeyError:
            gs.RE.md['dark_scan_info'] = {}
        '''

        print('Collecting your dark stacks now...')

        # get rid of residuals
        pe1.acquire_time=0.1
        dummy_scan = bluesky.scans.Count([pe1], num=10)
 
        from bluesky import RunEngine
        gs.RE(dummy_scan)
        
        # Real dark stack
        dark_dict = {}
        try:
            _close_shutter()
            
            for i in range(1,5):
                pe1.acquire_time = 0.1*i
                dark_scan_expsoure = pe1.acquire_time
                # FIXME my_md = md_gen()
                #gs.RE.md['dark_scan_info'] = {'dark_scan_exposure_time':pe1.acquire_time}

                ctscan = bluesky.scans.Count([pe1],num=1)
                ctscan.subs = LiveTable(['pe1_image_lightfield'])
                gs.RE(ctscan, sample=my_md)
        
                # verify dimension in dark_base
                dark_base_header=db[-1]
                img = np.array(get_images(dark_base_header,'pe1_image_lightfield'))
                print('image shape is '+ str(np.shape(img)))
                
                # fill up dark_dict
                dark_dict[pe1.acquire_time] = dark_base_header.start.uid
           
            # FIXME _recover_md()
            #gs.RE.md['isdark'] = False
            pe1.quire_time = dark_cnt_hold

        
            dark_dict_name = '_'.join(['dark_base', _timestampstr(time.time())])
            w_dark_dict_name =  os.path.join(D_DIR, dark_dict_name)
            print('Your dark dictionary with (exposure_time, uid) pairs is :')
            print(dark_dict)

            #save dark_dict for search later on
            with open(w_dark_dict_name+'.txt', 'w') as w_dark:
                json.dump(dark_dict, w_dark)
            if os.path.isfile(w_dark_dict_name+'.txt'):
                print('%s has been saved to %s' % (w_dark_dict_name, W_DIR))
            else:
                print('dark dictionary is not saved, please run get_dark_images() again')
                return

        except:
            # gs.RE.md['isdark'] = False
            # FIXME recover_md()
            pe1.acquire_time = dark_cnt_hold

            _close_shutter()
            print('Something went wrong, dark images acqusition was not complete. Please check everything and run get_dark_images() again')
            
            return

    else:
        # FIXME I know it is unstableeeeeeeee
        # allow user to collect dark frame with certain exposure time
        pe1.acquire_time = dark_scan_exposure_time
        ctscan = bluesky.scans.Count([pe1], num=1)
        gs.RE(ctscan)
        dark_dict_name = [f_name for f_name in os.listdir(D_DIR) if f_name.endswith('txt')]
        dark_dict_list = []

        for d in dark_dict_name:
            dark_dict_list.append(os.path.join(D_DIR,d))
        if not dark_dict_list:
            print('There is no dark dictionary in dark_base. Pleas run get_dark_images() again to build dark_base')
            return

        last_dark_dict = sorted(dark_dict_list, key = os.path.getmtime) # find the lastest dark_dict
        rv = last_dark_dict[-1]
        print(rv)
        with open(rv) as f:
            read_dict = json.load(f)
        new_dict = {str(pe1.acquire_time) : str(ctscan.start.uid)}
        read_dict.update(new_dict)
        with open(read_dict,'w') as f:
            json.dump(read_dict, f)
        return

def _close_shutter():
    photon_shutter_try = 0
    number_shutter_tries = 5
    while photon_shutter.value == 1 and photon_shutter_try < number_shutter_tries:
        photon_shutter.close_pv.put(1)
        time.sleep(4.)   
        print('photon_shutter value after close_pv.put(1): %s' % photon_shutter.value)
        photon_shutter_try += 1
    if photon_shutter.value == 1:
        print('photon shutter failed to close after %i tries. Please check before continuing' % photon_shutter_try)
    return

def _open_shutter():
    #shutter status
    if sh1.open:
        pass
    else:
        sh1.open = 1

    # this logic needed when we are using photon shutter at xpd
    print('photon_shutter value before open_pv.put(1): %s' % photon_shutter.value)
    # open photon shutter
    photon_shutter_try = 0
    photon_shutter_tries = 5
    while photon_shutter.value == 0 and photon_shutter_try < number_shutter_tries:
        photon_shutter.open_pv.put(1)
        time.sleep(4.)   
        print('photon_shutter value after open_pv.put(1): %s' % photon_shutter.value)
        photon_shutter_try += 1
    if photon_shutter.value == 0:
        print('photon shutter failed to open after %i tries. Please check before continuing' % photon_shutter)
        return



def save_tif(headers, tif_name = False, sum_frames = True, dark_uid = False, dark_correct = True):
    ''' save images obtained from dataBroker as tiff format files. It returns nothing.

    arguments:
        headers - list - a list of header objects obtained from a query to dataBroker
        file_name - str - optional. File name of tif file being saved. default setting yields a name made of time, uid, feature of your header
        sum_frames - bool - optional. when it is set to True, image frames contained in header will be summed as one file
        dark_uid - str - optional. The uid of dark_image you wish to use. If unspecified, the most recent dark stack in dark_base will beused.
        dark_correct - bool - optional. Decide if you want to dark_correction or not
    '''
    # prepare header
    if type(list(headers)[1]) == str:
        header_list = list()
        header_list.append(headers)
    else:
        header_list = headers

    # Find corresponding dark image that will be used to perform correction
    #print('Finding dark image with the same cnt time....')
    if not dark_uid:
        dark_dict_name = [f_name for f_name in os.listdir(D_DIR) if f_name.endswith('txt')]
        dark_dict_list = []
        for d in dark_dict_name:
            dark_dict_list.append(os.path.join(D_DIR,d))
        if not dark_dict_list:
            print('There is not dark dictionary in dark_base. Pleas run get_dark_images() again to build dark_base')
            return
        last_dark_dict = sorted(dark_dict_list, key = os.path.getmtime) # find the lastest dark_dict
        rv = last_dark_dict[-1]
        print(rv)
        with open(rv) as f:
            read_dict = json.load(f)
        #print(read_dict)
    else:
        dark_header = db[str(dark_uid)]

    # iterate over header(s)
    for header in header_list:
        print('Plotting and saving your image(s) now....')
        # get images and exposure time from headers
        try:
            img_field =[el for el in header.descriptors[0]['data_keys'] if el.endswith('_image_lightfield')][0]
            print('Images are pulling out from %s' % img_field)
            light_imgs = np.array(get_images(header,img_field))
        except IndexError:
            uid = header.start.uid
            print('This header with uid = %s does not contain any image' % uid)
            print('Was area detector correctly mounted then?')
            print('Stop saving')
            return
        
        header_events = list(get_events(header))

        # get events from header
        cnt_time = find_cnt_time(header)
        print('cnt_time = %s' % cnt_time)
        
        
        # container for final image, corrected or not
        correct_imgs = []

        if dark_correct:
            dark_uid = read_dict[str(cnt_time)]
            print('dark header used to correct image is %s: ' % dark_uid)
            dark_header = db[str(dark_uid)]
            print('dark_cnt_time = %s' % find_cnt_time(dark_header))
            # dark correction
            dark_img_field =[el for el in dark_header.descriptors[0]['data_keys'] if el.endswith('_image_lightfield')][0]
            dark_img_list = np.array(get_images(dark_header,dark_img_field)) # confirmed that it comes with reverse order
            dark_amount = dark_img_list[-1]

            for i in range(light_imgs.shape[0]):
                dummy = (light_imgs[i]-dark_amount)
                correct_imgs.append(dummy)
        else:
            for i in range(light_imgs.shape[0]):
                dummy = light_imgs[i] # raw image, no correction
                correct_imgs.append(dummy)
            
        scan_type = header.start.scan_type
        if scan_type != 'Count':
            sum_frames = False
        else:
            pass

        if sum_frames:
            if not tif_name:
                header_uid = header.start.uid[:5]
                time_stub = _timestampstr(header.stop.time)
                feature = feature_gen(header)
                if dark_correct:
                    f_name ='_'.join([time_stub, header_uid, feature+ '.tif'])
                else:
                    f_name = '_'.join([time_stub, header_uid, feature, 'raw.tif'])
            else:
                f_name = tif_name
            w_name = os.path.join(W_DIR,f_name)
            img = np.sum(correct_imgs,0)/len(correct_imgs)
            #if np.isnan(img).any():
                #print('we have nan in summed img')
            #else:
                #print('we do not have nan in summed img')
                #pass
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

        else:
            if scan_type == 'Count':  #fixme: is Count the only one doesn't move motor?
                for i in range(len(header_events)):
                    if not tif_name:
                        header_uid = header.start.uid[:5]
                        time_stub =_timestampstr(header_events[i]['timestamps'][img_field])
                        feature = feature_gen(header)
                        
                        if dark_correct:
                            f_name ='_'.join([time_stub, header_uid, feature, '00'+str(i)+'.tif'])
                        else:
                            f_name ='_'.join([time_stub, header_uid, feature, '00'+str(i), 'raw.tif'])
                    else:
                        f_name = tif_name + '_00' + str(i) +'.tif'
                    w_name = os.path.join(W_DIR,f_name)
                    img = correct_imgs[i]
                    if np.isnan(img).any():
                        print('we have nan in indivisual img')
                    else:
                        print('we do not have nan in indivisual img')
                        pass
                    if len(correct_imgs) <5:
                        try:
                            fig = plt.figure(f_name)
                            plt.imshow(img)
                            plt.show()
                        except TypeError:
                            pass
                    else:
                        #print('There are more than 5 images in this header, will not plot now for saving computation resource/')
                        #print('You can view these images after they are saved')
                        pass
                    
                    imsave(w_name, img) # overwrite mode now !!!!
                    if os.path.isfile(w_name):
                        print('dark corrected %s has been saved at %s' % (f_name, W_DIR))
                    else:
                        print('Sorry, something went wrong with your tif saving')
                        return


            else:
                print('This is a motor scan, frames will be saved seperately..')
                # is a motor scan now, get motor name
                motor_name = eval(header.start.motor).name
                motor_series = get_motor(header,motor_name)
                for i in range(len(header_events)): # length of light images should be as long as temp series
                    if not tif_name:
                        header_uid = header.start.uid[:5]
                        time_stub =_timestampstr(header_events[i]['timestamps'][img_field])
                        feature = feature_gen(header)
                        motor_step = str(motor_series[i])

                        if dark_correct:
                            f_name ='_'.join([time_stub, header_uid, feature, motor_step, '00'+str(i)+'.tif'])
                        else:
                            f_name ='_'.join([time_stub, header_uid, feature, motor_step, '00'+str(i), 'raw.tif'])
                    else:
                        f_name ='_'.join([tif_name, motor_step, '00'+str(i)+'.tif'])
                        
                    w_name = os.path.join(W_DIR,f_name)
                    img = correct_imgs[i]
                    if len(correct_imgs)<5:
                        try:
                            fig = plt.figure(f_name)
                            plt.imshow(img)
                            plt.show()
                        except TypeError:
                            pass
                    else:
                        #print('There are more than 5 images in this header, will not plot now for saving computation resource/')
                        #print('You can view these images after they are saved')
                        pass
                    imsave(w_name, img) # overwrite mode now !!!!
                    if os.path.isfile(w_name):
                        print('dark corrected %s has been saved at %s' % (f_name, W_DIR))
                    else:
                        print('Sorry, something went wrong with your tif saving')
                        return

        
        # write config data
        print('Writing config file used in header....')
        f_name = None # clear value and re-assign it as we don't need to save multiple files
        #f_name = '_'.join([time_stub, uid, feature+'.cfg'])
        f_name = filename_gen(header) + '.cfg'
        config_f_name = '_'.join(['config', f_name])
        config_w_name = os.path.join(W_DIR, config_f_name)
        try:
            config_dict = header.start['calibration_scan_info']['calibration_information']['config_data']
            if isinstance(config_dict, dict):
                pass
            else:
                print('Your config data is not a dictionary, please make sure you load your config file properly')
                print('User load_calibration() and then try again.')
                print('Stop saving')
                return
            write_config(config_dict, config_w_name)
            if os.path.isfile(config_w_name):
                print('%s has been saved at %s' % (config_f_name, W_DIR))
        except KeyError:
            print('It seems there is no config data in your metadata dictioanry or it is at wrong dictionary')
            print('User load_calibration() and then try again.')

        print('Writing metadata stored in header....')
        metadata = [ info for info in gs.RE.md if info != 'calibration_scan_info']
        md_f_name = filename_gen(header)+'.txt'
        md_w_name = os.path.join(W_DIR, md_f_name)
        with open(md_w_name, 'w') as f:
            json.dump(metadata, f)
        if os.path.isfile(md_w_name):
                print('%s has been saved at %s' % (md_f_name, W_DIR))
        else:
            print('Something went wrong when saving your metadata locally. Do not worry, it is still saved remotely in centralized filestore')
        
        print('||********Saving process SUCCEEDED********||')

# Holding place
    #print(str(check_output(['ls', '-1t', '|', 'head', '-n', '10'], shell=True)).replace('\\n', '\n'))
    #gs.RE.md.past({'field':'value'})
#    if not sample_temperature:
#        temp = cs700.value[1]


'''
def _bluesky_pe1():
    from ophyd.controls.area_detector import (AreaDetectorFileStoreHDF5, AreaDetectorFileStoreTIFF,AreaDetectorFileStoreTIFFSquashing)
    # from shutter import sh1
    #shctl1 = EpicsSignal('XF:28IDC-ES:1{Det:PE1}cam1:ShutterMode', name='shctl1')
    shctl1 = EpicsSignal('XF:28IDC-ES:1{Sh:Exp}Cmd-Cmd', name='shctl1')
    pe1 = AreaDetectorFileStoreTIFFSquashing('XF:28IDC-ES:1{Det:PE1}',name='pe1',stats=[], ioc_file_path = 'H:/pe1_data',file_path ='/home/xf28id1/pe1_data')#shutter=shctl1, #shutter_val=(1, 0))
    return pe1

def _bluesky_global_state():
    Import and return the global state from bluesky.

    from bluesky.standard_config import gs
    return gs

def _bluesky_metadata_store():
    Return the dictionary of bluesky global metadata.

    gs = _bluesky_global_state()
    return gs.RE.md

def _bluesky_cs700():
    from ophyd.controls import EpicsMotor, PVPositioner
    cs700 = PVPositioner('XF:28IDC-ES:1{Env:01}T-SP', readback='XF:28IDC-ES:1{Env:01}T-I', #done='XF:28IDC-ES:1{Env:01}Cmd-Busy',
            done_val=0, stop='XF:28IDC-ES:1{Env:01}Cmd-Cmd', 
            stop_val=13, put_complete=True, name='cs700')
    return cs700

def _bluesky_sh1():
    from xpdacquire.shutter import sh1 
    #sh1 = Nsls2Shutter(open='XF:28IDC-ES:1{Sh:Exp}Cmd:Opn-Cmd', open_status='XF:28IDC-ES:1{Sh:Exp}Sw:Opn1-Sts', close='XF:28IDC-ES:1{Sh:Exp}Cmd:Cls-Cmd', close_status='XF:28IDC-ES:1{Sh:Exp}Sw:Cls1-Sts')
    return sh1
'''
