## xpd md data, using composition method
import time

## current logic: this metadata class manage data input, lib_xpd_md takes care of method

class Beamtime(object):
    def __init__(self, safN, start_date, end_date, experimenters = [], update = False ):
        import time
        import uuid
        uid = str(uuid.uuid1())
        self.beamtime_uid = uid
        print('uid to this beamtime is %s' % uid)

        self.beamtime_start_date = start_date
        self.beamtime_end_date = end_date
        print('start date and end date of this beamtime: ( %s, %s )' % (start_date, end_date))
       
        self.modified_time = time.time() 
        
        self.set_beamtime(safN, experimenters, update)

    def set_beamtime(self, safN_val, experimenters_val, update = False):
        from lib_xpd_md import Set_beamtime
        out = Set_beamtime(safN_val, experimenters_val, update)
        self.safN = out[0]
        self.experimenters = out[1]
        self.modified_time = out[2]

    def show_beamtime(self):
        full_info = self.__dict__
        real_info = {}
        for k in full_info.keys():
            if k.islower():
                real_info[k] = full_info.get(k)
        return real_info


class Experiment(object):
    def __init__(self, obj, user_dict=None):
        #FIXME method to dump in key, value pairs to attribute
        import uuid
        uid = str(uuid.uuid1())
        self.experiment_uid = uid
        
        if user_dict:
            for k,v in user_dict.items():
                setattr(self, k, v)  
    
        self.set_experiment()
        self.Beamtime = obj

    def set_experiment(self):
        from lib_xpd_md import Set_experiment
        out = Set_experiment()
        #self.safN = out[0]
        #self.experimenters = out[1]
        #self.modified_time = out[2]

    def show_experiment(self):
        full_info = self.__dict__
        real_info = {}
        for k in full_info.keys():
            if k.islower():
                real_info[k] = full_info.get(k)
        return real_info
    
    def __getattr__(self, name):
        # get attributes from all parent layer
        return getattr(self.Beamtime, name)
        
class Sample(object):
    def __init__(self, obj, sample_name='', composition=(), comments='', time = time.time()):
        self.set_sample(sample_name, composition)
        self.sample_comments = comments

        # assign Experiment to object name
        self.Experiment = obj

    def set_sample(self, sample_name_val, sample_val, time = time.time()):
        from lib_xpd_md import Set_sample
        out = Set_sample(sample_name_val, sample_val, time)
        self.sample_name = out[0]
        self.composition = out[1]
        # FIXME: time stamp is incorrect now. It is the time of instanciation
        self.modified_time = out[2]

    def show(self):
        full_info = self.__dict__
        real_info = {}
        for k in full_info.keys():
            if k.islower():
                real_info[k] = full_info.get(k)
        return real_info

    def __getattr__(self, name):
        # get attributes from all parent layer
        return getattr(self.Experiment, name)


class Scan(object):
    def __init__(self, obj, scan_tag = '', config = {}):
        self.set_scan(scan_tag, config)
        
        self.Sample = obj

    def set_scan(self, scan_tag, config):
        self.scan_tag = '_method_applied'
        self.config = {}

    def show(self):
            full_info = self.__dict__
            real_info = {}
            for k in full_info.keys():
                if k.islower():
                    real_info[k] = full_info.get(k)
            return real_info

    def __getattr__(self, name):
        # get attributes from all parent layer
        return getattr(self.Sample, name)
