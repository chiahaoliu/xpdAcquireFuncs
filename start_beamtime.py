def start_beamtime():
    '''sets up a new beamtime

    Function checks that tif_base, dark_base etc. is empty from the previous beamtime
    '''
    import os
    
    HOME_DIR = '/home/xf28id1/xpdUser'
    
    W_DIR = '/home/xf28id1/xpdUser/tif_base'
    D_DIR = '/home/xf28id1/xpdUser/dark_base'
    R_DIR = '/home/xf28id1/xpdUser/config_base'
    S_DIR = '/home/xf28id1/xpdUser/script_base'


    os.chdir(HOME_DIR)
    current_dir = os.getcwd()
    print('successfully moved to working directory: ')
    print(current_dir+'\n')
    
    # fixme check that all of tif_base, dark_base, config_base are empty
    w_len = len(os.listdir(W_DIR))
    d_len = len(os.listdir(D_DIR))
    r_len = len(os.listdir(R_DIR))
    s_len = len(os.listdir(S_DIR))
    if not (w_len!=0 and d_len!=0 and r_len!=0 and s_len!=0):
        print('the working directories are not empty.')
        print('if this is really a new beamtime, then please run end_beamtime.py to archive')
        print('the current user-generated data and empty the directories for the new user.')
        return
    else:
        print('everything is ready to begin.  Please continue with icollection')

if __name__ == '__main__':
    start_beamtime()
