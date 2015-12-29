############ clean code, ready to be applied to class  ###############

def _timestampstr(timestamp):
    import datetime
    time = str(datetime.datetime.fromtimestamp(timestamp))
    date = time[:10]
    hour = time[11:16]
    m_hour = hour.replace(':','-')
    timestampstring = '_'.join([date,hour])
    #corrected_timestampstring = timestampstring.replace(':','-')
    return timestampstring


def Set_experiment(safN, experimenters, update, time):
    ''' This function sets up experimenter name(s). This function can be run at anytime to change experimenter global setting
    Argument:
        experimenters - str or list - name of current experimenters
        update - bool - optional. set True to update experimenters list and set False to extend experimenters list
    '''
    experimenters_list = []
    if not isinstance(experimenters, list):
        if isinstance(experimenters, str):
            experimenters_list.append(experimenters)
        else:
            raise TypeError('Experimenters needs to be str or list')
    else:
        experimenters_list = experimenters

    if not isinstance(safN, str):
        raise TypeError('SAF number needs to be a str')
    
    timestamp = _timestampstr(time)    
    print('Current experimenters is/are %s' % experimenters_list)
    print('Current SAF number is %s' % safN)

    return (safN, experimenters_list, timestamp)


def composition_dict_gen(sample):
    '''generate composition dictionary with desired form

    argument:
    sample_name - tuple - if it is a mixture, give a tuple following corresponding amounts. For example, ('NaCl',1,'Al2O3',2)
    '''

    from utils import composition_analysis
    sample_list = [ el for el in sample if isinstance(el,str)]
    amount_list = [ amt for amt in sample if isinstance(amt, float) or isinstance(amt, int)]
    compo_dict_list = []
    for i in range(len(sample_list)):
        compo_dict = {}
        compo_dict['phase_name'] = sample_list[i]
        compo_analysis_dict = {}
        (e,a) = composition_analysis(sample_list[i])
        for j in range(len(e)):
            compo_analysis_dict[e[j]] = a[j]
        compo_dict['element_info'] = compo_analysis_dict
        compo_dict['phase_amount'] = amount_list[i]
        
        compo_dict_list.append(compo_dict)
    return compo_dict_list


def Set_sample(sample_name, sample, time):
    '''set up metadata fields for your runengine

    This function sets up persistent metadata that will be saved with subsequent scans,
    including a list of experimenters and the sample composition, as well as other user
    defined comments.  It can be rerun multiple times until you are happy with the settings,
    then these settings will be applied to scan metadata when the scans are run later.

    Arguments:
    
    sample_name - str - name to your sample
    sample - tuple- a tuple including sample name such as "dppa2" or "Al2O3" and corresponding amount.
        For example, ('CaCO3',1.0) means a pure sample and ('CaCO3',1.0,'TiO2',2.0) stands for a 1:2 mix of CaCO3 and TiO2
    '''
    #gs = _bluesky_global_state()

    if not isinstance(sample_name, str):
        raise TypeError('sample_name must be a str')
    
    if not isinstance(sample, tuple):
        raise TypeError('sample must be a tuple in order to generate composition dictionary')

    composition = composition_dict_gen(sample)
    timestamp = _timestampstr(time)
    print('Current sample_name is %s' % sample_name)
    print('Current composition is %s' % composition)
 
    return (sample_name, composition, timestamp) 



###########################################################







## functionalities of managing metadata
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
    #gs = _bluesky_global_state()
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

