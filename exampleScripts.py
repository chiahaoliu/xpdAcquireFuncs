#example script for collecting time-series data.

get_dark_images()
get_calibration('Ag_bearate',0.)
       #do calibration and save cfg file
load_calibration()
new_sample('Ag_bearate',experimenters=['Tim','Simon'])

# keeps collecting indefinitely
#fixme code to open filter/shutter
want_to_run = True
while want_to_run:
    get_light_image(scan_time=5.0)
# fixme code to close filter/shutter

# keeps collecting for fixed length of time
#fixme code to open filter/shutter
while timenow < end-time:
    get_light_image(scan_time=5.0)
# fixme code to close filter/shutter
