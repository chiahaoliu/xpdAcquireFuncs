## xpd md data, using composition method

import time
class Experiment(object):
    def __init__(self, safN = '', experimenters = [], update = False, time = time.time()):
        self.set_experiment(safN, experimenters, update, time)

    def set_experiment(self, safN_val, experimenters_val, update = False, time=time.time()):
        from lib_xpd_md import Set_experiment
        out = Set_experiment(safN_val, experimenters_val, update, time)
        self.safN = out[0]
        self.experimenters = out[1]
        # FIXME: time stamp is incorrect now. It is the time of instanciation
        self.modified_time = out[2]
        
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

    def __getattr__(self, name):
        # get attributes from all parent layer
        return getattr(self.Sample, name)
