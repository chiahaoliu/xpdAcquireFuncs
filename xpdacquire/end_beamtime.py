import datetime
import os
from xpdacquire.xpdacquirefuncs import _bluesky_metadata_store
from xpdacquire.config import datapath
import sys


metadata = _bluesky_metadata_store()

W_SUB_DIR = 'tif_base'
D_SUB_DIR = 'dark_base'
R_SUB_DIR = 'config_base'
S_SUB_DIR = 'script_base'

W_DIR = datapath.tif
D_DIR = datapath.dark
R_DIR = datapath.config
S_DIR = datapath.script

B_DIR = '/home/xf28id1/billingegroup/pe1_data' 
# default networked drive where all tifs are automatically written but also user-generated data will be stored


def end_beamtime():
    '''cleans up at the end of a beamtime

    Function takes all the user-generated tifs and config files, etc., and archives them to a
    directory in the remote file-store with filename B_DIR/useriD

    '''
    
    SAF_num = metadata['SAF_number']
    userID = SAF_num
    userIn = input('SAF number to current experiment is %s. Is it correct (y/n)? ' % SAF_num)
    if userIn not in ('y','yes',''):
        print('Alright, lets do it again...')
        return

    print('Checking if your input results in invalid directory name in unix system...')
    # check if name is a valid name
    clean_name = [ ch for ch in userID if ch.isalnum()]
    time = datetime.datetime.now()
    year = time.year
    month = time.month
    clean_path = ''.join(clean_name)
    time_path = '_'.join([str(year), str(month)])
    path_element = (clean_path, time_path)
    backup_trunk = os.path.join(B_DIR, clean_path, time_path)

    print('Current data in tif_base, dark_base, config_base and script_base will be moved to %s' % backup_trunk)
    userJustify = input('Please confirm again that is a correct path (yes/no) :')
    if userJustify not in ('yes', 'y',''):
        print('Alright, lets do it again...')
        return
    if os.path.exists(backup_trunk):
        print('a directory already appears to exist for this userID for this month.')
        print('before proceeding, check that you entered the correct userID')
        print('do you want to create a new backup directory for a new beamtime with this user?')
        print('to add files to the existing backup directory hit return.')
        respo = input('Otherwise, enter a new directory name, e.g., "secondbeamtime":')
        if str(respo) != '':
            new_path = os.path.join(B_DIR, clean_path, time_path + str(respo))
            backup_trunk = new_path
        else:
            print('continue...')

    # check if backup_trunk exitsts and create it if it doesn't exist
    if not os.path.exists(backup_trunk):
       os.makedirs(backup_trunk)

    print('Now we are about to move files....')
    todir_w = os.path.join(backup_trunk,W_SUB_DIR)
    todir_d = os.path.join(backup_trunk,D_SUB_DIR)
    todir_r = os.path.join(backup_trunk,R_SUB_DIR)
    todir_s = os.path.join(backup_trunk,S_SUB_DIR)
    dir_list = [todir_w, todir_d, todir_r, todir_s]

    #print(dir_list)
    
    for el in dir_list:
        try:
            os.makedirs(el)
        except OSError:
            print('%s has already existed. Please investigate what happen' % el)
            return

    # os.renames already testing if user has the right to write files
    os.renames(W_DIR, todir_w)
    os.renames(D_DIR, todir_d)
    os.renames(R_DIR, todir_r)
    os.renames(S_DIR, todir_s)
    print('All user generated files have been moved from:')
    print(W_DIR)
    print(R_DIR)
    print(D_DIR)
    print(S_DIR)
    print('to:')
    print(todir_w)
    print(todir_r)
    print(todir_d)
    print(todir_s)
    print('where they will be archived for at least one year')
    print('END of process')

#if __name__ == '__main__':
    #end_beamtime()
