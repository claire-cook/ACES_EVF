
import os, glob
from pathlib import Path

import numpy as np
import pandas as pd
import pylab
import matplotlib.cm as cm
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from astropy.io import fits
from astropy.wcs import WCS
from astropy.table import Table


import matplotlib.pyplot as pl
import matplotlib.colors as mc
from matplotlib.ticker import (MultipleLocator, AutoMinorLocator)
from mpl_toolkits.mplot3d import axes3d, art3d, proj3d
from matplotlib import colors
from matplotlib.colors import Normalize
import matplotlib.cm as cm


from scipy.interpolate import NearestNDInterpolator
from numpy import linspace, array, logspace, sin, cos, pi, arange, sqrt, arctan2, arccos
from adjustText import adjust_text
import matplotlib.patheffects as PathEffects
from astropy.coordinates import Angle, SkyCoord, Longitude
from astropy.nddata.utils import Cutout2D
import astropy.units as u
from astropy.wcs.utils import pixel_to_skycoord
import astropy.io.fits as pyfits


from regions import Regions
import regions
from spectral_cube import SpectralCube
from spectral_cube import Projection

from reproject import reproject_interp

#Paths and definitions
drivepath = '/orange/adamginsburg/ACES/mosaics/cubes/' #Data directory containing cubes
mom0dir = '/orange/adamginsburg/ACES/broadline_sources/EVFs/moments/'#Directory where mom0 maps are stored. Please don't put other things in this directory.
savedir_fits = '/orange/adamginsburg/ACES/broadline_sources/EVFs/ratio_maps/' #Directory where ratio map figures will be saved (with folders in this dir made for each EVF)


EVF_tab = Table.read('/blue/adamginsburg/savannahgramze/ACES_EVF/aces_evf/Filtered_EVFs_table.ecsv')
EVF_reg = Regions.read('/blue/adamginsburg/savannahgramze/ACES_EVF/aces_evf/EVF_reg_list.reg')

vel_range_list = []
delta_l_list  = []
delta_b_list = []
lb_list = []
evf_num = []
for evf in EVF_tab:
    vel_range = (evf['min_v'], evf['max_v'])
    vel_range_list.append(vel_range)
    delta_l_list.append(evf['deltal'])
    delta_b_list.append(evf['deltab'])
    evf_num.append(evf['ID Number'])
    lb=(evf['l'], evf['b'])
    lb_list.append(lb)

#linetracers = ['SiOFAKE', 'CS21FAKE', 'HNCOFAKE']
linetracers = ['CS21', 'H13CN', 'H13COp', 'SiO21', 'SO32', 'SO21', 'HN13C', 'HC3N', 'HNCO_7m12mTP']

#Make and save moment 0 maps for all line tracers
for line in linetracers:
    print("Making moment 0 maps for: ", line, flush=True)
    mom0folder = mom0dir + '{}'.format(line)
    Path(mom0folder).mkdir(parents=True, exist_ok=True) #look for folder for the linetracer mom0 maps, if it doesn't exit, make it
    for file in glob.glob(drivepath + line + '_CubeMosaic.fits', recursive=True):
        data = pyfits.open(file) 
        cube = SpectralCube.read(data)
        data.close()
        cube.allow_huge_operations=True

        for i in range(len(EVF_tab)):
            print("Making moment 0 map for EVF: ", evf_num[i], " at l,b: ", lb_list[i][0], lb_list[i][1], flush=True)
            row = EVF_tab[i]
            EVF_reg = regions.RectangleSkyRegion(SkyCoord(row['l'], row['b'], unit='deg', frame='galactic'), width=row['deltal']*u.deg, height=row['deltab']*u.deg)
            subcube = cube.subcube_from_regions([EVF_reg])
            subcube = subcube.spectral_slab(vel_range_list[i][0]* u.km / u.s, vel_range_list[i][1]* u.km / u.s)
            mom0 = subcube.moment(order=0)

            print("Saving moment 0 map for EVF: ", evf_num[i], " at l,b: ", lb_list[i][0], lb_list[i][1], flush=True)
            mom0.write(mom0folder +f'/EVF_{evf_num[i]}_l{lb_list[i][0]}_b{lb_list[i][1]}_{line}mom0.fits', overwrite=True)
            #mom0.write(mom0folder +f'/l{lb_list[i][0]}_b{lb_list[i][1]}_{line}mom0.fits', overwrite=True)


#Gets array of all the EVFs to make line ratios for
evf_source_names=[]
lb_name_list=[]
i=0
s=0

for idx,lb in enumerate(lb_list):
    lb_name='l' + str(lb[0])+'_b'+str(lb[1])
    evf_source_names.append('evf'+str(evf_num[idx])+'_'+lb_name)
    lb_name_list.append(lb_name)

#This will make and save line tracer ratio maps AS FITS FILES for all EVF sources
noise_threshold = 9*10**(-3) #Jy/beam noise threshold below which we mask in our ratio maps (including any absorption)
s=0
i=0
print("Making ratio maps for all EVF sources", flush=True)
while s<len(evf_source_names): #Iterates through each source
    #Figure out which lines are available for each EVF source
    source=evf_source_names[s]
    lb_name=lb_name_list[s]
    
    lines = linetracers.copy() #array for line names
    mom0paths = [] #array for the source's mom0 maps
    for line in lines: 
        for folder in os.listdir(mom0dir): #goes through line folders (and any other files/folders) in mom0dir
            foldername = os.fsdecode(folder)
            if line in foldername:
                for file in os.listdir(mom0dir+foldername):
                    filename = os.fsdecode(file)
                    if source + '_' in filename: 
                        mom0paths.append(filename)
    
    print(mom0paths)
    lines_avoidredundant = lines.copy() #arrays I'll remove elements from to avoid redundant pairs
    mom0_avoidredundant = mom0paths.copy()
    print("Source: ")
    print(evf_source_names[s])
    
    i=0
    while i<len(lines):
        r=0
        while r<len(lines_avoidredundant):
            if lines[i] == lines_avoidredundant[r]: #don't bother calculating CS-CS, HCN-HCN, etc, ratios
                r+=1
            else: #run everything else
                print(lines[i], "-->", lines_avoidredundant[r])
                #Open mom0 map of line 1:
                mom0path1 = mom0dir + lines[i] + '/' + mom0paths[i]
                print(mom0path1)
                hdul = fits.open(mom0path1)
                sc_line1_moment0 = Projection.from_hdu(hdul) #makes 2D spectral cube object called a "Projection"
                
                #Open mom0 map of line2:
                mom0path2 = mom0dir + lines_avoidredundant[r] + '/' + mom0_avoidredundant[r]
                print(mom0path2)
                hdul = fits.open(mom0path2)
                sc_line2_moment0 = Projection.from_hdu(hdul) #makes 2D spectral cube object called a "Projection"
                
                #Match shapes of 2D moment maps so we can calculate ratios
                sc_line1_moment0_reproject, footprint = reproject_interp(sc_line1_moment0.hdu,sc_line2_moment0.header) #reproject line1 to line2

                #Now that images are same size, compute ratio of moment maps
                ratio = sc_line2_moment0.hdu.data/sc_line1_moment0_reproject

                #Mask pixels (exclude certain values) in the ratio map:
                badpix = pylab.where(sc_line1_moment0_reproject<noise_threshold) # Identify emission below a threshold to mask for line 1
                badpix2 = pylab.where(sc_line2_moment0.hdu.data<noise_threshold)   #Line2 noise and absorption
                ratio[badpix] = np.nan # Mask the ratio map
                ratio[badpix2] = np.nan

                #Check for all-NaN ratio maps
                if np.isnan(np.nanmin(ratio))==True or np.isnan(np.nanmax(ratio))==True:
                    print("!!!!! ALL-NAN RATIO MAP !!!!!!!!!!!!")
                    print("Check mom0 maps for: ", source)
                    print("Potentially problematic maps: ", mom0path1, mom0path2)
                
                #Make and save ratio map .fits file   
                else: 
                    #Make a new .fits file to save ratio maps
                    hdu_ratio = pyfits.PrimaryHDU(data=ratio)
                    ratio_header = hdu_ratio.header
                    mom02header = fits.getheader(mom0path2) #gets the header of the mom0 map we reproject to

                    ratio_header.set('ctype1',"GLON-TAN")
                    ratio_header.set('crval1', mom02header['CRVAL1'])
                    ratio_header.set('cdelt1', mom02header['CDELT1'])
                    ratio_header.set('crpix1', mom02header['CRPIX1'])
                    ratio_header.set('cunit1',"deg" )

                    ratio_header.set('ctype2',"GLAT-TAN")
                    ratio_header.set('crval2', mom02header['CRVAL2'])
                    ratio_header.set('cdelt2', mom02header['CDELT2'])
                    ratio_header.set('crpix2', mom02header['CRPIX2'])
                    ratio_header.set('cunit2', "deg")

                    #Save each ratio map as .fits files
                    Path(savedir_fits+source).mkdir(parents=True, exist_ok=True) #look for folder individual EVF, if it doesn't exit, make it
                    savepath_fits = savedir_fits + source + '/RatioMap_' + lines_avoidredundant[r] + '_' + lines[i] + '_' + source + '.fits'
                    pyfits.writeto(savepath_fits, ratio, ratio_header, overwrite=True)   

                r+=1
        del lines_avoidredundant[0] #remove 1st element each line iteration to avoid redundant runs (if CS-HC3N done, don't do HC3N-CS)
        del mom0_avoidredundant[0]
        i+=1
    print("**************************************", flush=True)

    s+=1

