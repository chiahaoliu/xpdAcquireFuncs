# python fixme
def end_beamtime(userID):
    '''cleans up at the end of a beamtime

    Function takes all the user-generated tifs and config files, etc., and archives them to a
    directory in the remote file-store with filename B_DIR/useriD

    Arguments:
        userID - string - unique id for the user group who is just finishing up
    '''
    import os

    W_DIR = '/home/xf28id1/xpdUser/tif_base'                # where the user-requested tif's go.  Local drive
    R_DIR = '/home/xf28id1/xpdUser/config_base'             # where the xPDFsuite generated config files go.  Local drive
    D_DIR = '/home/xf28id1/xpdUser/dark_base'               # where the tifs from dark-field collections go. Local drive
    B_DIR = '/home/xf28id1/pe1_data'                        # default networked drive where all tifs are automatically written but also user-generated data will be stored
    while True:
        userID = input('Please enter the beamline ID (name) of the user-group(with no spaces):')
        print('Checking if your input contains invalid file name in unix system...')
        # check if name is a valid name
        clean_name = [ ch for ch in userID if ch.isalnum()]
        clean_path = ''.join(clean_name)
        backup_trunk = os.path.join(B_DIR,clean_path)
        print('Current data in tif_base, dark_base and config_base will be moved to %s' % backup_trunk)
        userJustify = input('Please confirm again that is a correct path (yes/no)')
        if userJustify == 'yes':
            break
        else:
            print('Alright, lets do it agin')
            pass

    # code to check if ALL of tif_base, etc. are empty
    w_len = len(os.listdir(W_DIR))
    d_len = len(os.listdir(D_DIR))
    r_len = len(os.listdir(R_DIR))
    s_len = len(os.listdir(S_DIR)) # script base
    if (w_len!=0 and d_len!=0 and r_len!=0 and s_len!=0):
        print('All the working directories appear to be empty.  Either end_beamtime.py has already been run')
        print('or the path to the expected working directories are incorrectly set.')
        print('The paths being checked are:')
        print(W_DIR)
        print(R_DIR)
        print(D_DIR)
        return
    # check if btrunk exitsts and create it if it doesn't exist
    if not os.path.exits(backup_trunk):
        os.makedir(backup_trunk)
    # prepare year and month
    time = datetime.datetime.now()
    year = str(time.year)
    month = str(time.month)
    yearMonth = '-'.join([year,month])
    bdir = os.path.join(btrunk,yearMonth)
    if os.path.exits(bdir):
        print('a directory already appears to exist for this userID for this month.')
        print('before proceeding, check that you entered the correct userID')
        print('do you want to create a new backup directory for a new beamtime with this user?')
        print('to add files to the existing backup directory hit return.')
        respo = input('Otherwise, enter a new directory name, e.g., "secondbeamtime":')
    if str(respo) != '':
        bdir = os.path.join.(bdir,str(respo))
        pass
    elif str(respo) == '':
        print('please enter a new directory name and try again')
        return

    # fixme mv tif_base, dark_base and config_base in the backup place then empty them on the local drive
    print('Now we are about to move files....')
    todir_w = os.path.join(bdir,W_DIR)
    todir_d = os.path.join(bdir,D_DIR)
    todir_r = os.path.join(bdir,r_DIR)
    os.rename(W_DIR, todir_w)
    os.rename(D_DIR, todir_d)
    os.rename(R_DIR, todir_r)
    print('All user generated files have been moved from:')
    print(W_DIR)
    print(R_DIR)
    print(D_DIR)
    print('to:')
    print(todir_w)
    print(todir_r)
    print(todir_d)
    print('where they will be archived for at least one year')

if __name__ == '__main__':
    end_beamtime()
