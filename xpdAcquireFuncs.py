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

#import localimports

#pd.set_option('max_colwidth',70)
pd.set_option('colheader_justify','left')

default_keys = ['owner', 'beamline_id', 'group', 'config', 'scan_id'] # required by dataBroker
feature_keys = ['composition', 'temperature', 'experimenter_name'] # required by XPD

# These are the default directory paths on the XPD data acquisition computer.  Change if needed here
W_DIR = '/home/xf28id1/xpdUser/tif_base'                # where the user-requested tif's go.  Local drive
R_DIR = '/home/xf28id1/xpdUser/config_base'             # where the xPDFsuite generated config files go.  Local drive
D_DIR = '/home/xf28id1/xpdUser/dark_base'               # where the tifs from dark-field collections go. Local drive

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

def save_tiff(headers, summing = True):
    ''' save images obtained from dataBroker as tiff format files
    
    arguments:
        header_list - list of header objects - obtained from a query to dataBroker
        summing - bool - frames will be summed if true
    returns:
        nothing
    '''
    # fixme check header_list is a list
    # if not, make header_list into a list with one element, then proceed
    # fixme this is much better than copy-pasting lines and lines of code.
    if type(headers) == list:
        header_list = headers
    else:
        header_list = list(headers)
 
    # iterate over header(s)
    for header in header_list:
        dummy = ''
        dummy_key_list = [e for e in header.start.keys() if e in feature_keys] # stroe a list independently

	for key in dummy_key_list:
            dummy += str(header.start[key])+'_'      
        feature = dummy[:-1]
        uid_val = header.start.uid[:6]
        try: 
            comment = header.start['comments']
        except KeyError:
            pass
        try: 
            cal = header.start['calibration']
        except KeyError:
            pass
        time= str(datetime.datetime.fromtimestamp(header.stop.time))
        date = time[:10]
        hour = time[11:16]
        timestamp = '_'.join([date, hour])
            
        # get images and expo time from headers
        imgs = np.array(get_images(header,'pe1_image_lightfield'))
        cnt_time = header.start.acquire_time

        # Identify the latest dark stack
        f_d = [ f for f in os.listdir(D_DIR) ]
        f_dummy = []
        for f in f_d:
            f_dummy.append(os.path.join(D_DIR,f))
        f_sort = sorted(f_dummy, key = os.path.getmtime)
             
        # get uid and look up cnt_time of target dark image
        d_uid = f_sort[-1][:5]
        d_cnt = db['d_uid'].start.dark_scan_info.dark_exposure_time
            
            
        # dark correction
        d_num = int(np.round(cnt_time / d_cnt))
        d_img_list = np.array(get_images(db['d_uid'],'pe1_image_lightfield')) # fixme: need to see if this list comes with reverse order

        correct_imgs = []
        for i in range(imgs.shape[0]):
            correct_imgs.append(imgs[i]-np.sum(d_img_list[:d_num],0)
             
        if summing == True:
            f_name = '_'.join([uid_val, timestamp, feature+'.tif'])
            w_name = os.path.join(W_DIR,f_name)
            img = np.sum(correct_imgs,0)
            imsave(w_name, img) # overwrite mode now !!!!
            if os.path.isfile(w_name):
                print('%s has been saved at %s' % (f_name, W_DIR))
            else:
                print('Sorry, somthing went wrong with your tif saving')
                return

        elif summing == False:
            for i in range(correct_imgs.shape[0]):
                f_name = '_'.join([uid_val, timestamp, feature,'00'+str(i)+'.tif'])
                w_name = os.path.join(W_DIR,f_name)
                img = correct_imgs[i]
                imsave(w_name, img) # overwrite mode now !!!!
                if os.path.isfile(w_name):
                    print('%s has been saved at %s' % (f_name, W_DIR))
                else:
                    print('Sorry, something went wrong with your tif saving')
                return


def run_calibration(sample, wavelength, exp_time=0.2 , num=10, **kwargs):
    '''Runs a calibration dataset
    
    Arguments:
        sample - string - Chemical composition of the calibrant in form LaB6, for example
        wavelength - float - wavelength in nm, which is obtained from verify_wavelength function
        exp_time - float - count-time in seconds.  Default = 0.2 s
        num - int - number of counts. Default = 10
    '''
    # store initial info
    hold_dict = {}
    hold_list = ['acquisition_time','composition', 'num_calib_exposures']
    for field in hold_list:
        hold_dict[field] = gs.RE.md[field]
 
    # set up calibration information
    gs.RE.md['comments'] = 'calibration'
    gs.RE.md['calibrant'] = sample
    gs.RE.md['composition'] = sample
    gs.RE.md['wavelength'] = wavelength
    gs.RE.md['acquisition_time'] = exp_time
    gs.RE.md['num_calib_exposures'] = num 

    # extra field define whatever you want
    extra_key = kwargs.keys()
    for key, value in kwargs.items():
        gs.RE.md[key] = value
    
    # define a scan
    pe1.acquire_time = 0.2
    ctscan = bluesky.scans.Count([pe1], num=num)
    print('collecting calibration data. '+str(num)+' acquisitions of '+str(exp_time)+' s will be collected')
    ctscan.subs = LiveTable(['pe1_image_lightfield'])
    gs.RE(ctscan)

    # recover to previous state, set to values before calibration
    for key in extra_key:
        gs.RE.md[key] = ''
        # del(gs.RE.md[key]) # alternative: delete it    
    gs.RE.md['comments'] = ''
    gs.RE.md['calibrant'] = ''
    for key, value in hold_list.items():
        gs.RE.md[key] = value

    # add a short time-stamp to the tiff filename
    header = db[-1]
    time= str(datetime.datetime.fromtimestamp(header.stop.time))
    date = time[:10]
    hour = time[11:16]
    timestamp = '_'.join([date, hour])
    uid = header.start.uid[:6]

    # sum images together before saving
    imgs = np.array(get_images(header,'pe1_image_lightfield'))
    if imgs.ndim ==3:
        img = np.sum(imgs,0)
    f_name = '_'.join(['calib', uid, timestamp, sample,'.tif'])
    w_name = os.path.join(W_DIR, f_name)
    imsave(w_name, img)
    if os.path.isfile(w_name):
        print('A summed image %s has been saved to %s' % (f_name, W_DIR))
    #print(str(check_output(['ls', '-1t', '|', 'head', '-n', '10'], shell=True)).replace('\\n', '\n'))
   

def load_calibration(config_file = False, config_dir = False):
    '''Function loads calibration values as BlueSky metadata
    
    takes calibration values from a SrXplanar config file and 
    loads them in the Bluesky global state run engine metadata dictionary. 
    They will all automatically be saved.  
    
    An example workflow is the following:
    1) run_calibration('Ni',wavelength=0.1234)
    2) open xPDFsuite and run the calibration in the SrXplanar module (green button
           in xPDFsuite).  See SrXplanar help documentation for more info.
    
    Arguments:
    config_file - str - name of your desired config file. If unspecified, most recent one will be used
    config_dir - str - directory where your config files located at. If unspecified, default directory is used
    '''

    ###### setting up directory #######
    if not config_dir:
        rear_dir = R_DIR
    else:
        rear_dir = str(config_dir)
    
    
    
    if not config_file: 
    # reading most recent config file in the rear_dir  ########
        f_list = [ f for f in os.listdir(rear_dir) if f.endswith('.cfg')]
    
        f_dummy = []
        for f in f_list:
            f_dummy.append(os.path.join(rear_dir,f))

        f_sort = sorted(f_dummy, key = os.path.getmtime)
        f_last = str(f_sort[-1])
        config_file = f_last
        f_name = os.path.join(rear_dir,config_file)
        if len(config_file) >0:
            print('Using '+ f_name +', the most recent config file that was found in ' +rear_dir )
        else:
            print('There is no file in '+ rear_dir)
    else:
        f_name = os.path.join(rear_dir,config_file)
        
        if os.path.isfile(f_name):
            print('Using user-supplied config file: '+config_file+' located at'+ rear_dir)
        else:
            print('Your config file ' + config_file +' is not found. Please check again your directory and file name')
            return
    
    ###### read config file into a dirctionary ######
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
    
    gs.RE.md['config'] = config_dict
    gs.RE.md['calibration'] = str(config_file)
    
    print('Calibration metadata has been successfully save as a dictionary in config field; use gs.RE.md to check.')
    print('Subsequent scans will carry the calibration data in their metadata stores until load_calibration() is run again.')
    

def config_md(user=False, sample, comments=False, temperature = False, **kwargs):
    '''configure metadata field for your runengine
    
    Arguments:
    name - str or list - current user name(s)
    sample - str or list - current sample
    comments - str - comments to current experiment
    *kargs - str - any fields you want to update in metadata dictionary
    '''
    if not temperature:
        temp = str(cs700.value[1])+'K'
    else:
        temp = str(temperature) # user defined value
    if type(sample) == str:
       #fixme : parsing elements
    
    # write metadata diectionray
    gs.RE.md['experimenter_name'] = user
    gs.RE.md['composition'] = sample
    gs.RE.md['temperature'] = temp
    gs.RE.md['date'] = str(datetime.datetime.today().date())
    
    if not Comments:
        gs.RE.md['comments'] = ''
    else:    
        gs.RE.md['comments'] = Comments
    
    # user define keys
    for key, value in kwargs.items():
        gs.RE.md[key] = value

    print('Your metadata dictionary is %s' % gs.RE.md)
    time.sleep(0.5)
    print('Setting up global run engines(gs.RE) with your metadata.......')
    time.sleep(0.5)
    print('global runengine states have been updated')
    print('Initialization finished.')
    
def and_search(**kwargs):
    '''generate mongoDB recongnizable query of "and_search" and rerutn data
    
    Arguments:
        -fields : fields you want to search on. For example, metadata stored in sample.<metadata>" or standard
        field like "start_time". Make sure you know where is the field-value pair exactly located at.
        
        -values : values you are looking for. For example, "NaCl" or "300k". Make sure you know where is the field-value pair 
        exactly located at.
        
        Note: Please type in fields and corresponding values of desired search with exact order
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
    ''' Takes in a header list generated by search functions and return a talbe
    with metadata information
    
    Argument:
    header_list - list - a header list generated by and_search function or
    general databroker search function
    
    '''
    plt_list = []
    cal_list = []
    feature_list = []
    comment_list = []
    uid_list = []

    if type(headers) == list:
        header_list = header_list
    else:
        header_list = list(headers)

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
    
#    time_query = {'start_time':timeHead, 'stop_time':timeTail}
#    time_search = db(**time_query)
#    time_out = get_events(time_search, fill=False)
#    time_out = list(time_out)
    print('||You assign a time search in the period:\n'+str(timeHead)+' and '+str(timeTail)+'||' )
    print('||Your search gives out '+str(len(event_time))+' results||')
          
    return header_time


def sanity_check(user_in=None):
    user = gs.RE.md['experimenter_name']
    compo = gs.RE.md['composition']
    calib = gs.RE.md['calibration']
    time = str(datetime.datetime.now())
    
    print('Hey '+user+' ,current sample is: '+compo+', calibration file is using: '+calib+', time is: '+time)
    uin= input('Is it correct? y/n')
    if uin == 'y':
        print('Great, lets start')
    elif uin == 'n':
        print('Please correct your setting or make sure that is your experiment')
    else:
        return

def prompt_save(name):
    if name == 'stop':
        header = db[-1]
        dummy = ''
        dummy_key_list = [f for f in header.start.keys() if f in feature_list] # stroe it independently
            
        for key in dummy_key_list:
            dummy += str(header.start[key])+'_'
                
        feature = dummy[:-1]
        
        # prepare timestamp, uid
        time= str(datetime.datetime.fromtimestamp(header.stop.time))
        date = time[:10]
        hour = time[11:16]
        timestamp = '_'.join([date, hour])
        uid = header.stop.uid[:5]

        file_name = '_'.join([uid, timestamp, feature])
        imgs = get_images(header,'pe1_image_lightfield')
        for i in range(imgs.shape[0]):
            f_name = '_'.join([uid, timestamp, feature,'00'+str(i)+'.tif'])
            w_name = os.path.join(backup_dir,f_name)
            img = imgs[i]
            imsave(w_name, img) # overwrite mode now !!!!
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
        # ctscan.subs = LiveTable(['pe1'])
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

