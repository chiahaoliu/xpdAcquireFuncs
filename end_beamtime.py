# python fixme
def end_beamtime():
    '''cleans up at the end of a beamtime

    Function takes all the user-generated tifs and config files and archives them to a
    directory in the remote file-store with filename B_DIR/useriD

    Arguments:
        userID - string - unique id for the user group who is just finishing up
    '''
    import os
    
    W_DIR = '/home/xf28id1/xpdUser/tif_base'                # where the user-requested tif's go.  Local drive
    R_DIR = '/home/xf28id1/xpdUser/config_base'             # where the xPDFsuite generated config files go.  Local drive
    D_DIR = '/home/xf28id1/xpdUser/dark_base'               # where the tifs from dark-field collections go. Local drive
    B_DIR = '/home/xf28id1/pe1_data'                        # default networked drive where all tifs are automatically written but also user-generated data will be stored

    input('Please enter the unique ID (name) of the user-group (with no spaces):',userID)
    backup_trunk = os.path.join(B_DIR,userID)
    # fixme code to check if ALL of tif_base, etc. are empty
    if checkempty:
        print('All the working directories appear to be empty.  Either end_beamtime.py has already been run')
        print('or the path to the expected working directories are incorrectly set.')
        print('The paths being used are:')
        print(W_DIR)
        print(R_DIR)
        print(D_DIR)
        exit()
        
    # fixme check if backup_trunk already exists
    if not btrunk:
        # create btrunk
    # fixme create yearMonth
    bdir = os.path.join(btrunk,yearMonth)
    # fixme check if bdir exists
    if bdir:
        print('a directory already appears to exist for this userID for this month.')
        print('before proceeding, check that you entered the correct userID')
        print('do you want to create a new backup directory for a new beamtime with this user?')
        print('to add files to the existing backup directory hit return.')
        input('Otherwise, enter a new directory name, e.g., "secondbeamtime":',respo)
        if str(respo) not '':
            bdir = os.path.join.(bdir,str(respo))

    # fixme mv tif_base, dark_base and config_base in the backup place then empty them on the local drive
    todir_w = os.path.join(bdir,W_DIR)
    todir_d = os.path.join(bdir,D_DIR)
    todir_r = os.path.join(bdir,r_DIR)
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
