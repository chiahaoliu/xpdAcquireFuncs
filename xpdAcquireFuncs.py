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
import sys
import time
import copy
import datetime
import numpy as np
import pandas as pd
import matplotlib as ml
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from configparser import ConfigParser

import localimports

#pd.set_option('max_colwidth',70)
pd.set_option('colheader_justify','left')

default_keys = ['owner', 'beamline_id', 'group', 'config', 'scan_id'] # required by dataBroker
feature_keys = ['sample_name','experimenters'] # required by XPD, time_stub and uid will be automatically added up as well
#fixme: remove sample field just for temporily useage

# These are the default directory paths on the XPD data acquisition computer.  Change if needed here
W_DIR = '/home/xf28id1/xpdUser/tif_base'                # where the user-requested tif's go.  Local drive
R_DIR = '/home/xf28id1/xpdUser/config_base'             # where the xPDFsuite generated config files go.  Local drive
D_DIR = '/home/xf28id1/xpdUser/dark_base'               # where the tifs from dark-field collections go. Local drive
S_DIR = '/home/xf28id1/xpdUser/script_base'             # where the user scripts go. Local drive

#fixme seach !

def _feature_gen(header):
    ''' generate a human readible file name. It is made of time + uid + sample_name + user
    filed will be skipped if it doesn't exist
    '''
    uid = header.start.uid
    time_stub = _timestampstr(header.start.time)

    dummy_list = []
    for key in feature_keys:
        try:
            dummy_list.append(header.start[key])  # feature list elements is at the first level, as it should be
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
 #   i = 0
 #   bound = len(inter_list)
 #   feature = ""
 #   inter_list.reverse()
 #   while i< bound:
 #       feature += str(inter_list.pop())
 #       i += 1
    return feature

def _MD_template():
    ''' use to generate idealized metadata structure, for pictorial memory and
    also for data cleaning.
    '''
    _clean_metadata()
    gs.RE.md['iscalib'] = 0
    gs.RE.md['isdark'] = 0
    gs.RE.md['experimenters'] = []
    gs.RE.md['sample_name'] = ''
    gs.RE.md['calibrant'] = '' # transient, only for calibration set
    gs.RE.md['user_supply'] = {}

    gs.RE.md['sample'] = {}
    gs.RE.md['sample']['composition'] = {}
    
    gs.RE.md['dark_sacn_info'] = {}

    gs.RE.md['scan_info'] = {}
    
    gs.RE.md['calibration_scan_info'] = {}
    gs.RE.md['calibration_scan_info']['calibration_information'] = {}

    return gs.RE.md
    
def sacn_info():
    all_sacn_info = [gs.RE.md.scan_info['exposure_time'],
            gs.RE.md.calibrationscan_info['calibration_exposure_time'],
            gs.RE.md.dark_scan_info['dark_exposure_time']]
    return print('scan exposure time is %s, calibration exposure time is %s, dark scan exposure time is %s' % (all_scan_info[0], all_scan_info[1], all_scan_info[2]))

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

def save_tif(headers, sum_frames = True):
    ''' save images obtained from dataBroker as tiff format files
    
    arguments:
        headers - list of header objects - obtained from a query to dataBroker
        sum_frames - bool - frames will be summed if true
    returns:
        nothing
    '''
    if type(list(headers)[1]) == str:
        header_list = [headers]
    else:
        header_list = headers
  
    # iterate over header(s)
    for header in header_list:
#        dummy = ''
#        dummy_key_list = [e for e in header.start.keys() if e in feature_keys] 
# 
#        for key in dummy_key_list:
#            dummy += str(header.start[key])+'_'      
#        feature = dummy[:-1]
#        uid_val = header.start.uid[:5]
#        time_stub =_timestampstr(header.stop.time)
        feature = _feature_gen(header)
        time_stub = _timestampstr(header.stop.time)
        uid = header.start.uid[:5]
        try: 
            comment = header.start['comments']
        except KeyError:
            pass
        try: 
           cal = header.start['calibration']
        except KeyError:
            pass
        # get images and expo time from headers
        light_imgs = np.array(get_images(header,'pe1_image_lightfield'))
        try:
            cnt_time = header.start.scan_info['scan_exposure_time']
        except KeyError:
            print('scan exposure time in your header can not be found, use default 0.5 secs for dark image correction.')
            cnt_time = 0.5
 
        # Identify the latest dark stack
        '''dummy = [ f for f in os.listdir(D_DIR) ]
        d_list = list()
        for el in dummy:
            d_list.append(os.path.join(D_DIR, el))
        sorted(d_list, key = os.path.getmtime)
        d_last = d_list[-1]
        d_last_uid = dummy[:5]
        #d_last_uid = dark_last[17:22] ... future use if f_name = (time_stub)_uid_feature
        print(d_last_uid)
        d_header = db[d_last_uid]
        '''
        uid_list = []
        f_d = [ f for f in os.listdir(D_DIR) ]
        for f in f_d:
            uid_list.append(f[:5]) # get uids in dark base
        uid_unique = np.unique(uid_list)

        header_list = []
        for d_uid in uid_unique:
            header_list.append(db[d_uid])

        time_list = []
        for header in header_list:
            time_list.append(header.stop.time)

        ind = np.argsort(time_list)
        d_header = header_list[ind[-1]]
        print('use uid = %s dark image scan' % d_header.start.uid)
        try:
            d_cnt_time = d_header.start.dark_scan_info['dark_exposure_time']
        except KeyError:
            print('can not find dark_exposure_time in header of dark images; using default 0.5 seconds now.')
            d_cnt_time = 0.5 # default value
            
        # dark correction
        print('Ploting and savinfg your dark-corrected image(s) now.....')
        d_num = int(np.round(cnt_time / d_cnt_time)) # how many dark frames needed for single light image
        print('Number of dark images applied to correction is %i.' % d_num)
        d_img_list = np.array(get_images(d_header,'pe1_image_lightfield')) # confirmed it comes with reverse order
        d_len = d_img_list.shape[0]
        correct_imgs = []
        for i in range(light_imgs.shape[0]):
            correct_imgs.append(light_imgs[i]-np.sum(d_img_list[d_len-d_num:d_len],0)) # use last few dark images
        if sum_frames:
            f_name = '_'.join([time_stub, uid, feature+'.tif'])
            w_name = os.path.join(W_DIR,f_name)
            img = np.sum(correct_imgs,0)
            fig = plt.figure(f_name)
            plt.imshow(img)
            plt.show()
            imsave(w_name, img) # overwrite mode now !!!!
            if os.path.isfile(w_name):
                print('%s has been saved at %s' % (f_name, W_DIR))
            else:
                print('Sorry, somthing went wrong with your tif saving')
                return
 
        else:
            for i in range(light_imgs.shape[0]):
                f_name = '_'.join([time_stub, uid, feature,'00'+str(i)+'.tif'])
                w_name = os.path.join(W_DIR,f_name)
                img = correct_imgs[i]
                fig = plt.figure(f_name)
                plt.imshow(img)
                plt.show()
                imsave(w_name, img) # overwrite mode now !!!!
                if os.path.isfile(w_name):
                    print('%s has been saved at %s' % (f_name, W_DIR))
                else:
                    print('Sorry, something went wrong with your tif saving')
                    return
        f_name = None



def get_dark_images(num=200, cnt_time=0.2):
    ''' Manually acquire stacks of dark images that will be used for dark subtraction later

    This module runs scans with the shutter closed (dark images) and saves them tagged
    as such.  You shouldn't have to look at these, they will be automatically used later
    for doing dark subtraction when you collect actual images.
    
    The default settings are to collect 5 minutes worth of dark scans in increments
    of 0.5 seconds.  This default behavior can be overriden by providing optional
    values for num (number of frames) and cnt_time.
    
    Arguments:
       num - int - Optional. Number of dark frames to take.  Default = 600
       cnt_time - float - Optional. exposure time for each frame. Default = 0.5 
    '''
    # set up scan
    gs.RE.md['isdark'] = True
    cnt_hold = copy.copy(pe1.acquire_time)
    pe1.acquire_time = cnt_time
    gs.RE.md['dark_scan_info'] = {'dark_exposure_time':cnt_time}   
    
    try:
        # fixme code to check that filter/shutter is closed.  If not, close it.
        ctscan = bluesky.scans.Count([pe1],num)
        ctscan.subs = LiveTable(['pe1_image_lightfield'])
        gs.RE(ctscan)

        gs.RE.md['isdark'] = False
        # delete dark_scan_info 
        pe1.acquire_time = cnt_hold
        # fixme code to to set filter/shutter back to initial state
    except:
        gs.RE.md['isdark'] = False
        # delete dark_scan_info field
        pe1.acquire_time = cnt_hold
        # fixme code to to set filter/shutter back to initial state

    # write images to tif file, only save 3 images in the middle as a hoook and data interogation
    header = db[-1]
    uid = header.start.uid[:5]
    time_stub = _timestampstr(header.stop.time)
    imgs = np.array(get_images(header,'pe1_image_lightfield'))
    #mid = round(num/2)
    for i in range(num-4, num):
        f_name = '_'.join([time_stub, uid, 'dark','00'+str(i)+'.tif'])
        w_name = os.path.join(D_DIR,f_name)
        img = imgs[i]
        imsave(w_name, img) # overwrite mode
        print('%ith images of dark scans have been saved to %s' % (i, W_DIR))
        if not os.path.isfile(w_name):
            print('Error: dark image tif file not written')
            print('Investigate and re-run')
            return

def get_calibration_images (calibrant, wavelength, calibration_scan_exposure_time=0.2 , num=10, composition = False, **kwargs):
    '''Runs a calibration dataset
    
    Arguments:
        calibrant - string - Chemical composition of the calibrant in form LaB6, for example
        wavelength - float - wavelength in nm, which is obtained from verify_wavelength function
        exposure_time - float - count-time in seconds.  Default = 0.2 s
        num - int - number of exposures to take. Default = 10
        **kwargs - dictionary - user specified info about the calibration. Don't use
            this to set global metadata, only use it to add information about the calibration
            It gets stored in the 'calibration_scan_info' dictionary.
    '''    

    # Prepare hold state
    try: 
        composition_hold = copy.copy(gs.RE.md['sample']['composition'])	
        sample_name_hold = copy.copy(gs.RE.md['sample_name'])
    except KeyError:
        composition_hold = {}
        sample_name_hold = '' 
    try:
        gs.RE.md['calibration_information']
    except KeyError:
        gs.RE.md['calibration_information'] = {}
        gs.RE.md['calibration_information']['calibration_scan_info']={}

    cnt_hold = copy.copy(pe1.acquire_time)
    gs.RE.md['iscalibration'] = True
    gs.RE.md['calibrant'] = calibrant
    gs.RE.md['sample_name'] = calibrant
    if not composition:
        gs.RE.md['sample']['composition'] = composition 
        # fixme, in the future, this should be a parsed field: ['phase1':{'Na',1},'phase2':{'Cl':1}]
    else:
        gs.RE.md['sample']['composition'] = composition
    gs.RE.md['calibration_scan_info'] = {'calibration_scan_exposure_time':calibraton_scan_exposure_time,'num_calib_exposures':num,'wavelength':wavelength}
    
    # extra fields, gives user freedom
    extra_key = kwargs.keys()
    for key, value in kwargs.items():
        gs.RE.md['user_supplied'][key] = value
    
    try:
        ctscan = bluesky.scans.Count([pe1], num=num)
        print('collecting calibration data. %s acquisitions of %s s will be collected' % (str(num),str(exposure_time)))
        ctscan.subs = LiveTable(['pe1_image_lightfield'])
        gs.RE(ctscan)

        # recover to previous state, set to values before calibration
        pe1.acquire_time = cnt_hold
        gs.RE.md['iscalibration'] = False
        del(gs.RE.md['calibrant'])
        gs.RE.md['sample']['composition'] = composition_hold
    except KeyError:
        # recover to previous state, set to values before calibration
        pe1.acquire_time = cnt_hold
        gs.RE.md['iscalibration'] = False
        del(gs.RE.md['calibrant'])
        gs.RE.md['sample']['composition'] = composition_hold
        print('scan failed. metadata dictionary reset to starting values.') 
        print('To debug, try running some scans using ctscan=bluesky.scans.Count([pe1])')
        print('then gs.RE(ctscan).  When it is working, rerun get_calibration_images()')
        return
    
    # construct calibration tif file name
    header = db[-1]
    time_stub = _timestampstr(header.stop.time)
    uid = header.start.uid[:5]
    f_name = '_'.join(['calib', time_stub, uid, calibrant+'.tif'])
    w_name = os.path.join(W_DIR, f_name)

    # sum images together and save
    imgs = np.array(get_images(header,'pe1_image_lightfield'))
    
    multiple_images = False
    if imgs.ndim ==3: multiple_images = True
    
    if multiple_images:
        img = np.sum(imgs,0)
    else:
        img = imgs     
    imsave(w_name, img)
    
    # confirm the write took place
    if os.path.isfile(w_name):
        print('A summed image %s has been saved to %s' % (f_name, W_DIR))
   
def get_light_images(scan_time=1.0, scan_exposure_time=0.5, scan_def=False, comments={}):
    '''function for getting a light image
    
    Arguments:
        scan_time - float - optional. data collection time for the scan. Default = 1.0 seconds
        exposure_time - float - optional. exposure time per frame.  number of exposures will be
            computed as int(scan_time/exposure_time)
        scan_def - bluesky scan object - optional. user can specify their own scan and pass it 
            to the function.  Not specified in normal usage.
        comments - dictionary - optional. dictionary of user defined key:value pairs.
    '''
    
    if comments:
        extra_key = comments.keys()
        for key, value in comments.items():
            gs.RE.md['user_supplied'][key] = value
    
    # don't expose the PE for more than 5 seconds max, set it to 1 seconds if you go beyond limit
    if scan_exposure_time > 5.0:
        exposure_time = 1.0
        num = int(scan_time/exposure_time)
    else:
        num = int(scan_time/exposure_time)

    if num == 0: num = 1 # at least one scan
    
    if not scan_def:
        scan = bluesky.scans.Count([pe1],num)
    else:
        scan = scan_def
    
    pe1.acquisition_time = scan_exposure_time

    try:
        gs.RE.md['sample']['temp']
        gs.RE.md['scan_info']['scan_exposure_time']
    except KeyError:
        gs.RE.md['sample'] = {}
        gs.RE.md['scan_info'] = {}
        gs.RE.md['sample']['temp'] = cs700.value[1]  # fixme: temporaily use
        gs.RE.md['scan_info']['scan_exposure_time'] = scan_exposure_time
        gs.RE.md['scan_info']['number_of_exposures'] = num
        gs.RE.md['scan_info']['total_scan_duration'] = num*exposure_time
        #gs.RE.md['scan_info']['detector'] = pe1  # pe1 is not a simple object, call it directly causes I/O Error
    
    try:
        # fixme: code to check the filter/shutter is open
        scan.subs = LiveTable(['pe1_image_lightfield'])
        gs.RE(scan)
        save_tiff(db[-1])
        print('Dark corrected images have been saved to %s' % W_DIR)
        # note, do not close the shutter again afterwards, we will do it manually outside of this function
		    
        # deconstruct the metadata
        gs.RE.md['scan_info'] = {} # give it a blank dictionary for rubustness
        gs.RE.md['user_supplied'] = {}
        gs.RE.md['sample']['temp'] = 0

    except:
        # deconstruct the metadata
        gs.RE.md['scan_info'] = {} # give it a blank dictionary for rubustness
        gs.RE.md['user_supplied'] = {}
        gs.RE.md['sample']['temp'] = 0
        print('image collection failed. Check why gs.RE(scan) is not working and rerun')
        return
    
def load_calibration(config_file = False, config_dir = False):
    '''Function loads calibration values as metadata to save with scans
    
    takes calibration values from a SrXplanar config file and 
    loads them in the Bluesky global state run engine metadata dictionary. 
    They will all automatically be saved with every run. 
    
    An example workflow is the following:
    1) get_calibration_images('Ni',wavelength=0.1234)
    2) open xPDFsuite and run the calibration in the SrXplanar module (green button
           in xPDFsuite).  See SrXplanar help documentation for more info.
    3) write the calibration data to an xPDFsuite config file in config_base directory
    
    Arguments:
    config_file -str - optional. name of your desired config file. If unspecified, the most recent one will be used
    config_dir - str - optional. directory where your config files are located. If unspecified, default directory is used
    normal usage is not to use change these defaults.
    '''

    if not config_dir:
        rear_dir = R_DIR
    else:
        rear_dir = str(config_dir)
    
    if not config_file: 
        # reading most recent config file in the rear_dir 
        f_list = [ f for f in os.listdir(rear_dir) if f.endswith('.cfg')]
        f_dummy = []
        for f in f_list:
            f_dummy.append(os.path.join(rear_dir,f))
        f_sort = sorted(f_dummy, key = os.path.getmtime)
        f_recent = f_sort[-1]
        f_recent_time = os.path.getmtime(f_recent)
        config_file_stub = str(f_recent)
        f_name = os.path.join(rear_dir,config_file_stub)
        if len(f_sort) >0:
            print('Using '+ f_name +', the most recent config file that was found in ' +rear_dir )
        else:
            print('There is no ".cfg" file in '+rear_dir)
            print('make sure the config file has been written in that directory and has extension ".cfg"')
    else:
        f_name = os.path.join(rear_dir,config_file)
        if os.path.isfile(f_name):
            print('Using user-supplied config file: '+config_file+' located in'+rear_dir)
        else:
            print('Your config file '+config_file+' is not found. Please check again your directory and file name')
            return
    
    # read config file into a dirctionary
    config = ConfigParser()
    config.read(f_name)
    sections = config.sections()

    config_dict = {}
    for section in sections:
        options = config.options(section)
        for option in options:
            try:
                config_dict[option] = config.get(section, option)
                #if config_dict[option] == -1:
                #    DebugPrint("skip: %s" % option)
            except:
                print("exception on %s!" % option)
                config_dict[option] = None
    gs.RE.md['calibration_information'] = {'from_calibration_file':str(config_file),'calib_file_creation_date':f_recent_time,
            'config_data':config_dict}
    
    print('Calibration metadata will be saved in dictionary "calibration_information" with subsequent scans. type gs.RE.md to check.')
    print('Run load_calibration() again on a different config file to update')
    
def new_user(user_list):
    ''' This function sets up experimenter name(s). This function can be run at anytime to change experimenter global setting
    Argument:
        user_list - str or list - name of current experimenters
    '''
    gs.RE.md['experimenters'] = user_list


def new_sample(sample, experimenters=[], comments={}, verbose = 1):
    '''configure metadata field for your runengine
    
    This function sets up persistent metadata that will be saved with subsequent scans, 
    including a list of experimenters and the sample composition, as well as other user
    defined comments.  It can be rerun multiple times until you are happy with the settings,
    then these settings will be applied to scan metadata when the scans are run later.
    
    Arguments:

    user - str or list - current user name(s), if it is not specified, current value will be used
    sample - str or list - current sample
    comments - str - comments to current experiment
    *kargs - str - any fields you want to update in metadata dictionary
    sample - str - current sample
    experimenters - list - optional. list of current experimenter(s). reuse current value if not given
    comments - dict - optional. user supplied comments that relate to the current sample. Default = ''
    verbose - bool - optional. set to false to suppress printed output.
    ''' 
    if verbose: print('Setting up global run engines(gs.RE) with your metadata.......')
    gs.RE.md['sample']['composition'] = sample    
    if not experimenters:
        experimenters = gs.RE.md['experimenters']
        print('current experimenters is/are '+experimenters)
        print('to change experimenters, rerun new_sample giving a list of experimenters as an argument')    
    
    time_form = str(datetime.datetime.fromtimestamp(time.time()))
    date = time_form[:10]
    hour = time_form[11:16]
    timestampstring = '_'.join([date, hour]) #fixme, get timestamp from central clock through bluesky
    gs.RE.md['sample_load_time'] = timestampstring
    gs.RE.md['sample']['comments'] = comments

    if verbose: print('Sample and experimenter metadata set')
    if verbose: print('To check what will be saved with your scans, type "gs.RE.md"')

#### block of search functions ####
def get_fuzzy_key(key, d=gs.RE.md):
    ''' Help user to do fuzzy search on key names contains in a nested
    dictionary. Return all possible key names starting with a fuzzy key name
    
    Arguments:
    key - str - possible key name, can be partial like 'exp', 'sca' or nearly complete like 'experiment'
    d - dict - dictionary you want searched for. Default is set to current metadata dictionary
    '''
    if hasattr(d,'items'):
        rv = [f for f in d.keys() if f.startswith(key)]
        print('Possible key(s) to your search is %s' % rv)
        print('Please identify your desired result and use build_keychain_list() function to generate complete keychian map to nested metadata dictionary')
        return rv
        fuzzy_key(key, d.values())

def get_keychain(wanted_key, d = gs.RE.md):
    ''' Return keychian(s) of specific key(s) in a nested dictionary
    
    argumets:
    wanted_key - str - name of key you want to search for
    d - dict - dictionary you want searched for. Default is set to current metadata dictionary
    '''
    for k, v in d.items():
        if isinstance(v, dict):
            result = get_keychain(wanted_key, v) # dig in nested element
            if result:
                return [k]+p
        elif k == wanted_key:
            return [k]


def build_keychain_list(key_list, d = gs.RE.md):
    ''' Return a list that yields correct path(s) to nested dictionary. String elements are ready to be used in and_search() function.
    
    argumets:
    key_list - str or list - name of key(s) you want to search for
    d - dict - dictionary you want searched for. Default is set to current metadata dictionary

    '''
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
                dummy.remove(key)
                path = '.'.join(dummy)
                result.append(path)
            elif len(dummy) == 1:
                path = dummy[0]
                result.append(path)
        else:
            path = key
            result.append(path)
        print('keychain to your desired key %s is %s' % (key, path))
    return result
    
def and_search(**kwargs):
    '''generate mongoDB recongnizable query of "and_search" and rerutn headers
    
    Arguments:
    - kwargs - dict - dictionary of your search. It is made up of key pairs like {'key': 'value'}
      Please use keychain_list to have correct keychain to desired keys and then access them through slicing.
      E.g.:
      mykeychain = keychain_list(gs.RE.md, ['experimenters', isdark'])
      header = and_search(**{mykeychain[0]:'Tim', mykeychain[1]:False})
    '''
    
    dict_gen = {}
    
    for key, value in kwargs.items():
        dict_gen[key] = value

    and_header = db(**dict_gen)
    and_out = get_events(and_header, fill=False)
    and_out = list(and_out)
    print('||Your search gives out '+str(len(and_header))+' headers||')
    
    return and_header
    
def table_gen(headers):
    ''' Takes in a header list generated by search functions and return a table
    with metadata information
    
    Argument:
    headers - list - a header list generated by and_search function or
    general databroker search function
    
    '''
    plt_list = []
    cal_list = []
    feature_list = []
    comment_list = []
    uid_list = []

    if type(list(headers)[1]) == str:
        header_list = [headers]
    else:
        header_list = headers

    for header in header_list:
        #dummy = ''
        #dummy_key_list = [e for e in header.start.keys() if e in feature_list] # stroe list independently
        feature = _feature_gen(header)
        time_stub = _timestampstr(header.start.time)
        uid = header.start.uid
        uid_list.append(uid[:5])
        #for key in dummy_key_list:
            #dummy += str(header.start[key])+'_'
        f_name = "_".join(time_stub, feature)
        feature_list.append(f_name)
	    
        try:
            comment_list.append(header.start['comments'])
        except KeyError:
            commet_list.append('None')
        #try:
            #cal_list.append(header.start['calibration'])
        #except KeyError:
            #pass
        try:
            uid_list.append(header.start['uid'])
        except KeyError:
            pass
    plt_list = [feature_list, comment_list, uid_list] # u_id for ultimate search
    inter_tab = pd.DataFrame(plt_list)
    tab = inter_tab.transpose()
    tab.columns=['Features', 'Comments', 'u_id']
    
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
    print('||Your search gives out '+str(len(event_time))+' results||')
          
    return header_time


def sanity_check(user_in=None):
    user = gs.RE.md['experimenters']
    compo = gs.RE.md['sample']['composition']
    calib_file = gs.RE.md['calibration_information']['from_calibration_file']
    
    print('Hey '+user+' ,current sample is: '+compo+', calibration file is using: '+calib+', time is: '+time)
    uin= input('Is it correct? y/n')
    if uin == 'y':
        print('Great, lets start')
    elif uin == 'n':
        print('Please correct your setting or make sure that is your experiment')
    else:
        return

''' Don't use it, it is slow and potentially dangerous to local work stations
when saving a lot of tif files.
def prompt_save(name,doc):
    if name == 'stop':
        header = db[doc['uid']] # fixme: how to do doc.uid ????
        #dummy = ''
        #dummy_key_list = [f for f in header.start.keys() if f in feature_list] # stroe it independently
            
        #for key in dummy_key_list:
        #    dummy += str(header.start[key])+'_'

        #feature = dummy[:-1]
        feature = _feature_gen(header)
        
        # prepare timestamp, uid
        time_stub = _timestampstr(header.stop.time)
        uid = header.stop.uid[:5]
        imgs = get_images(header,'pe1_image_lightfield')
        
        for i in range(imgs.shape[0]):
            f_name = '_'.join([time_stub, uid, feature,'00'+str(i)+'.tif'])
            w_name = os.path.join(backup_dir,f_name)
            img = imgs[i]
            imsave(w_name, img) # overwrite mode !!!!
            if os.path.isfile(w_name):
                print('%s has been saved at %s' % (f_name, backup_dir))
            else:
                print('Sorry, something went wrong with your tif saving')
                return
'''
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
    extra_key_list = [ f for f in gs.RE.md.keys() if f not in default_keys]
    for key in extra_key_list:
        del(gs.RE.md[key])
    gs.RE.md['sample'] = {}


# Holding place
    #print(str(check_output(['ls', '-1t', '|', 'head', '-n', '10'], shell=True)).replace('\\n', '\n'))
    #gs.RE.md.past({'field':'value'})
#    if not sample_temperature:
#        temp = cs700.value[1]


