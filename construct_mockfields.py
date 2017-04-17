import os
import sys
import numpy as np
import glob
import gfs_sublink_utils as gsu
import shutil
import math
import astropy
import astropy.io.fits as pyfits
#import matplotlib
#import matplotlib.pyplot as plt
import scipy
import scipy.ndimage
#import make_color_image
import numpy.random as random
import congrid
import tarfile
import string
import astropy.io.ascii as ascii
from astropy.convolution import *


filters_to_analyze = np.asarray(['hst/acs_f435w','hst/acs_f606w','hst/acs_f775w','hst/acs_f850lp',
                      'hst/wfc3_f105w','hst/wfc3_f125w','hst/wfc3_f160w',
                      'jwst/nircam_f070w', 'jwst/nircam_f090w','jwst/nircam_f115w', 'jwst/nircam_f150w', 
                      'jwst/nircam_f200w', 'jwst/nircam_f277w', 'jwst/nircam_f356w', 'jwst/nircam_f444w', 
                      'hst/wfc3_f140w',
                      'hst/wfc3_f275w', 'hst/wfc3_f336w',
                      'hst/acs_f814w',
                      'jwst/miri_F560W','jwst/miri_F770W','jwst/miri_F1000W','jwst/miri_F1130W',
                      'jwst/miri_F1280W','jwst/miri_F1500W','jwst/miri_F1800W','jwst/miri_F2100W','jwst/miri_F2550W'])

psf_dir = os.path.expandvars('$GFS_PYTHON_CODE/vela-yt-sunrise/kernels')

psf_names = np.asarray(['TinyTim_IllustrisPSFs/F435W_rebin.fits','TinyTim_IllustrisPSFs/F606W_rebin.fits','TinyTim_IllustrisPSFs/F775W_rebin.fits','TinyTim_IllustrisPSFs/F850LP_rebin.fits',
             'TinyTim_IllustrisPSFs/F105W_rebin.fits','TinyTim_IllustrisPSFs/F125W_rebin.fits','TinyTim_IllustrisPSFs/F160W_rebin.fits',
             'WebbPSF_F070W_trunc.fits','WebbPSF_F090W_trunc.fits','WebbPSF_F115W_trunc.fits','WebbPSF_F150W_trunc.fits',
             'WebbPSF_F200W_trunc.fits','WebbPSF_F277W_trunc.fits','WebbPSF_F356W_trunc.fits','WebbPSF_F444W_trunc.fits',
             'TinyTim_IllustrisPSFs/F140W_rebin.fits','TinyTim_IllustrisPSFs/F275W_rebin.fits','TinyTim_IllustrisPSFs/F336W_rebin.fits','TinyTim_IllustrisPSFs/F814W_rebin.fits',
             'WebbPSF_F560W_trunc.fits','WebbPSF_F770W_trunc.fits','WebbPSF_F1000W_trunc.fits','WebbPSF_F1130W_trunc.fits',
             'WebbPSF_F1280W_trunc.fits','WebbPSF_F1500W_trunc.fits','WebbPSF_F1800W_trunc.fits','WebbPSF_F2100W_trunc.fits','WebbPSF_F2550W_trunc.fits'])


psf_pix_arcsec = np.asarray([0.03,0.03,0.03,0.03,0.06,0.06,0.06,0.0317,0.0317,0.0317,0.0317,0.0317,0.0648,0.0648,0.0648,0.06,0.03,0.03,0.03,0.11,0.11,0.11,0.11,0.11,0.11,0.11,0.11,0.11])
psf_fwhm = np.asarray([0.10,0.11,0.12,0.13,0.14,0.17,0.20,0.11,0.11,0.11,0.11,0.12,0.15,0.18,0.25,0.18,0.07,0.08,0.13,
            0.035*5.61,0.035*7.57,0.035*9.90,0.035*11.30,0.035*12.75,0.035*14.96,0.035*17.90,0.035*20.65,0.035*25.11])



#construct real illustris lightcones from individual images

#in parallel, produce estimated Hydro-ART surveys based on matching algorithms -- high-res?


def process_single_filter(data,filname,fil_index,output_dir):

    print('Processing:  ', filname)

    pbi= filters_to_analyze==filname
    this_psf_file=os.path.join(psf_dir,psf_names[pbi][0])
    this_psf_pixsize_arcsec=psf_pix_arcsec[pbi][0]
    this_psf_fwhm=psf_fwhm[pbi][0]
    print('PSF info: ', this_psf_file, this_psf_pixsize_arcsec, this_psf_fwhm)


    full_npix=data['full_npix'][0]
    pixsize_arcsec=data['pixsize_arcsec'][0]

    desired_pixsize_arcsec=this_psf_pixsize_arcsec

    full_fov=full_npix*pixsize_arcsec

    desired_npix=full_fov/desired_pixsize_arcsec

    orig_psf_kernel = pyfits.open(this_psf_file)[0].data ; print(orig_psf_kernel.shape)

    #psf kernel shape must be odd for astropy.convolve??
    if orig_psf_kernel.shape[0] % 2 == 0:
        new_psf_shape = orig_psf_kernel.shape[0]-1
        psf_kernel = congrid.congrid(orig_psf_kernel,(new_psf_shape,new_psf_shape))
    else:
        psf_kernel = orig_psf_kernel
        
    assert( psf_kernel.shape[0] % 2 != 0)


    image_cube = np.zeros((full_npix,full_npix),dtype=np.float64)

    success=[]

    #for bigger files, may need to split by filter first

    for origin_i,origin_j,run_dir,this_npix in zip(data['origin_i'],data['origin_j'],data['run_dir'],data['this_npix']):
        try:
            bblist=pyfits.open(os.path.join(run_dir,'broadbandz.fits'))
            this_cube = bblist['CAMERA0-BROADBAND-NONSCATTER'].data
            bblist.close()
            success.append(True)
        except:
            print('Missing file, ', run_dir)
            success.append(False)
            continue
        i_tc=0
        j_tc=0
        i_tc1=this_npix
        j_tc1=this_npix

        if origin_i < 0:
            i0=0
            i_tc=-1*origin_i
        else:
            i0=origin_i

        if origin_j < 0:
            j0=0
            j_tc=-1*origin_j
        else:
            j0=origin_j

        if i0+this_npix > full_npix:
            i1=full_npix
            i_tc1= full_npix-i0   #this_npix - (i0+this_npix-full_npix)
        else:
            i1=i0+this_npix-i_tc

        if j0+this_npix > full_npix:
            j1=full_npix
            j_tc1= full_npix-j0
        else:
            j1=j0+this_npix-j_tc


        sub_cube1=image_cube[i0:i1,j0:j1]
        this_subcube=this_cube[fil_index,i_tc:i_tc1,j_tc:j_tc1]
        print(run_dir, this_subcube.shape)

        image_cube[i0:i1,j0:j1] = sub_cube1 + this_subcube



    #convolve here
    
    #first, re-grid to desired scale

    new_image=congrid.congrid(image_cube,(desired_npix,desired_npix))
    conv_im = convolve_fft(new_image,psf_kernel,boundary='fill',fill_value=0.0,normalize_kernel=True)


    outname=os.path.join(output_dir,image_filelabel+'_'+filname.replace('/','-')+'.fits')
    print('saving:', outname)

    primary_hdu=pyfits.PrimaryHDU(conv_im)
    primary_hdu.header['FILTER']=filname.replace('/','-')
    
    psf_hdu = pyfits.ImageHDU(psf_kernel)

    output_list=pyfits.HDUList([primary_hdu,psf_hdu])
    output_list.writeto(outname,overwrite=True)
    output_list.close()

    return success


def build_lightcone_images(image_info_file,run_type='images'):

    data=ascii.read(image_info_file)
    print(data)


    #get expected shape
    test_file=os.path.join(data['run_dir'][0],'broadbandz.fits')
    tfo =pyfits.open(test_file)
    print(tfo.info())
    cube=tfo['CAMERA0-BROADBAND-NONSCATTER'].data
    cubeshape=cube.shape
    print(cubeshape)
    auxcube=tfo['CAMERA0-AUX'].data

    filters_hdu = tfo['FILTERS']

    lightcone_dir=os.path.abspath(os.path.dirname(image_info_file))
    print('Constructing lightcone data from: ', lightcone_dir)

    output_dir = os.path.join(lightcone_dir,os.path.basename(image_info_file).rstrip('.txt'))
    print('Saving lightcone outputs in: ', output_dir)
    if not os.path.lexists(output_dir):
        os.mkdir(output_dir)

    success_catalog=os.path.join(output_dir,os.path.basename(image_info_file).rstrip('.txt')+'_success.txt')

    image_filelabel='lightcone_image'

    N_filters = cubeshape[0]

    #N_aux=auxcube.shape[0]
    #aux_cube = np.zeros((N_aux,full_npix,full_npix),dtype=np.float64)



    filters_data=filters_hdu.data

    for i,filname in enumerate(filters_data['filter']):
        success=process_single_filter(data,filname,i,output_dir)
        if i==0:
            success=np.asarray(success)
            newcol=astropy.table.column.Column(data=success,name='success')
            data.add_column(newcol)
            ascii.write(data,output=success_catalog)


    #convert units before saving.. or save both?

    return
