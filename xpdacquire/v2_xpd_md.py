## md class v2: inheritance

import time

class Experiment(object):
    def __init__(self, safN='', experimenters=[], update = False):
        super(Experiment, self).__init__()
        self.set_experiment(safN, experimenters, update)
        
    #def show(self):
        #return self.__dict__

    #FIXME include logic for partially update experimenters  
    def set_experiment(self, safN_val, experimenters_val, update = False):
        from lib_xpd_md import Set_experiment
        import time
        time = time.time()
        out = Set_experiment(safN_val, experimenters_val, update, time)
        self.safN = out[0]
        self.experimenters = out[1]
        self.modified_time = out[2]

class Sample(Experiment):
    def __init__(self, sample_name = '', sample=tuple(), comments=''):
        super(Sample, self).__init__()
        self.set_sample(sample_name, sample, time.time())
        self.sample_comments = comments
    
    #def show_sample(self):
        #return getattr(self, list(vars(self).keys())[0])
    
    def set_sample(self, sample_name_val, sample_val, time = time.time()):
        from lib_xpd_md import Set_sample
        out = Set_sample(sample_name_val, sample_val, time=time)

        self.sample_name = out[0]
        self.composition = out[1]
        self.modified_time = out[2]
    
class Scan(Sample):
    def __init__(self, scan=''):
        super(Scan, self).__init__()
        self.set_scan(scan)
        #self.scan = scan

    def show(self):
        # display current md, need to be located at top level
        return self.__dict__

    def set_scan(self, val):
        self.scan = val + '_method applied'


