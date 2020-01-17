import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.ioff()
import matplotlib.gridspec as gridspec
from astropy.io import fits
import emcee
#from schwimmbad import MPIPool
from multiprocessing import Pool
import nirspec_fmp as nsp
import model_fit
import InterpolateModel
import mcmc_utils
import corner
import os
import sys
import time
import copy
import argparse
import json
import ast
import warnings
warnings.filterwarnings("ignore")

##############################################################################################
## This is the script to make the code multiprocessing, using arcparse to pass the arguments
## The code is run with 8 parameters, including Teff, logg, RV, vsini, telluric alpha, and 
## nuisance parameters for wavelength, flux and noise.
##############################################################################################

parser = argparse.ArgumentParser(description="Run the forward-modeling routine for science files",
	usage="run_mcmc_science.py order date_obs sci_data_name tell_data_name data_path tell_path save_to_path lsf priors limits")

#parser.add_argument("source",metavar='src',type=str,
#   default=None, help="source name", nargs="+")

parser.add_argument("order",metavar='o',type=int,
    default=None, help="order", nargs="+")

parser.add_argument("date_obs",metavar='dobs',type=str,
    default=None, help="source name", nargs="+")

parser.add_argument("sci_data_name",metavar='sci',type=str,
    default=None, help="science data name", nargs="+")

parser.add_argument("tell_data_name",metavar='tell',type=str,
    default=None, help="telluric data name", nargs="+")

parser.add_argument("data_path",type=str,
    default=None, help="science data path", nargs="+")

parser.add_argument("tell_path",type=str,
    default=None, help="telluric data path", nargs="+")

parser.add_argument("save_to_path",type=str,
    default=None, help="output path", nargs="+")

#parser.add_argument("lsf",type=float,
#    default=None, help="line spread function", nargs="+")

parser.add_argument("-outlier_rejection",metavar='--rej',type=float,
    default=3.0, help="outlier rejection based on the multiple of standard deviation of the residual; default 3.0")

parser.add_argument("-ndim",type=int,
    default=8, help="number of dimension; default 8")

parser.add_argument("-nwalkers",type=int,
    default=50, help="number of walkers of MCMC; default 50")

parser.add_argument("-step",type=int,
    default=600, help="number of steps of MCMC; default 600")

parser.add_argument("-burn",type=int,
    default=500, help="burn of MCMC; default 500")

parser.add_argument("-moves",type=float,
    default=2.0, help="moves of MCMC; default 2.0")

parser.add_argument("-pixel_start",type=int,
    default=10, help="starting pixel index for the science data; default 10")

parser.add_argument("-pixel_end",type=int,
    default=-40, help="ending pixel index for the science data; default -40")

#parser.add_argument("-alpha_tell",type=float,
#    default=1.0, help="telluric alpha; default 1.0")

parser.add_argument("-applymask",type=bool,
    default=False, help="apply a simple mask based on the STD of the average flux; default is False")

parser.add_argument("-plot_show",type=bool,
    default=False, help="show the MCMC plots; default is False")

parser.add_argument("-coadd",type=bool,
    default=False, help="coadd the spectra; default is False")

parser.add_argument("-coadd_sp_name",type=str,
    default=None, help="name of the coadded spectra")

parser.add_argument("-modelset",type=str,
    default='btsettl08', help="model set; default is btsettl08")

parser.add_argument("-final_mcmc", action='store_true', help="run final mcmc; default False")

args = parser.parse_args()

######################################################################################################
instrument             = 'nirspec'
#source                 = str(args.source[0])
order                  = int(args.order[0])
date_obs               = str(args.date_obs[0])
sci_data_name          = str(args.sci_data_name[0])
tell_data_name         = str(args.tell_data_name[0])
data_path              = str(args.data_path[0])
tell_path              = str(args.tell_path[0])
save_to_path_base      = str(args.save_to_path[0])
ndim, nwalkers, step   = int(args.ndim), int(args.nwalkers), int(args.step)
burn                   = int(args.burn)
moves                  = float(args.moves)
applymask              = args.applymask
pixel_start, pixel_end = int(args.pixel_start), int(args.pixel_end)
#alpha_tell             = float(args.alpha_tell[0])
plot_show              = args.plot_show
coadd                  = args.coadd
outlier_rejection      = float(args.outlier_rejection)
modelset               = str(args.modelset)
final_mcmc             = args.final_mcmc

if final_mcmc:
	save_to_path1  = save_to_path_base + '/init_mcmc'
	save_to_path   = save_to_path_base + '/final_mcmc'

else:
	save_to_path   = save_to_path_base + '/init_mcmc'
	

#####################################

data            = nsp.Spectrum(name=sci_data_name, order=order, path=data_path, applymask=applymask)
tell_data_name2 = tell_data_name + '_calibrated'
tell_sp         = nsp.Spectrum(name=tell_data_name2, order=data.order, path=tell_path, applymask=applymask)

data.updateWaveSol(tell_sp)

if coadd:
	sci_data_name2 = str(args.coadd_sp_name)
	if not os.path.exists(save_to_path):
		os.makedirs(save_to_path)
	data1       = copy.deepcopy(data)
	data2       = nsp.Spectrum(name=sci_data_name2, order=order, path=data_path, applymask=applymask)
	data.coadd(data2, method='pixel')

	plt.figure(figsize=(16,6))
	plt.plot(np.arange(1024),data.flux,'k',
		label='coadd median S/N = {}'.format(np.median(data.flux/data.noise)),alpha=1)
	plt.plot(np.arange(1024),data1.flux,'C0',
		label='{} median S/N = {}'.format(sci_data_name,np.median(data1.flux/data1.noise)),alpha=0.5)
	plt.plot(np.arange(1024),data2.flux,'C1',
		label='{} median S/N = {}'.format(sci_data_name2,np.median(data2.flux/data2.noise)),alpha=0.5)
	plt.plot(np.arange(1024),data.noise,'k',alpha=0.5)
	plt.plot(np.arange(1024),data1.noise,'C0',alpha=0.5)
	plt.plot(np.arange(1024),data2.noise,'C1',alpha=0.5)
	plt.legend()
	plt.xlabel('pixel')
	plt.ylabel('cnts/s')
	plt.minorticks_on()
	plt.savefig(save_to_path+'/coadd_spectrum.png')
	#plt.show()
	plt.close()

sci_data  = data
tell_data = tell_sp 

"""
MCMC run for the science spectra. See the parameters in the makeModel function.

Parameters
----------

sci_data  	: 	sepctrum object
				science data

tell_data 	: 	spectrum object
				telluric data for calibrating the science spectra

priors   	: 	dic
				keys are teff_min, teff_max, logg_min, logg_max, vsini_min, vsini_max, rv_min, rv_max, alpha_min, alpha_max, A_min, A_max, B_min, B_max

Optional Parameters
-------------------

limits 		:	dic
					mcmc limits with the same format as the input priors

ndim 		:	int
				mcmc dimension

nwalkers 	:	int
					number of walkers

	step 		: 	int
					number of steps

	burn 		:	int
					burn for the mcmc

	moves 		: 	float
					stretch parameter for the mcmc. The default is 2.0 based on the emcee package

	pixel_start	:	int
					starting pixel number for the spectra in the MCMC

	pixel_end	:	int
					ending pixel number for the spectra in the MCMC

	alpha_tell	:	float
					power of telluric spectra for estimating the line spread function of the NIRSPEC instrument

	modelset 	:	str
					'btsettl08' or 'phoenixaces' model sets

	save_to_path: 	str
					path to savr the MCMC output				

"""

if save_to_path is not None:
	if not os.path.exists(save_to_path):
		os.makedirs(save_to_path)
else:
	save_to_path = '.'

#if limits is None: limits = priors

data          = copy.deepcopy(sci_data)
tell_sp       = copy.deepcopy(tell_data)
data.updateWaveSol(tell_sp)

# barycentric corrction
barycorr      = nsp.barycorr(data.header).value
#print("barycorr:",barycorr)

## read the input custom mask and priors
lines          = open(save_to_path+'/mcmc_parameters.txt').read().splitlines()
custom_mask    = json.loads(lines[5].split('custom_mask')[1])
priors         = ast.literal_eval(lines[6].split('priors ')[1])

# no logg 5.5 for teff lower than 900
if priors['teff2_min'] < 900: logg_max = 5.0
else: logg_max = 5.5

# limit of the flux nuisance parameter: 5 percent of the median flux
A_const       = 0.05 * abs(np.median(data.flux))

#if modelset == 'btsettl08':
#limits 			=  {
#						'teff1_min':max(priors['teff1_min']-200,500), 'teff1_max':min(priors['teff1_min']+200,3500),
#						'logg1_min':3.5,		'logg1_max':logg_max,
#						'vsini1_min':0.0,	'vsini1_max':100.0,
#						'rv1_min':-200.0,		'rv1_max':200.0,
#						'teff2_min':min(priors['teff2_min']-200,500), 'teff2_max':min(priors['teff2_min']+200,3500),
#						'logg2_min':3.5,		'logg2_max':5.0,
#						'vsini2_min':0.0,	'vsini2_max':70.0,
#						'rv2_min':-200.0,		'rv2_max':200.0,
#						'flux2_scale_min':0.1, 'flux2_scale_max':1.0,
#						'airmass_min':1.0,	    'airmass_max':3.0,							
#						'pwv_min':0.5,	    'pwv_max':20.0,
#						#'alpha_min':0.9,	'alpha_max':1.1,
#						'A_min':-0.01,		'A_max':0.01,
#						'B_min':-0.01,		'B_max':0.01,
#						'N_min':0.99,		'N_max':1.01 			
#					}

## set the limits as a small range 
limits 			=  {
						'teff1_min':max(priors['teff1_min']-200,500), 'teff1_max':min(priors['teff1_min']+200,3500),
						'logg1_min':3.5,		'logg1_max':logg_max,
						'vsini1_min':0.0,	'vsini1_max':100.0,
						'rv1_min':-200.0,		'rv1_max':200.0,
						'teff2_min':min(priors['teff2_min']-200,500), 'teff2_max':min(priors['teff2_min']+200,3500),
						'logg2_min':3.5,		'logg2_max':5.0,
						'vsini2_min':0.0,	'vsini2_max':70.0,
						'rv2_min':-200.0,		'rv2_max':200.0,
						'flux2_scale_min':0.1, 'flux2_scale_max':1.0,
						'airmass_min':1.0,	    'airmass_max':3.0,							
						'pwv_min':0.5,	    'pwv_max':20.0,
						#'alpha_min':0.9,	'alpha_max':1.1,
						'A_min':-0.01,		'A_max':0.01,
						'B_min':-0.01,		'B_max':0.01,
						'N_min':0.99,		'N_max':1.01 			
					}

if modelset == 'phoenixaces':
	limits['teff1_min'] = max(priors['teff1_min']-200,2300) 
	limits['teff1_max'] = max(priors['teff1_max']+200,10000) 
	limits['teff2_min'] = max(priors['teff2_min']-200,2300) 
	limits['teff2_max'] = max(priors['teff2_max']+200,10000) 

if final_mcmc:
	limits['rv_min'] = priors['rv_min'] - 10
	limits['rv_max'] = priors['rv_max'] + 10

## apply a custom mask
data.mask_custom(custom_mask=custom_mask)

## add a pixel label for plotting
length1     = len(data.oriWave)
pixel       = np.delete(np.arange(length1),data.mask)
pixel       = pixel[pixel_start:pixel_end]

### mask the end pixels
data.wave     = data.wave[pixel_start:pixel_end]
data.flux     = data.flux[pixel_start:pixel_end]
data.noise    = data.noise[pixel_start:pixel_end]

tell_sp.wave  = tell_sp.wave[pixel_start:pixel_end]
tell_sp.flux  = tell_sp.flux[pixel_start:pixel_end]
tell_sp.noise = tell_sp.noise[pixel_start:pixel_end]

#if final_mcmc:
#	priors, limits         = mcmc_utils.generate_final_priors_and_limits(sp_type=sp_type, barycorr=barycorr, save_to_path1=save_to_path1)
#else:
#	priors, limits         = mcmc_utils.generate_initial_priors_and_limits(sp_type=sp_type)
#print(priors, limits)

lsf     = tell_sp.header['LSF']
airmass = data.header['AIRMASS']
pwv     = tell_sp.header['PWV_FIT']

#if lsf is None:
#	lsf           = nsp.getLSF(tell_sp,alpha=alpha_tell, test=True, save_path=save_to_path)


# log file
log_path = save_to_path + '/mcmc_parameters.txt'

file_log = open(log_path,"w+")
file_log.write("data_path {} \n".format(data.path))
file_log.write("tell_path {} \n".format(tell_sp.path))
file_log.write("data_name {} \n".format(data.name))
file_log.write("tell_name {} \n".format(tell_sp.name))
file_log.write("order {} \n".format(data.order))
file_log.write("custom_mask {} \n".format(custom_mask))
file_log.write("priors {} \n".format(priors))
file_log.write("ndim {} \n".format(ndim))
file_log.write("nwalkers {} \n".format(nwalkers))
file_log.write("step {} \n".format(step))
file_log.write("burn {} \n".format(burn))
file_log.write("pixel_start {} \n".format(pixel_start))
file_log.write("pixel_end {} \n".format(pixel_end))
file_log.write("barycorr {} \n".format(barycorr))
file_log.write("lsf {} \n".format(lsf))
file_log.write("airmass_init {} \n".format(airmass))
file_log.write("pwv_init {} \n".format(pwv))
file_log.close()


#########################################################################################
## for multiprocessing
#########################################################################################
flux2_scale = 0.8
#priors =  {
#				'teff1_min':self.teff-200, 'teff1_max':self.teff+200,
#				'logg1_min':logg_min,		'logg1_max':logg_max,
#				'vsini1_min':vsini_min,	'vsini1_max':vsini_max,
#				'rv1_min':rv_min,		'rv1_max':rv_max,
#				'teff2_min':self.teff2-200, 'teff2_max':self.teff2+200,
#				'logg2_min':logg_min,		'logg2_max':logg_max,
#				'vsini2_min':vsini_min,	'vsini_max':vsini_max,
#				'rv2_min':rv_min,		'rv_max':rv_max,
#				'flux2_scale_min':flux2_scale-0.1, 'flux2_scale_max':flux2_scale+0.1,
#				'airmass_min':0.9,	    'airmass_max':1.1,							
#				'pwv_min':0.9,	    'pwv_max':1.1,
#				#'alpha_min':0.9,	'alpha_max':1.1,
#				'A_min':-0.01,		'A_max':0.01,
#				'B_min':-0.01,		'B_max':0.01,
#				'N_min':0.99,		'N_max':1.01 			
#				}


def lnlike(theta, data, lsf):
	"""
	Log-likelihood, computed from chi-squared.

	Parameters
	----------
	theta
	lsfp
	data

	Returns
	-------
	-0.5 * chi-square + sum of the log of the noise

	"""

	## Parameters MCMC
	teff1, logg1, vsini1, rv1, teff2, logg2, vsini2, rv2, flux2_scale, airmass, pwv, A, B, N = theta #N noise prefactor

	model = model_fit.makeModel(teff1, logg1, 0.0, vsini1, rv1, 1.0, B, A, airmass=airmass, pwv=pwv,
		lsf=lsf, order=data.order, data=data, modelset=modelset, binary=True,
		teff2=teff2, logg2=logg2, rv2=rv2, vsini2=vsini2, flux2_scale=flux2_scale)

	chisquare = nsp.chisquare(data, model)/N**2

	return -0.5 * (chisquare + np.sum(np.log(2*np.pi*(data.noise*N)**2)))

def lnprior(theta, limits=limits):
	"""
	Specifies a flat prior
	"""
	## Parameters for theta
	teff1, logg1, vsini1, rv1, teff2, logg2, vsini2, rv2, flux2_scale, airmass, pwv, A, B, N = theta

	if  limits['teff1_min']       < teff1       < limits['teff1_max'] \
	and limits['logg1_min']       < logg1       < limits['logg1_max'] \
	and limits['vsini1_min']      < vsini1      < limits['vsini1_max']\
	and limits['rv1_min']         < rv1         < limits['rv1_max']   \
	and limits['teff2_min']       < teff2       < limits['teff2_max'] \
	and limits['logg2_min']       < logg2       < limits['logg2_max'] \
	and limits['vsini2_min']      < vsini2      < limits['vsini2_max']\
	and limits['rv2_min']         < rv2         < limits['rv2_max']   \
	and limits['flux2_scale_min'] < flux2_scale < limits['flux2_scale_max']\
	and limits['airmass_min']     < airmass     < limits['airmass_max']\
	and limits['pwv_min']         < pwv         < limits['pwv_max']\
	and limits['A_min']           < A           < limits['A_max']\
	and limits['B_min']           < B           < limits['B_max']\
	and limits['N_min']           < N           < limits['N_max']:
		return 0.0

	return -np.inf

def lnprob(theta, data ,lsf):
		
	lnp = lnprior(theta)
		
	if not np.isfinite(lnp):
		return -np.inf
		
	return lnp + lnlike(theta, data, lsf)

pos = [np.array([	priors['teff1_min']   + (priors['teff1_max']   - priors['teff1_min'] ) * np.random.uniform(), 
					priors['logg1_min']   + (priors['logg1_max']   - priors['logg1_min'] ) * np.random.uniform(), 
					priors['vsini1_min']  + (priors['vsini1_max']  - priors['vsini1_min']) * np.random.uniform(),
					priors['rv1_min']     + (priors['rv1_max']     - priors['rv1_min']   ) * np.random.uniform(),
					priors['teff2_min']   + (priors['teff2_max']   - priors['teff2_min'] ) * np.random.uniform(), 
					priors['logg2_min']   + (priors['logg2_max']   - priors['logg2_min'] ) * np.random.uniform(), 
					priors['vsini2_min']  + (priors['vsini2_max']  - priors['vsini2_min']) * np.random.uniform(),
					priors['rv2_min']     + (priors['rv2_max']     - priors['rv2_min']   ) * np.random.uniform(),
					priors['flux2_scale_min'] + (priors['flux2_scale_max'] - priors['flux2_scale_min'] ) * np.random.uniform(),   
					priors['airmass_min'] + (priors['airmass_max']- priors['airmass_min']) * np.random.uniform(),
					priors['pwv_min']     + (priors['pwv_max']    - priors['pwv_min'])     * np.random.uniform(),
					priors['A_min']       + (priors['A_max']      - priors['A_min'])       * np.random.uniform(),
					priors['B_min']       + (priors['B_max']      - priors['B_min'])       * np.random.uniform(),
					priors['N_min']       + (priors['N_max']      - priors['N_min'])       * np.random.uniform()]) for i in range(nwalkers)]

## multiprocessing

with Pool() as pool:
	sampler = emcee.EnsembleSampler(nwalkers, ndim, lnprob, args=(data, lsf), a=moves, pool=pool)
	time1 = time.time()
	sampler.run_mcmc(pos, step, progress=True)
	time2 = time.time()

print('total time: ',(time2-time1)/60,' min.')
print("Mean acceptance fraction: {0:.3f}".format(np.mean(sampler.acceptance_fraction)))
print(sampler.acceptance_fraction)

np.save(save_to_path + '/sampler_chain', sampler.chain[:, :, :])

samples = sampler.chain[:, :, :].reshape((-1, ndim))

np.save(save_to_path + '/samples', samples)

# create walker plots
sampler_chain = np.load(save_to_path + '/sampler_chain.npy')
samples = np.load(save_to_path + '/samples.npy')

ylabels = [	"$T_{eff_{1}} (K)$","$log \, g_{1}$(dex)","$vsin \, i_{1}(km/s)$","$RV_{1}(km/s)$",
			"$T_{eff_{2}} (K)$","$log \, g_{2}$(dex)","$vsin \, i_{2}(km/s)$","$RV_{2}(km/s)$",
			"$C_{F_{2}}$","airmass", "pwv (mm)",
			"$C_{F_{\lambda}}$ (cnt/s)","$C_{\lambda}$($\AA$)","$C_{noise}$"]

## create walker plots
plt.rc('font', family='sans-serif')
plt.tick_params(labelsize=30)
fig = plt.figure(tight_layout=True, figsize=(16,16))
gs  = gridspec.GridSpec(ndim, 1)
gs.update(hspace=0.1)

for i in range(ndim):
	ax = fig.add_subplot(gs[i, :])
	for j in range(nwalkers):
		ax.plot(np.arange(1,int(step+1)), sampler_chain[j,:,i],'k',alpha=0.2)
		ax.set_ylabel(ylabels[i])
fig.align_labels()
plt.minorticks_on()
plt.xlabel('nstep')
plt.savefig(save_to_path+'/walker.png', dpi=300, bbox_inches='tight')
if plot_show:
	plt.show()
plt.close()

# create array triangle plots
triangle_samples = sampler_chain[:, burn:, :].reshape((-1, ndim))
#print(triangle_samples.shape)

# create the final spectra comparison
teff1_mcmc, logg1_mcmc, vsini1_mcmc, rv1_mcmc, teff2_mcmc, logg2_mcmc, vsini2_mcmc, rv2_mcmc, flux2_scale_mcmc, \
			airmass_mcmc, pwv_mcmc, A_mcmc, B_mcmc, N_mcmc = map(lambda v: (v[1], v[2]-v[1], v[1]-v[0]), 
			zip(*np.percentile(triangle_samples, [16, 50, 84], axis=0)))

# add the summary to the txt file
log_path = save_to_path + '/mcmc_parameters.txt'
file_log = open(log_path,"a")
file_log.write("*** Below is the summary *** \n")
file_log.write("total_time {} min\n".format(str((time2-time1)/60)))
file_log.write("mean_acceptance_fraction {0:.3f} \n".format(np.mean(sampler.acceptance_fraction)))
file_log.write("teff1_mcmc {} K\n".format(str(teff1_mcmc)))
file_log.write("logg1_mcmc {} dex (cgs)\n".format(str(logg1_mcmc)))
file_log.write("vsini1_mcmc {} km/s\n".format(str(vsini1_mcmc)))
file_log.write("rv1_mcmc {} km/s\n".format(str(rv1_mcmc)))
file_log.write("teff2_mcmc {} K\n".format(str(teff2_mcmc)))
file_log.write("logg2_mcmc {} dex (cgs)\n".format(str(logg2_mcmc)))
file_log.write("vsini2_mcmc {} km/s\n".format(str(vsini2_mcmc)))
file_log.write("rv2_mcmc {} km/s\n".format(str(rv2_mcmc)))
file_log.write("flux2_scale_mcmc {}\n".format(str(flux2_scale_mcmc)))
file_log.write("airmass_mcmc {}\n".format(str(airmass_mcmc)))
file_log.write("pwv_mcmc {}\n".format(str(pwv_mcmc)))
file_log.write("A_mcmc {}\n".format(str(A_mcmc)))
file_log.write("B_mcmc {}\n".format(str(B_mcmc)))
file_log.write("N_mcmc {}\n".format(str(N_mcmc)))
file_log.close()

# log file
log_path2 = save_to_path + '/mcmc_result.txt'

file_log2 = open(log_path2,"w+")
file_log2.write("teff1_mcmc {} K\n".format(str(teff1_mcmc)))
file_log2.write("logg1_mcmc {} dex (cgs)\n".format(str(logg1_mcmc)))
file_log2.write("vsini1_mcmc {} km/s\n".format(str(vsini1_mcmc)))
file_log2.write("rv1_mcmc {} km/s\n".format(str(rv1_mcmc)))
file_log2.write("teff2_mcmc {} K\n".format(str(teff2_mcmc)))
file_log2.write("logg2_mcmc {} dex (cgs)\n".format(str(logg2_mcmc)))
file_log2.write("vsini2_mcmc {} km/s\n".format(str(vsini2_mcmc)))
file_log2.write("rv2_mcmc {} km/s\n".format(str(rv2_mcmc)))
file_log2.write("flux2_scale_mcmc {}\n".format(str(flux2_scale_mcmc)))
file_log2.write("airmass_mcmc {}\n".format(str(airmass_mcmc)))
file_log2.write("pwv_mcmc {}\n".format(str(pwv_mcmc)))
file_log2.write("A_mcmc {}\n".format(str(A_mcmc)))
file_log2.write("B_mcmc {}\n".format(str(B_mcmc)))
file_log2.write("N_mcmc {}\n".format(str(N_mcmc)))
file_log2.write("teff1_mcmc_e {}\n".format(str(max(abs(teff1_mcmc[1]), abs(teff1_mcmc[2])))))
file_log2.write("logg1_mcmc_e {}\n".format(str(max(abs(logg1_mcmc[1]), abs(logg1_mcmc[2])))))
file_log2.write("vsini1_mcmc_e {}\n".format(str(max(abs(vsini1_mcmc[1]), abs(vsini1_mcmc[2])))))
file_log2.write("rv1_mcmc_e {}\n".format(str(max(abs(rv1_mcmc[1]), abs(rv1_mcmc[2])))))
file_log2.write("teff2_mcmc_e {}\n".format(str(max(abs(teff2_mcmc[1]), abs(teff2_mcmc[2])))))
file_log2.write("logg2_mcmc_e {}\n".format(str(max(abs(logg2_mcmc[1]), abs(logg2_mcmc[2])))))
file_log2.write("vsini2_mcmc_e {}\n".format(str(max(abs(vsini2_mcmc[1]), abs(vsini2_mcmc[2])))))
file_log2.write("rv2_mcmc_e {}\n".format(str(max(abs(rv2_mcmc[1]), abs(rv2_mcmc[2])))))
file_log2.write("flux2_scale_mcmc_e {}\n".format(str(max(abs(flux2_scale_mcmc[1]), abs(flux2_scale_mcmc[2])))))
file_log2.write("airmass_mcmc_e {}\n".format(str(max(abs(airmass_mcmc[1]), abs(airmass_mcmc[2])))))
file_log2.write("pwv_mcmc_e {}\n".format(str(max(abs(pwv_mcmc[1]), abs(pwv_mcmc[2])))))
file_log2.write("N_mcmc_e {}\n".format(str(max(abs(N_mcmc[1]), abs(N_mcmc[2])))))
file_log2.close()

triangle_samples[:,3] += barycorr
triangle_samples[:,7] += barycorr

## triangular plots
plt.rc('font', family='sans-serif')
fig = corner.corner(triangle_samples, 
	labels=ylabels,
	truths=[teff1_mcmc[0], 
	logg1_mcmc[0],
	vsini1_mcmc[0], 
	rv1_mcmc[0]+barycorr, 
	teff2_mcmc[0], 
	logg2_mcmc[0],
	vsini2_mcmc[0], 
	rv2_mcmc[0]+barycorr, 
	flux2_scale_mcmc[0],
	airmass_mcmc[0],
	pwv_mcmc[0],
	A_mcmc[0],
	B_mcmc[0],
	N_mcmc[0]],
	quantiles=[0.16, 0.84],
	label_kwargs={"fontsize": 20})
plt.minorticks_on()
fig.savefig(save_to_path+'/triangle.png', dpi=300, bbox_inches='tight')
if plot_show:
	plt.show()
plt.close()

teff1        = teff1_mcmc[0]
logg1        = logg1_mcmc[0]
z            = 0.0
vsini1       = vsini1_mcmc[0]
rv1          = rv1_mcmc[0]
teff2        = teff2_mcmc[0]
logg2        = logg2_mcmc[0]
vsini2       = vsini2_mcmc[0]
rv2          = rv2_mcmc[0]
flux2_scale  = flux2_scale_mcmc[0]
airmass      = airmass_mcmc[0]
pwv          = pwv_mcmc[0]
A            = A_mcmc[0]
B            = B_mcmc[0]
N            = N_mcmc[0]

## new plotting model 
## read in a model
model        = nsp.Model(teff=teff1, logg=logg1, feh=z, order=data.order, modelset=modelset, instrument=instrument)

# apply vsini
model.flux   = nsp.broaden(wave=model.wave, flux=model.flux, vbroad=vsini1, rotate=True)    
# apply rv (including the barycentric correction)
model.wave   = nsp.rvShift(model.wave, rv=rv1)

model1       = copy.deepcopy(model)

## secondary component
model2       = nsp.Model(teff=teff2, logg=logg2, feh=z, order=order, modelset=modelset, instrument=instrument)
# apply vsini
model2.flux  = nsp.broaden(wave=model2.wave, flux=model2.flux, vbroad=vsini2, rotate=True, gaussian=False)
# apply rv (including the barycentric correction)
model2.wave  = nsp.rvShift(model2.wave, rv=rv2)
# linearly interpolate the model2 onto the model1 grid
from scipy.interpolate import interp1d
fit = interp1d(model2.wave, model2.flux)
select_wavelength = np.where( (model.wave < model2.wave[-1]) & (model.wave > model2.wave[0]) )
model.flux = model.flux[select_wavelength]
model.wave = model.wave[select_wavelength]

# combine the models together and scale the secondary flux
model.flux += flux2_scale * fit(model.wave)

model_notell = copy.deepcopy(model)
# apply telluric
model        = nsp.applyTelluric(model=model, airmass=airmass, pwv=pwv)
# NIRSPEC LSF
model.flux   = nsp.broaden(wave=model.wave, flux=model.flux, vbroad=lsf, rotate=False, gaussian=True)
# wavelength offset
model.wave        += B
	
# integral resampling
model.flux   = np.array(nsp.integralResample(xh=model.wave, yh=model.flux, xl=data.wave))
model.wave   = data.wave

# contunuum correction
model, cont_factor = nsp.continuum(data=data, mdl=model, prop=True)

# NIRSPEC LSF
model_notell.flux  = nsp.broaden(wave=model_notell.wave, flux=model_notell.flux, vbroad=lsf, rotate=False, gaussian=True)
model1.flux        = nsp.broaden(wave=model1.wave, flux=model1.flux, vbroad=lsf, rotate=False, gaussian=True)
model2.flux        = flux2_scale * nsp.broaden(wave=model2.wave, flux=model2.flux, vbroad=lsf, rotate=False, gaussian=True)

# wavelength offset
model_notell.wave += B
model1.wave       += B
model2.wave       += B

# integral resampling
model_notell.flux  = np.array(nsp.integralResample(xh=model_notell.wave, yh=model_notell.flux, xl=data.wave))
model_notell.wave  = data.wave
model_notell.flux *= cont_factor

model1.flux  = np.array(nsp.integralResample(xh=model1.wave, yh=model1.flux, xl=data.wave))
model1.wave  = data.wave
model1.flux *= cont_factor

model2.flux  = np.array(nsp.integralResample(xh=model2.wave, yh=model2.flux, xl=data.wave))
model2.wave  = data.wave
model2.flux *= cont_factor

# flux offset
model.flux        += A
model_notell.flux += A

model1.flux        += A
model2.flux        += A


# include fringe pattern
#model.flux        *= (1 + amp * np.sin(freq * (model.wave - phase)))
#model_notell.flux *= (1 + amp * np.sin(freq * (model.wave - phase)))

fig = plt.figure(figsize=(16,6))
ax1 = fig.add_subplot(111)
plt.rc('font', family='sans-serif')
plt.tick_params(labelsize=15)
ax1.plot(model.wave, model.flux, color='C3', linestyle='-', label='binary model',alpha=0.8)
ax1.plot(model_notell.wave,model_notell.flux, color='C0', linestyle='-', label='model no telluric',alpha=0.8)
ax1.plot(data.wave,data.flux,'k-',
	label='data',alpha=0.5)
ax1.plot(data.wave,data.flux-model.flux,'k-',alpha=0.8)
plt.fill_between(data.wave,-data.noise*N,data.noise*N,facecolor='C0',alpha=0.5)
plt.axhline(y=0,color='k',linestyle='-',linewidth=0.5)
plt.ylim(-np.max(np.append(np.abs(data.noise),np.abs(data.flux-model.flux)))*1.2,np.max(data.flux)*1.2)
plt.ylabel("Flux ($cnts/s$)",fontsize=15)
plt.xlabel("$\lambda$ ($\AA$)",fontsize=15)
plt.figtext(0.89,0.85,str(data.header['OBJECT'])+' '+data.name+' O'+str(data.order),
	color='k',
	horizontalalignment='right',
	verticalalignment='center',
	fontsize=15)
plt.figtext(0.89,0.82,"$Primary Teff \, {0}^{{+{1}}}_{{-{2}}}/ logg \, {3}^{{+{4}}}_{{-{5}}}/ en \, 0.0/ vsini \, {6}^{{+{7}}}_{{-{8}}}/ RV \, {9}^{{+{10}}}_{{-{11}}}$".format(\
	round(teff1_mcmc[0]),
	round(teff1_mcmc[1]),
	round(teff1_mcmc[2]),
	round(logg1_mcmc[0],1),
	round(logg1_mcmc[1],3),
	round(logg1_mcmc[2],3),
	round(vsini1_mcmc[0],2),
	round(vsini1_mcmc[1],2),
	round(vsini1_mcmc[2],2),
	round(rv1_mcmc[0]+barycorr,2),
	round(rv1_mcmc[1],2),
	round(rv1_mcmc[2],2)),
	color='C0',
	horizontalalignment='right',
	verticalalignment='center',
	fontsize=12)
plt.figtext(0.89,0.79,"$Secondary Teff \, {0}^{{+{1}}}_{{-{2}}}/ logg \, {3}^{{+{4}}}_{{-{5}}}/ en \, 0.0/ vsini \, {6}^{{+{7}}}_{{-{8}}}/ RV \, {9}^{{+{10}}}_{{-{11}}}$".format(\
	round(teff2_mcmc[0]),
	round(teff2_mcmc[1]),
	round(teff2_mcmc[2]),
	round(logg2_mcmc[0],1),
	round(logg2_mcmc[1],3),
	round(logg2_mcmc[2],3),
	round(vsini2_mcmc[0],2),
	round(vsini2_mcmc[1],2),
	round(vsini2_mcmc[2],2),
	round(rv2_mcmc[0]+barycorr,2),
	round(rv2_mcmc[1],2),
	round(rv2_mcmc[2],2)),
	color='C0',
	horizontalalignment='right',
	verticalalignment='center',
	fontsize=12)
plt.figtext(0.89,0.76,r"$\chi^2$ = {}, DOF = {}".format(\
	round(nsp.chisquare(data,model)), round(len(data.wave-ndim)/3)),
color='k',
horizontalalignment='right',
verticalalignment='center',
fontsize=12)
plt.minorticks_on()

ax2 = ax1.twiny()
ax2.plot(pixel, data.flux, color='w', alpha=0)
ax2.set_xlabel('Pixel',fontsize=15)
ax2.tick_params(labelsize=15)
ax2.set_xlim(pixel[0], pixel[-1])
ax2.minorticks_on()
	
#plt.legend()
plt.savefig(save_to_path + '/spectrum.png', dpi=300, bbox_inches='tight')
if plot_show:
	plt.show()
plt.close()

fig = plt.figure(figsize=(16,6))
ax1 = fig.add_subplot(111)
plt.rc('font', family='sans-serif')
plt.tick_params(labelsize=15)
ax1.plot(model.wave, model.flux, color='C3', linestyle='-', label='binary model',alpha=0.8)
ax1.plot(model1.wave, model1.flux, color='goldenrod', linestyle='-', label='primary model',alpha=0.8)
ax1.plot(model2.wave, model2.flux, color='forestgreen', linestyle='-', label='secondary model',alpha=0.8)
ax1.plot(model_notell.wave,model_notell.flux, color='C0', linestyle='-', label='binary model no telluric',alpha=0.8)
ax1.plot(data.wave,data.flux,'k-',
	label='data',alpha=0.5)
ax1.plot(data.wave,data.flux-model.flux,'k-',alpha=0.8)
plt.fill_between(data.wave,-data.noise*N,data.noise*N,facecolor='C0',alpha=0.5)
plt.axhline(y=0,color='k',linestyle='-',linewidth=0.5)
plt.ylim(-np.max(np.append(np.abs(data.noise),np.abs(data.flux-model.flux)))*1.2,np.max(data.flux)*1.2)
plt.ylabel("Flux ($cnts/s$)",fontsize=15)
plt.xlabel("$\lambda$ ($\AA$)",fontsize=15)
plt.figtext(0.89,0.85,str(data.header['OBJECT'])+' '+data.name+' O'+str(data.order),
	color='k',
	horizontalalignment='right',
	verticalalignment='center',
	fontsize=15)
plt.figtext(0.89,0.82,"$Primary Teff \, {0}^{{+{1}}}_{{-{2}}}/ logg \, {3}^{{+{4}}}_{{-{5}}}/ en \, 0.0/ vsini \, {6}^{{+{7}}}_{{-{8}}}/ RV \, {9}^{{+{10}}}_{{-{11}}}$".format(\
	round(teff1_mcmc[0]),
	round(teff1_mcmc[1]),
	round(teff1_mcmc[2]),
	round(logg1_mcmc[0],1),
	round(logg1_mcmc[1],3),
	round(logg1_mcmc[2],3),
	round(vsini1_mcmc[0],2),
	round(vsini1_mcmc[1],2),
	round(vsini1_mcmc[2],2),
	round(rv1_mcmc[0]+barycorr,2),
	round(rv1_mcmc[1],2),
	round(rv1_mcmc[2],2)),
	color='goldenrod',
	horizontalalignment='right',
	verticalalignment='center',
	fontsize=12)
plt.figtext(0.89,0.79,"$Secondary Teff \, {0}^{{+{1}}}_{{-{2}}}/ logg \, {3}^{{+{4}}}_{{-{5}}}/ en \, 0.0/ vsini \, {6}^{{+{7}}}_{{-{8}}}/ RV \, {9}^{{+{10}}}_{{-{11}}}$".format(\
	round(teff2_mcmc[0]),
	round(teff2_mcmc[1]),
	round(teff2_mcmc[2]),
	round(logg2_mcmc[0],1),
	round(logg2_mcmc[1],3),
	round(logg2_mcmc[2],3),
	round(vsini2_mcmc[0],2),
	round(vsini2_mcmc[1],2),
	round(vsini2_mcmc[2],2),
	round(rv2_mcmc[0]+barycorr,2),
	round(rv2_mcmc[1],2),
	round(rv2_mcmc[2],2)),
	color='forestgreen',
	horizontalalignment='right',
	verticalalignment='center',
	fontsize=12)
plt.figtext(0.89,0.76,r"$\chi^2$ = {}, DOF = {}".format(\
	round(nsp.chisquare(data,model)), round(len(data.wave-ndim)/3)),
color='k',
horizontalalignment='right',
verticalalignment='center',
fontsize=12)
plt.minorticks_on()
plt.legend()
ax2 = ax1.twiny()
ax2.plot(pixel, data.flux, color='w', alpha=0)
ax2.set_xlabel('Pixel',fontsize=15)
ax2.tick_params(labelsize=15)
ax2.set_xlim(pixel[0], pixel[-1])
ax2.minorticks_on()
#plt.legend()
plt.savefig(save_to_path + '/spectrum_binary.png', dpi=300, bbox_inches='tight')
if plot_show:
	plt.show()
plt.close()