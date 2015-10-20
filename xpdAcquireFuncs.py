import os
import sys
import time
import datetime
import numpy as np
import pandas as pd
import matplotlib as ml
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from configparser import ConfigParser

import bluesky.scans
from bluesky.global_state import gs
from bluesky.examples import motor, det
from bluesky.run_engine import RunEngine
from bluesky.run_engine import DocumentNames
from bluesky.broker_callbacks import LiveImage
from bluesky.callbacks import CallbackBase, LiveTable, LivePlot

from ophyd.commands import *
from ophyd.controls import *

from dataportal import DataBroker as db
from dataportal import get_events, get_table, get_images
from metadatastore.commands import find_run_starts
from tifffile import *

#pd.set_option('max_colwidth',70)
pd.set_option('colheader_justify','left')

default_keys = ['owner', 'beamline_id', 'group', 'config', 'scan_id'] # default fields in databroker
feature_keys = ['composition', 'temperature', 'experimenter_name'] # this need to be hard coded, as it defines our human readible file name

w_dir = '/home/xf28id1/xpdUser/tif_base'
r_dir = '/home/xf28id1/xpdUser/config_base'
d_dir = '/home/xf28id1/xpdUser/dark_base'
backup_dir = '/home/xf28id1/pe1_data'

def meta_gen(fields, values):
    """generate metadata dictionary used in your run engines
    arguments:
        -fields: metadata fields, it is defined to suite your need.
        -values: metadata values corresponding to fields your defined.
        
    Note: Please type in fields and corresponding values of desired search with exact order
    """
    metadata_dict = {}
    for i in range(len(fields)):
        metadata_dict[fields[i]] = values[i]
    return metadata_dict

def save_tiff(header_list, summing = True):
    ''' save image files in certain header(s)
    
    argument:
    header_list - list - obtained from dataBroker
    summing - decided if you want to sum different frames

    '''
    # iterate over header(s)
    try: 
        for header in header_list:
            dummy = ""
            dummy_key_list = [e for e in header.start.keys() if e in feature_keys] # stroe a list independently

            for key in dummy_key_list:
                dummy += str(header.start[key])+'_'      
            feature = dummy[:-1]
            uid_val = header.start.uid[:6]
            try: # try to obtain these fields
                comment = header.start['comments']
            except:
                pass
            try: # try to obtain these fields
                cal = header.start['calibration']
            except:
                pass
            time= str(datetime.datetime.fromtimestamp(header.stop.time))
            date = time[:10]
            hour = time[11:16]
            timestamp = '_'.join([date, hour])
            
            # get images from headers
            imgs = np.array(get_images(header,'pe1_image_lightfield'))
            
            if summing == True:
                f_name = '_'.join([uid_val, timestamp, feature+'.tif'])
                w_name = os.path.join(w_dir,f_name)
                img = np.sum(imgs,0)
                imsave(w_name, img) # overwrite mode now !!!!
                if os.path.isfile(w_name):
                    print('%s has been saved at %s' % (f_name, w_dir))
                else:
                    print('Sorry, somthing went wrong with your tif saving')
                    return
            elif summing == False:
                for i in range(imgs.shape[0]):
                    f_name = '_'.join([uid_val, timestamp, feature,'00'+str(i)+'.tif'])
                    w_name = os.path.join(w_dir,f_name)
                    img = imgs[i]
                    imsave(w_name, img) # overwrite mode now !!!!
                    if os.path.isfile(w_name):
                        print('%s has been saved at %s' % (f_name, w_dir))
                    else:
                        print('Sorry, somthing went wrong with your tif saving')
                        return


    except AttributeError:  # when only one header is given
        dummy = ""
        header = header_list
        dummy_key_list = [f for f in header.start.keys() if f in feature_keys]

        for key in dummy_key_list:
            dummy += str(header.start[key])+'_'

        feature = dummy[:-1]
        uid_val = header.start.uid[:6]
        try:
            comment = header.start['comments']
        except:
            pass
        try:
            cal = header.start['calibration']
        except:
            pass
        time= str(datetime.datetime.fromtimestamp(header.stop.time))
        date = time[:10]
        hour = time[11:16]
        timestamp = '_'.join([date, hour])
            
        # get images as np array from headers
        imgs = np.array(get_images(header,'pe1_image_lightfield'))
        if summing == True:
            f_name = '_'.join([uid_val, timestamp, feature+'.tif'])
            w_name = os.path.join(w_dir,f_name)
            img = np.sum(imgs,0)
            imsave(w_name, img) # overwrite mode now !!!!
            if os.path.isfile(w_name):
                print('%s has been saved at %s' % (f_name, w_dir))
            else:
                print('Sorry, somthing went wrong with your tif saving')
                return
        elif summing == False:
            for i in range(imgs.shape[0]):
                f_name = '_'.join([uid_val, timestamp, feature,'00'+str(i)+'.tif'])
                w_name = os.path.join(w_dir,f_name)
                img = imgs[i]
                imsave(w_name, img) # overwrite mode now !!!!
                if os.path.isfile(w_name):
                    print('%s has been saved at %s' % (f_name, w_dir))
                else:
                    print('Sorry, somthing went wrong with your tif saving')
                    return
       

def run_calibration(sample, wavelength, exp_time=0.2 , num=10, **kwargs):
    '''Runs a calibration dataset
    
    Arguments:
    sample - string - Chemical composition of the calibrant in form LaB6, for example
    wavelength - float - wavelength in nm, which is obtained from verify_wavelength function
    exp_time - float - count-time in seconds.  Default = 0.2 s
    num - int - number of counts
    '''
    import os
    # set up calibration information
    gs.RE.md['comments'] = 'calibration'
    gs.RE.md['calibrant'] = sample
    gs.RE.md['composition'] = sample
    gs.RE.md['wavelength'] = wavelength
    gs.RE.md['acquisition_time'] = exp_time
    gs.RE.md['num_calib_exposures'] = num 

    # extra field define whatever you want
    for key, value in kwargs.items():
        gs.RE.md[key] = value
    
    # define a scan
    pe1.acquire_time = 0.2
    ctscan = bluesky.scans.Count([pe1], num=num)
    print('collecting calibration data. '+str(num)+' acquisitions of '+str(exp_time)+' s will be collected')
    ctscan.subs = LiveTable(['pe1_image_lightfield'])
    gs.RE(ctscan)

    # recover to clean state, remove extra key
    extra_key = [f for f in gs.RE.md.keys() if f not in default_keys]
    for key in extra_key:
        del(gs.RE.md[key])

    gs.RE.md['comments'] = ''
    gs.RE.md['calibrant'] = ''
    gs.RE.md['composition'] = ''
    gs.RE.md['wavelength'] = '' # fixme: maybe delete it as we don't need in experiments ?
    gs.RE.md['acquisition_time'] = ''
    gs.RE.md['num_calib_exposures'] = ''
    
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
    w_name = os.path.join(w_dir, f_name)
    imsave(w_name, img)
    if os.path.isfile(w_name):
        print('A summed image %s has been saved to %s' % (f_name, w_dir))
    #print(str(check_output(['ls', '-1t', '|', 'head', '-n', '10'], shell=True)).replace('\\n', '\n'))
   

def load_calibration(config_file = False, config_dir = False):
    '''Function loads calibration values as BlueSky metadata
    
    takes calibration values from a SrXplanar config file and 
    loads them in the Bluesky global state run engine metadata dictionary. 
    They will all automatically be saved
    
    Arguments:
    config_file - str - name of your desired config file. If unspecified, most recent one will be used
    config_dir - str - directory where your config files located at. If unspecified, default directory is used
    '''

    ###### setting up directory #######
    if not config_dir:
        read_dir = r_dir
    else:
        read_dir = str(config_dir)
    
    
    
    if not config_file: 
    # reading most recent config file in the read_dir  ########
        f_list = [ f for f in os.listdir(read_dir) if f.endswith('.cfg')]
    
        f_dummy = []
        for f in f_list:
            f_dummy.append(os.path.join(read_dir,f))

        f_sort = sorted(f_dummy, key = os.path.getmtime)
        f_last = str(f_sort[-1])
        config_file = f_last
        f_name = os.path.join(read_dir,config_file)
        if len(config_file) >0:
            print('Using '+ f_name +', the most recent config file that was found in ' +read_dir )
        else:
            print('There is no file in '+ read_dir)
    else:
        f_name = os.path.join(read_dir,config_file)
        
        if os.path.isfile(f_name):
            print('Using user-supplied config file: '+config_file+' located at'+ read_dir)
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
    

def new_user(User, Sample, Comments=False, temperature = False, **kwargs):
    '''creates new metadata field for your runengine
    
    Arguments:
    name - str - current user name
    sample - str - current sample
    comments - str - comments to current experiment
    *kargs - str - any fields you want to update in metadata dictionary
    '''
    while True:
        if not temperature:
            temp = str(cs700.value[1])+'K'
        else:
            temp = str(temperature) # user defined value
        
        # read out current metadata diectionray
        gs.RE.md['experimenter_name'] = User
        gs.RE.md['composition'] = Sample
        gs.RE.md['temperature'] = temp
        gs.RE.md['date'] = str(datetime.datetime.today().date())
        
        if not Comments:
            gs.RE.md['comments'] = " "
        else:    
            gs.RE.md['comments'] = Comments
        
        # user define keys
        for key, value in kwargs.items():
            gs.RE.md[key] = value

        meta_keys = list(gs.RE.md.keys())
        meta_values = list(gs.RE.md.values())
    
        print("Your metadata fields are: "+ str(meta_keys))
        print("Corresponding values are: "+ str(meta_values))
        
        time.sleep(0.5)
        #fixme: discuss with Sanjit on 20151018, not sure if we are doing this or not
        user_dir = input('Where do you want to put your backup file under /home/xf28id1/pe1_data ?')
        user_backup_dir = os.path.join(backup_dir, user_dir) 

        user_justify = input("Is everything listed above correct?(y/n)")
        if user_justify == "y":
            break

        elif user_justify == "n":
            print("Abroted. Stop setting up")
            return
        
        else:
            print("Please only type in y/n")
            print("Return to defining meatadata")
            pass
    
    print("Continue setting up global run engines(gs.RE) with your metadata.......")
    time.sleep(0.5)
    print("global runengine states have been updated")
    print("Initialization finished.")
        
def new_sample(Sample, **kwargs):
    '''Sets up the metadata when the sample has been changed
    
    Argument:
    Sample - str - list of your sample and it can include amount infortmation
    '''
    gs.RE.md['sample']['composition'] = str(Sample)

    #user defined field
    for key, value in kwargs.items():
        gs.RE.md[key] = value

    return
    
def and_search(**kwargs):
    """generate mongoDB recongnizable query of "and_search" and rerutn data
    
    Arguments:
        -fields : fields you want to search on. For example, metadata stored in sample.<metadata>" or standard
        field like "start_time". Make sure you know where is the field-value pair exactly located at.
        
        -values : values you are looking for. For example, "NaCl" or "300k". Make sure you know where is the field-value pair 
        exactly located at.
        
        Note: Please type in fields and corresponding values of desired search with exact order
    """
    dict_gen = {}
    cond_list = []
    
    for key, value in kwargs.items():
        dict_gen[key] = value

    and_header = db(**dict_gen)
    and_out = get_events(and_header, fill=False)
    and_out = list(and_out)
    print('||Your search gives out '+str(len(and_header))+' headers||')
    
    return and_header
    
def table_gen(header_list):
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
    excluding_list = ['calibration', 'instrument'] # which fields are excluded when ploting header
    try: 
        for header in header_list:
            dummy = ""
            dummy_key_list = [e for e in header.start.sample.keys() if f not in excluding_list] # stroe list independently

            for key in dummy_key_list:
                dummy += str(header.start.sample[key])+'_'      
            feature_list.append(dummy[:-1])

            try:
                comment_list.append(header.start.sample['comments'])
                cal_list.append(header.start.sample['calibration'])
                uid_list.append(header.start.uid[:4])
            except:
                pass
    except AttributeError:
        dummy = ""
        key_list = header_list.start.sample.keys()
        dummy_key_list = [f for f in key_list if f not in excluding_list] # stroe list independently

        for key in dummy_key_list:
            dummy += str(header_list.start.sample[key])+'_'      
        feature_list.append(dummy[:-1])

        try:
            comment_list.append(header_list.start.sample['comments'])
            cal_list.append(header_list.start.sample['calibration'])
            uid_list.append(header_list.start.uid[:4])
        except:
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
    print('||You assign a time search in the period:\n'+str(timeHead)+' and '+str(timeTail)+"||" )
    print('||Your search gives out '+str(len(event_time))+' results||')
          
    return header_time


def sanity_check(user_in=None):
    user = gs.RE.md['sample']['experimenter_name']
    compo = gs.RE.md['sample']['composition']
    calib = gs.RE.md['sample']['calibration']
    time = str(datetime.datetime.now())
    
    print('Hey '+user+' ,current sample is: '+compo+', calibration file is using: '+calib+', time is: '+time)
    uin= input('Is it correct? y/n')
    if uin == 'y':
        print('Great, lets start')
    elif uin == 'n':
        print('Please correct your setting or make sure that is your experiment')
    else:
        return

def data_saver(header_list, save_dir = False):
    ''' save image data of give header_list as tif file to save_dir
    arguments:
    header_list - list - a list of desired header
    save_dir - str - directory name of where tif data will be saved. Default is /home/xf28id1/xpdUser/tif_base
    '''

    excluding_list = ['calibration', 'instrument'] # which fields are excluded in ploting header
    cal_list = []
    feature_list = []
    uid_list = []
    try: 
        for header in header_list:
            dummy = ""
            dummy_key_list = [e for e in header.start.sample.keys() if f not in excluding_list] # stroe list independently

            for key in dummy_key_list:
                dummy += str(header.start.sample[key])+'_'
            feature = dummy[:-1]

            try:
                #comment_list.append(header.start.sample['comments'])
                cal_list.append(header.start.sample['calibration'])
                uid_list.append(header.start.uid[:4])
            except:
                pass
        # prepare timestamp, uid
            time= str(datetime.datetime.fromtimestamp(header.stop.time))
            date = time[:10]
            hour = time[11:16]
            timestamp = '_'.join([date, hour])
            uid = header.stop.uid[:4]

            file_name = '_'.join([uid, feature, timestamp])
            ts.basename = file_name

            if not save_dir:
                tif_dir = w_dir
            else:
                tif_dir = save_dir
            ts.outputdir = tif_dir

            try:
                ts.saveScans(header)
                print('tif files are successfully saved at '+ tif_dir + '. Confirm it as you wish')
            except:
                print('tif is not saved for some reason. Please check your setting')
                print('Typical issue: does your header contain 2D image?')        
                return
    except AttributeError:
        dummy = ""
        header = header_list # important !
        key_list = header.start.sample.keys()
        dummy_key_list = [f for f in key_list if f not in excluding_list] # stroe list independently

        for key in dummy_key_list:
            dummy += str(header.start.sample[key])+'_'      
        feature = dummy[:-1]

        try:
            #comment_list.append(header.start.sample['comments'])
            cal_list.append(header.start.sample['calibration'])
            uid_list.append(header.start.uid[:4])
        except:
            pass
                
        
        # prepare timestamp, uid
        time= str(datetime.datetime.fromtimestamp(header_list.stop.time))
        date = time[:10]
        hour = time[11:16]
        timestamp = '_'.join([date, hour])
        uid = header_list.stop.uid[:4]

        file_name = '_'.join([uid, feature, timestamp])
        ts.basename = file_name

        if not save_dir:
            tif_dir = w_dir
        else:
            tif_dir = save_dir
        ts.outputdir = tif_dir

        try:
            ts.saveScans(header)
            print('tif files are successfully saved at '+ tif_dir + '. Confirm it as you wish')
        except:
            print('tif is not saved for some reason. Please check your setting')
            print('Typical issue: does your header contain 2D image?')        
            return


def prompt_save(name):
    excluding_list = ['calibration', 'instrument'] # which fields are excluded in ploting header
    if name == "stop":
        header = db[-1]
        dummy = ""
        dummy_key_list = [f for f in header.start.sample.keys() if f not in excluding_list] # stroe it independently
            
        for key in dummy_key_list:
            dummy += str(header.start.sample[key])+'_'
                
        feature = dummy[:-1]
        
        # prepare timestamp, uid
        time= str(datetime.datetime.fromtimestamp(header.stop.time))
        date = time[:10]
        hour = time[11:16]
        timestamp = '_'.join([date, hour])
        uid = header.stop.uid[:4]

        file_name = '_'.join([uid, feature, timestamp])
        ts.basename = file_name
        ts.outputdir = user_backup_dir
        ts.saveScans(header)

def get_dark_images(num = 600, cnt_time =0.5):
    """ Acquire dark image stacks as a correction base
    """
    gs.RE.md['dark_bool'] = 'True'
    
    time= str(datetime.datetime.fromtimestamp(header.stop.time))
    date = time[:10]
    hour = time[11:16]
    timestamp = '_'.join([date, hour])
    dark_info = {'uids':[], 'timestamp':timestamp, 'expo_time':cnt_time}
    
    # set up scan
    pe1.acquire_time = cnt_time
    ctscan = bluesky.scans.Count([pe1],num) 
    
    # obtain dark image
    gs.RE(ctscan)

#    for i in range(num):  #fixme: I follow the sudo code, but don't we want long count time?
#        ct()
#        uid = db[-1].start.uid
#        dark_info['uids']=uid[:5] # put into dictionary
    
    gs.RE.md['dark_bool'] = 'False'
    gs.RE.md['dark_info'] = dark_info # put in your dark dictionary
    print('Your current acquire_time is %i' % pe1.acquire_time)

    header = db[-1]
    uid = header.start.uid[:5]
    timestamp = header.start.dark_info.timestamp
    imgs = get_images(header,'pe1_image_lightfiled')

    for i in range(imgs.shape[0]):
        f_name = '_'.join([uid, timestamp, dark,'00'+str(i)+'.tif'])
        w_name = os.path.join(d_dir,f_name)
        img = imgs[i]
        imsave(w_name, img) # overwrite mode now !!!!
        if not os.path.isfile(w_name):
            print('Sorry, somthing went wrong when doing dark_image') # just quit, not printing
            return




def dark_correction(header_list, dark_base):
    """ substract dark images """

    dark_info = gs.RE.md['dark_info']
    dark_count_time = dark_info['expo_time']
    excluding_list = ['calibration', 'instrument']

