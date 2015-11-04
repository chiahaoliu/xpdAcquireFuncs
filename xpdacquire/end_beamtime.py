from xpdacquire.config import datapath
W_DIR = datapath.tif
D_DIR = datapath.dark
R_DIR = datapath.config
S_DIR = datapath.script

def end_beamtime():
    '''cleans up at the end of a beamtime

    Function takes all the user-generated tifs and config files, etc., and archives them to a
    directory in the remote file-store with filename B_DIR/useriD

    '''
    import os
    
    B_DIR = '/tmp/pe1_data' # default networked drive where all tifs are automatically written but also user-generated data will be stored
    while True:
        userID = input('Please enter the SAF number of this beamtime(no space): ')
        print('Checking if your input results in invalid directory name in unix system...')
        # check if name is a valid name
        clean_name = [ ch for ch in userID if ch.isalnum()]
        clean_path = ''.join(clean_name)
        backup_trunk = os.path.join(B_DIR,clean_path)
        print('Current data in tif_base, dark_base, config_base and script_base will be moved to %s' % backup_trunk)
        userJustify = input('Please confirm again that is a correct path (yes/no) :')
        if userJustify == 'yes':
            break
        else:
            print('Alright, lets do it agin')
            pass

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
        elif str(respo) == '':
            print('please enter a new directory name and try again')
            return

    # fixme mv tif_base, dark_base and config_base in the backup place then empty them on the local drive
    print('Now we are about to move files....')
    todir_w = os.path.join(bdir,W_DIR)
    todir_d = os.path.join(bdir,D_DIR)
    todir_r = os.path.join(bdir,R_DIR)
    todir_s = os.path.join(bdir,S_DIR)
    dir_list = [todir_w, todir_d, todir_r, todir_s]
    try:
        for el in dir_list:
            with open(os.join(el,'writting_test.txt')) as f:
                f.write('Test writting permission ....')
    except FileNotFoundError:
        print('You do not have writting priveleges on all the directories, either already exits or you are not root')
        print('Please reach out IT sector or beamline scientists for help')
        print('Stop moving data...')
        return

    os.renames(W_DIR, todir_w)
    os.renames(D_DIR, todir_d)
    os.renames(R_DIR, todir_r)
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
