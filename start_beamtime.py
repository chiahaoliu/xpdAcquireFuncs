def start_beamtime():
    '''sets up a new beamtime

    Function checks that tif_base, dark_base etc. is empty from the previous beamtime
    '''
    # fixme check that all of tif_base, dark_base, config_base are empty
    if not empty:
        print('the working directories are not empty.'
        print('if this is really a new beamtime, then please run end_beamtime.py to archive')
        print('the current user-generated data and empty the directories for the new user.')
        exit()
    else:
        print('everything is ready to begin.  Please continue with icollection')

if __name__ == '__main__':
    start_beamtime()
