"""Independent 3.5 local release; preserve all earlier inputs and releases."""
from package_34 import main

if __name__=='__main__':
    main(version='3.5',label='参数复刻与平铺版',ui_count=38,extra_tests=('tests.test_ae_pattern',),
         web_markers=('AE_COPY_PASTE_AND_FIT_HANDLERS_OK','MIRRORED_DRAG_BOTH_GEOMETRIES_AND_PICKED_SIDE_OK'))
