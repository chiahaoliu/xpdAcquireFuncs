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
feature_keys = ['composition', 'experimenter_name'] # required by XPD

# These are the default directory paths on the XPD data acquisition computer.  Change if needed here
W_DIR = '/home/xf28id1/xpdUser/tif_base'                # where the user-requested tif's go.  Local drive
R_DIR = '/home/xf28id1/xpdUser/config_base'             # where the xPDFsuite generated config files go.  Local drive
D_DIR = '/home/xf28id1/xpdUser/dark_base'               # where the tifs from dark-field collections go. Local drive

#fixme seach !

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

def save_tiff(headers, sum_frames = True):
    ''' save images obtained from dataBroker as tiff format files
    
    arguments:
        headers - list of header objects - obtained from a query to dataBroker
        sum_frames - bool - frames will be summed if true
    returns:
        nothing
    '''
    # fixme check header_list is a list
    # if not, make header_list into a list with one element, then proceed
    # fixme this is much better than copy-pasting lines and lines of code.
    if type(list(headers)[1]) == str:
        header_list = [headers]
    else:
        header_list = headers
  
    # iterate over header(s)
    for header in headers:
        dummy = ''
        dummy_key_list = [e for e in header.start.keys() if e in feature_keys] 
 
        for key in dummy_key_list:
            dummy += str(header.start[key])+'_'      
        feature = dummy[:-1]
        uid_val = header.start.uid[:5]
        try: 
            comment = header.start['comments']
        except KeyError:
            pass
        try: 
           cal = header.start['calibration']
        except KeyError:
            pass
        time_stub =_timestampstr(header.stop.time)

        # get images and expo time from headers
        imgs = np.array(get_images(header,'pe1_image_lightfield'))
        cnt_time = header.start.scan_info.exposure_time
 
        # Identify the latest dark stack
        f_d = [ f for f in os.listdir(D_DIR) ]
        uid_list = []
        for f in f_d:
            uid_list.append(f[:5]) # get uids in dark base
        uid_unique = np.unique(uid_list)

        header_list = []
        for uid in uid_list:
            header_list.append(db[uid])

        time_list = []
        for header in header_list:
            time_list.append(header.stop.time)

        ind = np.argsort(time_list)
        d_header = header_list[ind[-1]]
        d_cnt = d_header.start.dark_scan_info.dark_exposure_time
            
        # dark correction
        cnt_time = header.start.scan_info['exposure_time']
        d_num = int(np.round(cnt_time / d_cnt))
        d_img_list = np.array(get_images(d_header,'pe1_image_lightfield')) # confirmed it comes with reverse order
        correct_imgs = []
        for i in range(imgs.shape[0]):
            correct_imgs.append(imgs[i]-np.sum(d_img_list[d_num:],0)) # use the last ones
        if sum_frames == True:
            f_name = '_'.join([uid_val, time_stub, feature+'.tif'])
            w_name = os.path.join(W_DIR,f_name)
            img = np.sum(correct_imgs,0)
            imsave(w_name, img) # overwrite mode now !!!!
            if os.path.isfile(w_name):
                print('%s has been saved at %s' % (f_name, W_DIR))
            else:
                print('Sorry, somthing went wrong with your tif saving')
                return
 
        elif sum_frames == False:
            for i in range(correct_imgs.shape[0]):
                f_name = '_'.join([uid_val, time_stub, feature,'00'+str(i)+'.tif'])
                w_name = os.path.join(W_DIR,f_name)
                img = correct_imgs[i]
                imsave(w_name, img) # overwrite mode now !!!!
                if os.path.isfile(w_name):
                    print('%s has been saved at %s' % (f_name, W_DIR))
                else:
                    print('Sorry, something went wrong with your tif saving')
                    return



def get_dark_images(num=600, cnt_time=0.5):
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
    mid = round(num/2)
    for i in range(mid:mid+4):
        f_name = '_'.join([uid, time_stub, 'dark','00'+str(i)+'.tif'])
        w_name = os.path.join(D_DIR,f_name)
        img = imgs[i]
        imsave(w_name, img) # overwrite mode 
        if not os.path.isfile(w_name):
            print('Error: dark image tif file not written')
            print('Investigate and re-run')
            return

def get_calibration_images(sample, wavelength, exposure_time=0.2 , num=10, **kwargs):
    '''Runs a calibration dataset
    
    Arguments:
        sample - string - Chemical composition of the calibrant in form LaB6, for example
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
        sample_hold = copy.copy(gs.RE.md['sample'])    
    except KeyError:
        composition_hold = ""
        sample_hold = ""
    cnt_hold = copy.copy(pe1.acqure_time)


    gs.RE.md['iscalibration'] = True
    gs.RE.md['calibrant'] = sample
    gs.RE.md['sample'] = sample
    gs.RE.md['sample']['composition'] = sampple # fixme, in the future, this should be a parsed field: ['phase1':{'Na',1},'phase2':{'Cl':1}]
    gs.RE.md['calibration_information']['calibration_scan_info'] = {'acquisition_time':exposure_time,'num_calib_exposures':num,'wavelength':wavelength}
    
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
        gs.RE.md['composition'] = composition_hold
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
    uid_stub = header.start.uid[:6]
    f_name = '_'.join(['calib', uid_stub, time_stub, sample+'.tif'])
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
   
def get_light_image(scan_time=1.0, exposure_time=0.5, scan_def=False, comments={}):
    '''function for getting a light image
    
    Arguments:
        scan_time - float - optional. data collection time for the scan. Default = 1.0 seconds
        exposure_time - float - optional. exposure time per frame.  number of exposures will be
            computed as int(scan_time/exposure_time)
        scan_def - bluesky scan object - optional. user can specify their own scan and pass it 
            to the function.  Not specified in normal usage.
        comments - dictionary - optional. dictionary of user defined key:value pairs.
    '''
    
    if not scan_def:
        scan = bluesky.scans.Count([pe1],num)
    else:
        scan = scan_def
    
    if comments:
        extra_key = comments.keys()
        for key, value in comments.items():
            gs.RE.md['user_supplied'][key] = value
    
    # don't expose the PE for more than 5 seconds max, set it to 1 seconds if you go beyond limit
    if exposure_time > 5.0:
        #exposures = int(exposure_time)
        exposure_time = 1.0
        num = int(scan_time/exposure_time) # should we find new exposure time?
    else:
	num = int(scan_time/exposure_time)

    if num == 0: num = 1 # at least one scan

    pe1.acquisition_time = exposure_time

    try:
        gs.RE.md['sample']['temp']
        gs.RE.md['scan_info']['exposure_time']
    except KeyError:
        gs.RE.md['sample'] = {}
        gs.RE.md['scan_info'] = {}
        gs.RE.md['sample']['temp'] = cs700.value[1]
        gs.RE.md['scan_info']['exposure_time'] = exposure_time
        gs.RE.md['scan_info']['number_of_exposures'] = num
        gs.RE.md['scan_info']['total_scan_duration'] = num*exposure_time
        #gs.RE.md['scan_info']['detector'] = pe1  # pe1 is not a simple object, call it directly causes I/O Error
    
    try:
        # fixme: code to check the filter/shutter is open
        gs.RE(scan)
        save_tiff(db[-1])
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
    gs.RE.md['experimenter'] = user_list


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
    
    gs.RE.md['sample_load_time'] = str(datetime.datetime.today().date().time()) #fixme, get timestamp from central clock through bluesky
    gs.RE.md['sample']['comments'] = comments

    if verbose: print('Sample and experimenter metadata set')
    if verbose: print('To check what will be saved with your scans, type "gs.RE.md"')

    
def and_search(**kwargs):
    '''generate mongoDB recongnizable query of "and_search" and rerutn data
    
    Arguments:
        -fields : fields you want to search on. For example, metadata stored in sample.<metadata>" or standard
        field like "start_time". Make sure you know where is the field-value pair exactly located at.
        
        -values : values you are looking for. For example, "NaCl" or "300k". Make sure you know where is the field-value pair 
        exactly located at.
        
        Note: Please type in fields and corresponding values of desired search with exact order

    Returns:
        list of bluesky header objects
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
        dummy = ''
        dummy_key_list = [e for e in header.start.keys() if e in feature_list] # stroe list independently

        time= str(datetime.datetime.fromtimestamp(header.stop.time))
        date = time[:10]
        hour = time[11:16]
        timestamp = '_'.join([date, hour])

        for key in dummy_key_list:
            dummy += str(header.start[key])+'_'      
        feature_list.append(timestamp + dummy[:-1])
	    
        try:
            comment_list.append(header.start['comments'])
        except KeyError:
            pass
        try:
            cal_list.append(header.start['calibration'])
        except KeyError:
            pass
        try:
            uid_list.append(header.start['calibration'])
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
          :/  d0 = exp_day1
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
    user = gs.RE.md['experimenter_name']
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

def prompt_save(name,doc):
    if name == 'stop':
        header = db[doc['uid']] # fixme: how to do doc.uid ????
        dummy = ''
        dummy_key_list = [f for f in header.start.keys() if f in feature_list] # stroe it independently
            
        for key in dummy_key_list:
            dummy += str(header.start[key])+'_'

        feature = dummy[:-1]
        
        # prepare timestamp, uid
        time_stub = _timestampstr(header.stop.time)
        uid = header.stop.uid[:5]
        imgs = get_images(header,'pe1_image_lightfield')
        
        for i in range(imgs.shape[0]):
            f_name = '_'.join([uid, timestamp, feature,'00'+str(i)+'.tif'])
            w_name = os.path.join(backup_dir,f_name)
            img = imgs[i]
            imsave(w_name, img) # overwrite mode !!!!
            if os.path.isfile(w_name):
                print('%s has been saved at %s' % (f_name, backup_dir))
            else:
                print('Sorry, something went wrong with your tif saving')
                return

def get_dark_images(num=600, cnt_time=0.5):
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
    gs.RE.md['dark_scan_info'] = {'dark_exposure_time':cnt_time}   
    cnt_hold = copy.copy(pe1.acquire_time)
    pe1.acquire_time = cnt_time
    
    try:
        ctscan = bluesky.scans.Count([pe1],num)
        # ctscan.subs = LiveTable([pe1])
        gs.RE(ctscan)

        gs.RE.md['isdark'] = False
        # delete dark_scan_info 
        pe1.acquire_time = cnt_hold
    except:
        gs.RE.md['isdark'] = False
        # delete dark_scan_info field
        pe1.acquire_time = cnt_hold
        
    # write images to tif file
    header = db[-1]
    uid = header.start.uid[:5]
    timestamp = str(datetime.datetime.fromtimestamp(header.start.time))
    imgs = np.array(get_images(header,'pe1_image_lightfield'))
    for i in range(imgs.shape[0]):
        f_name = '_'.join([uid, timestamp, 'dark','00'+str(i)+'.tif'])
        w_name = os.path.join(D_DIR,f_name)
        img = imgs[i]
        imsave(w_name, img) # overwrite mode 
        if not os.path.isfile(w_name):
            print('Error: dark image tif file not written')
            print('Investigate and re-run')
            return

def _timestampstr(timestamp):
    time= str(datetime.datetime.fromtimestamp(timestamp))
    date = time[:10]
    hour = time[11:16]
    timestampstring = '_'.join([date, hour])
    return timestampstring

# Holding place
    #print(str(check_output(['ls', '-1t', '|', 'head', '-n', '10'], shell=True)).replace('\\n', '\n'))
    #gs.RE.md.past({'field':'value'})
#    if not sample_temperature:
#        temp = cs700.value[1]


