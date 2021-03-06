import copy
import os, argparse
import sys,glob
import shutil
import subprocess
import time
import math
import numpy as np
import pdb
import random
from bolshoireader import bolshoireader

# This is a script to allow you to run the GIDGET code with
# a wide variety of systematically varied parameters. The functions here are described
# in some detail, but if you skip to the end of the script, there are plenty of 
# examples of what you can run from the command line, e.g.
#  $ python exper.py ex1
# will execute the example used in the README file.


t0=time.time()
allModels={} # a global dictionary of all experiments created.
allProcs=[] # a global list of all processes we've started
allStartTimes=[] # a global list of the start times of all of these processes


globalBolshoiReader = bolshoireader('rf_registry4.txt',3.0e11,3.0e14, os.environ['GIDGETDIR']+'/bolshoi/')
bolshoiSize =  len(globalBolshoiReader.keys)

def HowManyStillRunning(procs):
    ''' Given a list of processes created with subprocess.Popen, (each of which
          in this case will be a single run of the gidget code), count up how
          many of those runs are still going.'''
    nStillRunning=0
    for proc in procs:
        if(proc.poll()==None):
            nStillRunning+=1
    return nStillRunning 

def successCode(filename):
    ''' Given a file assumed to contain the standard error output of
    a run of the gidget code, return 0 for success (file is empty)
    1 for a time step below floor result, 2 for a problem with Qst,
    3 for a rejected accr. history, or 4 for a miscellaneous error code.  '''
    if (not os.path.exists(filename)):
      return -1 # if the file *stde.txt doesn't exist, this particular run has not been started.

    if os.stat(filename).st_size == 0:
      return 0 # the *_stde.txt file is empty, i.e. there were no errors (so far) for this run

    with open(filename,'r') as f:
        contents = f.read()
        if 'floor' in contents:
            return 1 # the time step has gotten very small. Typically
                     # this is caused by 1 cell in the gas column density
                     # distribution becoming very small.
        if 'Qst' in contents:  
            return 2 # a spike in the stellar column density distribution
                     # which in turn causes an interpolation error
        if 'merger' in contents:
            return 3 # accretion history rejected because of a merger
    return 4 # none of the most common types of failures
    

class experiment:
    ''' This class is a container to generate and store the necessary information to run
         a series of GIDGET models with parameters varied in a systematic way.'''
    def __init__(self,name):
        ''' All we need here is a name. This will be the directory containing and the prefix for
             all files created in all the GIDGET runs produced as part of this experiment.'''
        # fiducial model
        self.p=[name,200,1.5,.01,4.0, \
                1,1,.01,1,10, \
                220.0,20.0,7000.0,2.5,.5, \
                1.0,2.0,5000.0,int(1e9),1.0e-3, \
                1.0,-2.0/3.0,0,.5,2.0, \
                2.0,0,0.0,1.5,1, \
                2.0,1.0,1.0e12,5.0,3.0, \
                0,2.0,-1.0,2.5,0.0, \
                0.54,0.1,200,.30959,0.38, \
                -0.25,1.0,1.0,0.3,1.0, \
                0,0.0,.1,.03,2.0, \
                .002,1.0,1.0,0.3,0.0,.054,0.0,0.0, -1.0/3.0, 10.0, 2.0, 1.0e12, \
                0.1, 2.0, 2.0, 1.4, 0.5, 1.0, -1.0, 1.0, 0.5]
        self.p_orig=self.p[:] # store a copy of p, possibly necessary later on.
        self.pl=[self.p[:]] # define a 1-element list containing a copy of p.
        # store some keys and the position to which they correspond in the p array

        # When adding new variables, put them /before/ bolshoiWeight, leaving bolshoiWeight as the final
        # element of this list!
        self.names=['name','nx','eta','epsff','tauHeat', \
                'analyticQ','cosmologyOn','xmin','NActive','NPassive', \
                'vphiR','R','gasTemp','Qlim','fg0', \
                'phi0','zstart','tmax','stepmax','TOL', \
                'muNorm','muColScaling','b','innerPowerLaw','softening', \
                'diskScaleLength','whichAccretionHistory','alphaMRI','thickness','migratePassive', \
                'fixedQ','kappaMetals','Mh0','minSigSt','NChanges', \
                'dbg','accScaleLength','zquench','zrelax','xiREC', \
                'RfREC','deltaOmega','Noutputs','accNorm','accAlphaZ', \
                'accAlphaMh','accCeiling','fscatter','invMassRatio','fcool', \
                'whichAccretionProfile','alphaAccretionProfile','widthAccretionProfile','fH2Min','tDepH2SC', \
                'ZIGM','fg0mult','ZIGMfac','chiZslope','deltaBeta','yREC','concentrationRandomFactor','muFgScaling', 'muMhScaling', 'ksuppress', 'kpower', 'MQuench', \
                'epsquench', 'muQuench', 'stScaleReduction', 'gaScaleReduction', 'ZMix', 'energyInjectionFactor', 'CloudHeatingRate', 'AccretionHeatingRate', 'bolshoiWeight']
        assert len(self.p)==len(self.names)
        self.keys={}
        ctr=0
        for n in self.names:
            self.keys[n]=ctr
            ctr=ctr+1
        self.expName=name
        self.covariables=np.zeros(len(self.p),int)

        # store the location of various expected subdirectories in the gidget distribution.
        #self.base=os.getcwd() # Assume we are in the base directory - alter this to /path/to/gidget/directory if necessary
        self.base = os.environ['GIDGETDIR']
        self.src=self.base+'/src'
        self.analysis=self.base+'/analysis'
        self.bin=self.base+'/bin'
        self.out=self.base+'/output'
        self.xgrid=self.base+'/xgrid'

        allModels[name] = self
       
    def changeName(self,newName):
        ''' If this object is copied to form the starting point for a separate experiment,
            the self.expName, the names of each GIDGET run, and the entry in allModels will
            need to be updated. This method takes care of all of these tasks.'''
        oldName = self.expName

        self.p[0] = newName
        self.p_orig[0] = newName
        for p in self.pl:
            p[0] = newName + p[0][len(oldName):] # new prefix + old suffixes
        self.expName = newName
        allModels[newName] = self
 
    def vary(self,name,mmin,mmax,n,log,cov=0):
        '''Set up to vary a particular parameter, name, over the
        range [mmin,mmax] with n steps spaced linearly if log=0 or
        logarithmically if log=1. The cov flag means that all variables
        with the same value of cov, e.g. accScaleLength and whichAccretionHistory,
        will be varied together rather than independently. '''
        if(n>1 and log==0):
            self.p[self.keys[name]]=[mmin + (mmax-mmin)*type(self.p_orig[self.keys[name]])(i)/type(self.p_orig[self.keys[name]])(n-1) for i in range(n)]
        elif(n>1 and log==1 and mmin!=0 and mmin!=0.0):
            rat = (float(mmax)/float(mmin))
            typ = type(self.p_orig[self.keys[name]])
            self.p[self.keys[name]]=[typ(float(mmin) * (rat)**(float(i)/float(n-1))) for i in range(n)]
        elif(n==1):
            self.p[self.keys[name]]=mmin # a mechanism for changing the parameter from its default value.
        self.covariables[self.keys[name]] = cov
        return self.p[self.keys[name]]

    def multiply(self,name,multiple):
        keynum = self.keys[name]
        if(type(self.p[keynum]) == type([])): # we're dealing with a list
            self.p[keynum] = [a*multiple for a in self.p[keynum]]
        else:
            self.p[keynum] = [self.p[keynum] * multiple]
        return self.p[keynum]

    def irregularVary(self,name,values,cov=0):
        ''' Similar to vary, except, rather than generating the
        array of parameter values to use for parameter "name",
        this list is specified explicitly in "values"'''
        keyNum = self.keys[name] # the element of the list self.p which we're editing today.
        typ = type(self.p_orig[keyNum]) # what type of variable is this in a single run of gidget?
        if(type(values) == type([1]) or type(values)==type(np.array([1.0,2.0]))): # if values is a list..
            # replace the given index of p with the list given by values.
            self.p[keyNum]=[typ(value) for value in values]
        else:
           # even though we weren't given a list, put our new value in a single-parameter list.
            try:
                self.p[keyNum]=[typ(values)]
            except:
                pdb.set_trace()
        # Next, we want to pass along the information we've been given on whether this parameter
        # should be covaried:
        self.covariables[self.keys[name]] = cov
        # and finally, give back what we've done.
        return self.p[keyNum]
    
    def ConsistencyCheck(self):
        ''' Here we check whether all parameters in a covarying set have
	the same length. Otherwise it makes little sense to vary them together.
	'''
        consistent = True
        distinctCovSetIndices = set(self.covariables)
        for ind in distinctCovSetIndices:
            covIndicesForThisSet = np.where(self.covariables == ind)
            lengths=[]
            for var in covIndicesForThisSet:
                lengths.append(len(self.p[var]))
                if(len(set(lengths)) != 1):
                    consistent=False
                    print( "Problem found in the ", ind, " set of covarying variables." )
                    print( "This corresponds to the variables ", covIndicesForThisSet )
                    print( "A set of variables you have asked to covary do not have the same lengths!" )

    def generatePl(self):
        '''vary() will change a certain element of self.p into a list
        of values for that variable. This method assumes that some
        (perhaps many) variables have been varied in this manner, and
        expands p into a list of well-defined parameter lists, each
        one of which corresponds to a run of the program. This list can
        then be sent to the xgrid or run on your machine. See other
        methods for details on how to do that.'''
        self.pl=[self.p_orig[:]] # in case generatePl() has already been run, reset pl.
	# for each separate parameter (e.g. number of cells, dissipation rate, etc.)
        for j in range(len(self.p)): 
            param = self.p[j] 
	    # if instead of a single value of the parameter, we have a whole list, create a set of runs
	    # such that for every previous run we had, we now have len(param) more, each with a different
	    # value from the list param.
            if(type(param)==list):
                covaryOtherVarsWithJ=False
                varyThisVariable=True # i.e. the variable corresponding to j.
                cov = self.covariables[j] # the flag for covarying variables.
                if (cov!=0): # if this parameter (j) is part of a set of covarying parameters...
                    covIndices = np.where(self.covariables == cov)[0]
                    # if our current variable, j, is the first in a set of variables we're covarying,
                    # let's go ahead and vary other the other variables in the same set.
                    if( covIndices[0] == j ): 
                        covaryOtherVarsWithJ = True
                        # whereas if this is not the case, then this variable has already been varied
                    else:
                        varyThisVariable = False
                if(varyThisVariable): 
                    # make len(param) copies of the current pl
                    pl2=[]
                    for i in range(len(param)):
                        f=copy.deepcopy(self.pl)
                        pl2.append(f) # pl2 ~ [pl,pl,pl]~[[p,p,p],[p,p,p],[p,p,p]]
                        # in each copy, set the jth parameter in p to param[i]
                        for a_p in pl2[i]: # each element is a list of parameters for
                            a_p[j]=param[i]
                            if(covaryOtherVarsWithJ): 
                                for covIndex in covIndices:
                                    if(covIndex != j): # already taken care of with a_p[j]=...
                                        #print covIndex, i, len(a_p), len(self.p), len(self.p[covIndex]) 
                                        a_p[covIndex] = self.p[covIndex][i]
                	    # in each copy, append to the name a...z corresponding to 
                            # which copy is currently being edited
                            if(i<=25):
                                base='a'
                                app=''
                            # If there are more than 26 variations, add a numeral for each
                            # time we have looped through the alphabet when this number is
                            # greater than zero.
                            else:
                                base='a'
                                app=str((i-(i%26))/26)
                            # avoid adding more letters to distinguish individual models
                            # if such a distinction is unnecessary.
                            if(len(param) > 1):
                                # but if such a distinction is necessary, by all means:
                                a_p[self.keys['name']]+=chr(ord(base)+(i%26))+app
	                # end loop over p's in pl2[i]
        	    # end loop over range of this varied parameter
                    # collapse pl to be a 1d array of p's.
                self.pl=[element for sub in pl2 for element in sub]
	    # end of param-being-a-list contingency
            else : #just a regular non-varying parameter
                # If the user has used vary() but with N=1, the new argument will
                # not be a list! In this case, we set this parameter in each element 
                # of pl to be the value the user picked, instead of the default value.
                for i in range(len(self.pl)):
                    if(self.pl[i][j]!=param):
                        self.pl[i][j]=param
                    else:
                        pass # nothing to do- just use default value
            # end of non-varying parameter contingency 
        # end of for loop over each parameter.

            
    def write(self,name):
        '''Write a text file which can be handled by GridStuffer to
        run the experiment. This consists of a list of lists, each
        one being a set of command line arguments to give to the
        executable. Note that before running this, you need to run
        generatePl() to generate this list of lists, and before that,
        you should run vary() to set up which parameter(s) to change
        in each run. Once you have written this file, to use it on
        your local xgrid, you use GridStuffer to create a new metajob
        with the "Input File" as the text file, and the "Output Folder"
        as gidget/output'''
        self.generatePl()
        with open(name,'w') as f:
            for a_p in self.pl:
                f.write('xgrid -job submit -in '+self.bin+' -out '+self.analysis+'/'+self.expName+' ./gidget')
                for param in a_p:
                    f.write(' '+repr(param))
                if(self.pl[-1]!=a_p):
                    f.write('\n') # no return after the last line
        if(os.path.exists(self.analysis+self.expName)):
            print("Warning: this experiment already exists! It would be a good idea to rename your experiment or delete the pre-existing one manually.")
        os.rename(name,self.xgrid+'/'+name) # move the text file to gidget/xgrid
        os.mkdir(self.xgrid+'/output/'+self.expName) # make gidget/xgrid/output/name to store stde and stdo files.
        print ("Prepared file ",name," for submission to xGrid.")

    def ExamineExperiment(self):
        self.generatePl()
        varied=[] # which elements of p are lists
        Nvaried=[] # how many variations for each such list.
        theLists=[] # a copy of each list.
        for j in range(len(self.p)): 
            param = self.p[j] 
            if(type(param)==list ):
                varied.append(j)
                Nvaried.append(len(param))
                theLists.append(param[:])
        successTable = np.ndarray(shape=tuple(Nvaried[:]),dtype=np.int64)
        successTableKeys = np.zeros(tuple(Nvaried[:]))
        for a_p in self.pl: # for each run..
            successTableKey =[]
            for i in range(len(varied)): # for each parameter that was varied
                j = varied[i]
                successTableKey.append(theLists[i].index(a_p[j]))
            successTable[tuple(successTableKey)] = successCode(self.analysis+'/'+self.expName+'/'+a_p[0]+"_stde.txt")
            successTableKeys[tuple(successTableKey)] = 1#tuple(successTableKey)
        print()
        print( "Success Table:")
        print (successTable.T)
        print() 
        return successTable.T



    def makeList(self):
        """ This function is under construction. The idea is that when we want to run a large
          number of experiments in series, we don't want to wait for the first experiment to
          finish if, say, it is still using up 2 processors but there are 2 other processors free.
        """
        self.generatePl()
        ctr=0
        binary = self.bin+'/gidget'
        expDir = self.analysis+'/'+self.expName
        if(os.path.exists(expDir) and startAt == 0):
          print( "Cancelling this run! ",self.expName)
          return ([],[],[])
        elif(os.path.exists(expDir) and startAt != 0):
          pass
        else:
          os.mkdir(expDir)
        stdo=[]
        stde=[]
        cmds=[]
        expDirs=[]
        for a_p in self.pl[startAt:]:
            ctr += 1
            tmpap = a_p[:]
            stdo.append(expDir+'/'+a_p[self.keys['name']]+'_stdo.txt')
            stde.append(expDir+'/'+a_p[self.keys['name']]+'_stde_aux.txt')
            cmds.append([binary]+tmpap[:1]+[repr(el) for el in tmpap[1:]])
            expDirs.append(expDir)

        return (cmds,stdo,stde,expDirs)


    def localRun(self,nproc,startAt,maxTime=7200.0,overwrite=False):
        ''' Run the specified experiment on this machine,
        using no more than nproc processors, and starting
        at the "startAt"th run in the experiment '''
        self.generatePl()
        procs=[]
        startTimes=[]
        ctr=0
        global allProcs
        binary=self.bin+'/gidget'
        expDir=self.analysis+'/'+self.expName #directory for output files
        #if(os.path.exists(expDir) and startAt == 0 and not overwrite):
        #print "dbg: ",startAt,overwrite,glob.glob(expDir+'/*comment.txt'),os.path.exists(expDir)
        if( len(glob.glob(expDir+'/*comment.txt'))!=0 and startAt == 0 and not overwrite ):
            print( "************")
            print( "This directory already contains output. CANCELLING this run!")
            print()
            return
        elif(os.path.exists(expDir) and (startAt != 0 or overwrite or len(glob.glob(expDir+'/*comment.txt'))==0)):
            pass # let the user overwrite whatever runs they so desire.
        else:
            os.mkdir(expDir)

        for a_p in self.pl[startAt:]:
            ctr+=1
            tmpap=a_p[:]
            globalBolshoiReader.copynearest(expDir, a_p[self.keys['name']]+'_inputRandomFactors.txt', a_p[self.keys['bolshoiWeight']], np.log10(a_p[self.keys['Mh0']]))
            try:
                shutil.copy('Lacey84_table_K.txt', expDir+'/'+'Lacey84_table_K.txt')
                shutil.copy('Lacey84_table_L.txt', expDir+'/'+'Lacey84_table_L.txt')
            except:
                #pdb.set_trace()
                print( "WARNING: failed to copy Lacey84 files. May need to add a set_trace in exper.py::experiment::localRun")
            with open(expDir+'/'+a_p[self.keys['name']]+'_stdo.txt','w') as stdo:
                with open(expDir+'/'+a_p[self.keys['name']]+'_stde_aux.txt','w') as stde:
                    print ("Sending run #",ctr,"/",len(self.pl[startAt:])," , ",tmpap[0]," to a local core.")
                    #print "Parameters: "
                    #print [binary]+tmpap[:1]+[repr(el) for el in tmpap[1:]]
                    os.chdir(expDir)
                    # Here we exclude the final element of tmpap since it corresponds to the variable bolshoiWeight, which
                    # is only used in the python code, not by the C code.
                    procs.append(subprocess.Popen([binary]+tmpap[:1]+[repr(el) for el in tmpap[1:-1]],stdout=stdo,stderr=stde))
                    cmd = ''
                    for el in tmpap:
                        cmd+=str(el)+' '
                    print ("Using cmd: ",cmd)
                    allProcs.append(procs[-1])
                    startTimes.append(time.time())
                    allStartTimes.append(time.time())
                    nPrinted=True

            # we've started a process off and running, but there are
            # probably more processes waiting to go. We do not want
            # to exceed the number of processors nproc the user
            # is willing to let run at once, so let's check what
            # our processes are up to:
            while True:

                # Check whether each process has exceeded the max time:
                for k,proc in enumerate(procs):
                    if proc.poll()==None:
                        # The process is still running.
                        if(time.time() - startTimes[k] > maxTime):
                            print ("WARNING: process has reached maximum allowed time of ",maxTime," seconds! Sending the kill signal.")
                            print (" If you're sure the process should be running longer, increase the maxTime argument of localRun.")
                            print (" Usually a run this long means something has gone horribly wrong.")
                            with open(expDir+'/'+a_p[self.keys['name']]+'_stde_aux.txt','a') as stde:
                                stde.write('Reached max allowed time '+str(maxTime)+'\n')
                            proc.kill()


                nStillRunning=HowManyStillRunning(allProcs)
                nStillRunning2=HowManyStillRunning(procs)
                #print "dbg2",nStillRunning,nStillRunning2,expDir
    
                # if our processors are all booked, wait a minute and try again
                if(nStillRunning >= nproc):
                    time.sleep(60) # wait a little bit
                    if(nPrinted):
                        print ("Waiting for a free processor...")
                        nPrinted=False # only print the above message if we haven't seen it since 
					# a new job has been submitted
                # whereas if we have free processors, loop back around to submit the next run. 
                # If there are no more runs, we're done!
                else:
                    break


def LocalRun(runBundle,nproc):
    cmds,stdo,stde,expDirs = runBundle
    for i in range(len(cmds)):
        with open(stdo[i],'w') as stdo_file:
            with open(stde[i],'w') as stde_file: 
                os.chdir(expDirs[i])
                procs.append(subprocess.Popen(cmds[i],stdout=stdo_file,stderr=stde_file))
                nPrinted=True
        while True:
            nStillRunning = HowManyStillRunning(procs)
            # if our processors are all booked, wait a minute and try again
            if(nStillRunning >= nproc):
                time.sleep(10) # wait a little bit
                if(nPrinted):
                    print ("Waiting for a free processor...")
                    nPrinted=False # only print the above message if we haven't seen it since 
    	                            # a new job has been submitted
                   # whereas if we have free processors, loop back around to submit the next run. 
                   # If there are no more runs, we're done!
            else:
                break
    # now all of our processes have been sent off
    nPrev = 0
    while True:
        nStillRunning=HowManyStillRunning(procs)
        # has anything changed since the last time we checked?
        if(nStillRunning == nPrev and nStillRunning != 0):
            # do nothing except wait a little bit
            time.sleep(5)
        else:
            nPrev=nStillRunning
            if(nPrev == 0):
               break # we're done!
            print ("Still waiting for ",nPrev, " processes to finish; I'll check every few seconds for changes.")
    print ("Local run complete!")


def GetScaleLengths(N,median=0.045,scatter=0.5,Mh0=1.0e12,sd=100,lower=0.0,upper=1.0e3,multiple=1.0):
    ''' Return a vector of scale lengths in kpc such that the haloes will have
        spin parameters of median, with a given scatter in dex. These 
        are also scaled by halo mass, since the Virial radius goes as M_h^(1/3).
        sd seeds the random number generator so that this function is deterministic.'''
    random.seed(sd)
    scLengths=[]
    while len(scLengths) < N:
        spinParameter = median  * (10.0 ** random.gauss(0.0,scatter)) # lognormal w/ scatter in dex
        if(type(Mh0) == type([1,2,3])): # if Mh0 is a list
            if(len(Mh0) == N):
                Mh=Mh0[len(scLengths)]
            else:
                print ("You've given GetScaleLengths the wrong number of halo masses")
                Mh=1.0e12
        else:
            Mh=Mh0
        length = multiple * (311.34 * (Mh/1.0e12)**(1.0/3.0) * spinParameter/(2.0**.5))
        #length = 2.5*(Mh/1.0e12)**(1./3.) * (spinParameter / .045) 
        if(length > lower and length < upper):
	        scLengths.append(length)
    return scLengths



def PrintSuccessTables(successTables):
    ''' Take the results of all experiments named when this script was called
     and sum them up such that it's obvious which runs succeeded and which failed.
     A schematic example output for a situation where 5 different experiments were
     run, each of which varied the same 2 variables, 2 values for 1, 3 for the other:

       [ [ 00000,  00000 ], [ 00010, 00010], [00011, 00011] ]
	
     indicates that, as far as whether the runs crash or succeed,
     the 2-value variable doesn't make a difference, but for increasing
     values of the 3-value variable, fewer runs succeed. The numbers which
     appear here are explained in the successCode function above. '''

    sumOfSuccessTables = np.zeros(shape=successTables[0].shape,dtype=np.int64)
    for i in range(len(successTables)):
        table = successTables[i]
        sumOfSuccessTables += (table * (10**i))

    strSumOfSuccessTables = np.array(sumOfSuccessTables, dtype=str)
    it = np.nditer(sumOfSuccessTables, flags=['multi_index'])
    while not it.finished:
        strSumOfSuccessTables[it.multi_index] = str(it[0]).zfill(len(successTables)-1)
        it.iternext()

    print()
    print ("Here is the sum of all success tables, in homogenized form")
    print()
    print (strSumOfSuccessTables)

def letter(i, caps=False):
    if caps:
        return chr(ord("A")+i)
    else:
        return chr(ord("a")+i)

def NewSetOfExperiments(copyFrom, name, N=1):
    if(type(copyFrom)==type([1])):
#        if(N!=len(copyFrom)):
#            print "WARNING: you asked for ",N,"experiments copied from ",\
#                    name," containing ",len(copyFrom),"experiments. Ignoring ",N,"."
        theList = [copy.deepcopy(copyFrom[i]) for i in range(len(copyFrom))]
    else:
        theList=[copy.deepcopy(copyFrom) for i in range(N)]

    [theList[i].changeName(name+letter(i)) for i in range(len(theList))]
    return theList


def experSuiteFromBroadMCMC(list_of_emceeparams, list_of_news, name, list_of_masses, ngal=10, accHistories=None):
    #offsets = [ 3.0, 2.0, 2.0, 2.0, 2.0, # raccVir, rstarRed, rgasRed, fg0mult, muColScaling
    #        2.0, 10.0, 1.0, 3.0, 0.28, # muFgScaling, muNorm, muMhScaling, ZIGMfac, zmix
    #        2.0, 2.0, 2.0, 10.0, 0.28, # eta, Qf, alphaMRI, epsquench, accCeiling
    #        0.3, 3.0, 0.23, 2.0, 0.5, # conRF, kZ, xiREC, epsff, initialSlope
    #        3.0, 3.0, 0.1] # mquench, enInjFac, chiZslope
    #logVars = [1, 1, 1, 1, 
    #        1, 0, 0, 1, 
    #        0, 1, 0, 1, 
    #        1, 1, 1, 0,
    #        0, 1, 0, 1, 
    #        0, 1, 1, 0]
    logVars = [1,1,1,1,
            0,0,1,0,
            1,0,1,1,
            1,1,0,0,
            1,0,1,0,
            1,1,0,0]
    
    # example\:
    #q50_11 = [ -0.75225373,   0.45321502,   0.46782298,   0.76024269, 
    #  -0.08407033, 0.29444897,  -0.7869128,   -0.94169641,  
    #  -0.07408208,   0.18528492, 0.25329861,   0.20123192, 
    # -1.33669819,  -2.75274658,   0.96226019, -0.09557928, 
    #  -1.26589114,   0.54808871,  -1.88592761,  -0.03303261,
    #  12.16116276,  -0.51294004,   0.24137744,   1.00588415]
    #from broad_svm import lnprior 
    experList = []

    for k in range(len(list_of_emceeparams)):
        emceeparams = list_of_emceeparams[k]
        news = list_of_news[k]
        for i in range(len(emceeparams)):
            if logVars[i]==1:
                news[i] = 10.0**news[i]
                emceeparams[i] = 10.0**emceeparams[i]
        experList.append(experFromBroadMCMC(emceeparams, name=name+'fid_k'+str(k), ngal=10, accHistories=accHistories, mass=list_of_masses[k]))
        for i in range(len(news)):
            thisX = emceeparams[:]
            thisX[i] = news[i]
            #if logVars[i]==1:
            #    thisX[i] = thisX[i]*offsets[i]
            #else:
            #    thisX[i] = thisX[i]+offsets[i]
            #if not np.isfinite(lnprior(thisX)): 
                #if logVars[i]==1:
                #    thisX[i] = thisX[i]/offsets[i]/offsets[i]
                #else:
                #    thisX[i] = thisX[i] - 2.0*offsets[i]
                #print "WARNING: Going the opposite direction for variable ",i
                #if not np.isfinite(lnprior(thisX)):
            #    pdb.set_trace() # tried adjusting in both directions and still ended up outside the allowed range?!
    
            experList.append(experFromBroadMCMC(thisX, name=name+'_k'+str(k)+'_'+chr(65+i), ngal=10, accHistories=accHistories, mass=list_of_masses[k]))
    return experList

def experFromBroadMCMC(emceeparams, name=None, ngal=30, accHistories=None, mass=12.0):
    raccRvir, rstarRed, rgasRed, fg0mult, muColScaling, muFgScaling, muNorm, muMhScaling, ZIGMfac, zmix, eta, Qf, alphaMRI, epsquench, accCeiling, conRF, kZ, xiREC, epsff, initialSlope, mquench, enInjFac, chiZslope = emceeparams

    if hasattr( mass, '__len__' ):
        assert np.all(mass>1.0e5)
        Mhz0 = list(mass)
    else:
        assert mass<20
        Mhz0 = list(np.power(10.0, np.linspace(mass, mass+0.001,ngal)))

    # create experiment
    
    assert not name is None, "Need a name!"
    #if name is None:
        #name = basename+str(runnumber).zfill(3)+'_'+str(rank).zfill(5)+'_'+str(proccounter).zfill(5)
    thisexper = experiment(copy.copy(name))


    # we need to put the random factors for the accretion history into a file for gidget to read.
    #directory = chaindir[0:-len(chaindirrel)]+'/'+name+'/'
    #if not os.path.exists(directory):
    #    os.makedirs(directory)

    #proccounter+=1

    #### Paramters to vary:
    # Mhz0, raccRvir, rstarRed, rgasRed, fg0mult, muColScaling, muFgScaling, muNorm, ZIGMfac, zmix, eta, Qf, alphaMRI, epsquench, accCeiling, conRF, kZ, xiREC

    thisexper.irregularVary('kappaMetals',kZ)
    thisexper.irregularVary('xiREC',xiREC)
    Mhz0 = np.array(Mhz0)
    Mhz4 = Mhz0/(.75*33.3 * np.power(Mhz0/1.5e13,0.359)) # very roughly... We know for Mh0 = 3e11, Mhz4 =4e10, and same for Mh0=2e13->Mhz4=6e11. Using those 4 numbers and assuming a powerlaw, we get this relation.
    def Moster(Mh, mparams):
        M10, M11, N10, N11, beta10, beta11, gamma10, gamma11 = mparams
        zti = 4.0
        logM1z = M10 + M11*zti/(zti+1.0)
        Nz = N10 + N11*zti/(zti+1.0)
        betaz = beta10 + beta11*zti/(zti+1.0)
        gammaz = gamma10 + gamma11*zti/(zti+1.0)
        M1 = np.power(10.0, logM1z)
        eff = 2.0*Nz / (np.power(Mh/M1,-betaz) + np.power(Mh/M1,gammaz))
        return eff
    central = np.array([11.590, 1.195, 0.0351, -0.0247, 1.376+initialSlope, -0.826, 0.608, 0.329])
    eff = Moster(Mhz4,central)
    mst = eff*Mhz4 # mstar according to the moster relation. ## at z=4 !!
    f0 = 1.0/(1.0 + np.power(mst/10.0**9.15,0.4)) # from Hayward & Hopkins (2015) eq. B2
    tau4 = 12.27/(12.27+1.60) # fractional lookback time at z=4
    fgz4 = f0*np.power(1.0 - tau4*(1.0-np.power(f0,1.5)), -2.0/3.0)
    reff4 = 5.28*np.power(mst/1.0e10, 0.25)*np.power(1.0+4.0,-0.6) # kpc (eq B3) at z=4
    reff411 = 5.28*np.power(1.0e11/1.0e10, 0.25)*np.power(1.0+4.0,-0.6) # kpc (eq B3) at z=4
    weight1 = np.exp(-Mhz0/1.0e12)  #the ad-hoc reductions in fg and fcool make things bad for high-mass galaxies. weight1 is for tiny galaxies.
    weight2 = 1-weight1
    rat4 = 1.0/(1.0/fgz4 - 1.0)
    rat4 *= fg0mult # double the gas content
    # even though we give fg0 to the gidget here, it is overridden later by giving gidget fg0mult and dbg switch 10, which internally computes in gidget's own initialization what the fg0 should be. Essentially this is because at this moment in the python code we don't actually know what the halo mass is at the initial redshift, and hence we don't know what the stellar mass is, so we don't know where we are in the "HH15" relation of fg vs. stellar mass. Within gidget we redo this ^ calculation with the actual initial halo,stellar masses.
    fgUsed =1.0/(1.0/rat4 + 1.0)*(1.0*weight1+1.0*weight2) 
    if not np.all(fgUsed<=1.0):
        pdb.set_trace()
    thisexper.irregularVary( 'fg0', list(fgUsed), 5)
    thisexper.irregularVary( 'Mh0', list(Mhz0), 5)
    fcools = 1.0/(1.0-fgUsed) * mst/(0.17*Mhz4) * (1.0*weight1+1.0*weight2)  # The factor of 0.3 is a fudge factor to keep the galaxies near Moster for longer, and maybe shift them to be a bit more in line with what we would expect for e.g. the SF MS.

    if not np.all(fcools<=1.0):
        print ("WARNING: ", name, "fcools exceed unity: ", fcools)
    thisexper.irregularVary('fcool', list(fcools), 5)
    thisexper.irregularVary('NChanges', 1001)

    width = 0.001
    asls = raccRvir*np.power(10.0, np.random.normal(0,1,len(Mhz0))*width) # * np.power(Mhz0/1.0e12,alpharmh)
    #if asls<0.005:
    #    asls=0.005
    asls = np.clip(asls, 0.005, np.inf)
    thisexper.irregularVary('accScaleLength', list(asls), 5)
    thisexper.irregularVary( 'R', list(np.power(reff4/reff411, 1.0)*50* asls/0.042)  , 5)
    thisexper.irregularVary('xmin',0.001) 

    if accHistories is None:
        bolweights = list( np.random.random(len(Mhz0)) )
    else:
        assert len(Mhz0) == len(accHistories)
        bolweights = list(accHistories[:])
    thisexper.irregularVary('bolshoiWeight', bolweights ,5)
    thisexper.irregularVary('Noutputs',200) ## why so many??
    thisexper.irregularVary('zstart',3.98)
    thisexper.irregularVary('zrelax',4.0)
    thisexper.irregularVary('tauHeat', 1.0)
    thisexper.irregularVary('muNorm', muNorm)
    thisexper.irregularVary('muFgScaling', muFgScaling)
    thisexper.irregularVary('muColScaling', muColScaling)
    thisexper.irregularVary('muMhScaling', muMhScaling)
    thisexper.irregularVary('fscatter', 1.0)
    thisexper.irregularVary('accCeiling',accCeiling)
    thisexper.irregularVary('NPassive',10)
    thisexper.irregularVary('eta',eta)
    thisexper.irregularVary('epsff',epsff)
    thisexper.irregularVary('yREC',0.03)
    thisexper.irregularVary( 'nx', 256 ) # FFT o'clock.
    ZLee = np.power(10.0, 5.65 + chiZslope*np.log10(mst/1.0e10) + 0.3*np.log10(1.0e10) - 8.7 ) # Z in Zsun
    thisexper.irregularVary('ZIGM', list(ZIGMfac*0.05*ZLee*0.02), 5)
    thisexper.irregularVary('concentrationRandomFactor', conRF) ## units of dex! # 0.7

    thisexper.irregularVary('ZIGMfac', ZIGMfac)
    thisexper.irregularVary('chiZslope', chiZslope)
    thisexper.irregularVary('deltaBeta', initialSlope)
    thisexper.irregularVary('fg0mult', fg0mult)
    thisexper.irregularVary('whichAccretionHistory', -112)
    thisexper.irregularVary('ksuppress', 10.0 )
    thisexper.irregularVary('kpower', 2.0)
    thisexper.irregularVary('dbg', 2**0 + 2**1 + 2**2 + 2**4 + 2**5 + 2**6 + 2**7 + 2**10 + 2**16 )
    thisexper.irregularVary('fscatter', 1.0)
    thisexper.irregularVary('MQuench', mquench)
    thisexper.irregularVary('epsquench', epsquench)
    thisexper.irregularVary('muQuench', 0.0)
    thisexper.irregularVary('gaScaleReduction', rgasRed )
    thisexper.irregularVary('stScaleReduction', rstarRed )
    thisexper.irregularVary('ZMix', zmix)
    thisexper.irregularVary('alphaMRI', alphaMRI)
    thisexper.irregularVary('Qlim', Qf+0.05)
    thisexper.irregularVary('fixedQ', Qf)
    thisexper.irregularVary('TOL', 6.0e-4)
    thisexper.irregularVary('energyInjectionFactor', enInjFac)
    thisexper.irregularVary('minSigSt', 10.0)
    thisexper.irregularVary('AccretionHeatingRate', 0.0)
    return thisexper



if __name__ == "__main__":

    # The structure here is straightforward:
    #   1) First, parse the arguments
    #   2) Then define a bunch of experiments
    #   3) Run the experiments the user told us to run in the command line arguments

    # Read in the arguments. To see the results of this bit of code, just try to run
    # this script without any arguments, i.e. $ python exper.py
    parser = argparse.ArgumentParser(description='Analyze data and/or run experiments associated with a list of experiment names.')
    parser.add_argument('models', metavar='experiment', type=str, nargs='+',
                   help='a string contained in any experiment to be run, e.g. if rs04a rs04b rs05a are the models defined, then exper.py rs04 will run the first two, exper.py a will run the first and last, exper.py rs will run all three, exper.py rs04b rs05 will run the last two, etc.')
    parser.add_argument('--nproc',type=int,help="maximum number of processors to use (default: 16)",default=16)
    parser.add_argument('--start',metavar='startingModel',type=int,
                   help='The number of the model in the experiment (as ordered by GeneratePl) at which we will start sending experiments to the processors to run. (default: 0)',default=0)
    parser.add_argument('--xgrid',type=bool,help="run on an xGrid (requires the user to submit the generated file to an xGrid (default: False)",default=False)
    args = parser.parse_args()
    
    # Store the names of the experiments the user has told us to run.
    modelList=[]
    for modelName in args.models:
        modelList.append(modelName)

    # Begin defining experiments!
    re01=experiment("re01")
    re01.irregularVary("R",40)
    re01.irregularVary('accScaleLength', .05) # now a fraction of r200
    re01.irregularVary('NPassive',3)
    re01.irregularVary('dbg',2)
    re01.irregularVary('xmin',.01)
    re01.irregularVary('alphaMRI',.01)
    re01.irregularVary('fcool',0.6)
    re01.irregularVary('nx',200)
    re01.irregularVary('kappaMetals',1.0)
    re01.irregularVary('xiREC',0.0)
    re01.irregularVary('muNorm',1)

    re02=NewSetOfExperiments(re01,'re02')
    re02[0].irregularVary('muNorm',[.1,1,10])

    re03=NewSetOfExperiments(re01,'re03')
    re03[0].irregularVary('accScaleLength', [.01,.03,.1])

    re04=NewSetOfExperiments(re01,'re044')
    re04[0].irregularVary('NPassive',1)
    re04[0].irregularVary('zstart',[4.8],3)
    re04[0].irregularVary('zrelax',[5.0],3)
    re04[0].irregularVary('accScaleLength',[.01,.031,.1,.25],4)
    re04[0].irregularVary('R',[15,20,35,40],4)
    re04[0].irregularVary('alphaMRI',0)
    re04[0].irregularVary('muNorm',0.0)

    re05=NewSetOfExperiments(re01,'re05')
    re05[0].irregularVary('zstart',[4.9],3)
    re05[0].irregularVary('zrelax',[5.0],3)
    re05[0].irregularVary('accScaleLength',[.01,.031,.1],4)
    re05[0].irregularVary('R',[15,30,45],4)
    re05[0].irregularVary('muNorm',[.1,1,10])
    re05[0].irregularVary('eta',[.5,4.5])
    re05[0].irregularVary('fixedQ',[1.3,2.0,3.0])
    re05[0].irregularVary('fcool',[.1,.9])
    re05[0].irregularVary('fg0',[.3,.6,.9])
    re05[0].irregularVary('Mh0',[3.0e11,1.0e12,3.0e12])

    # Playing around with mass dependence
    re06=NewSetOfExperiments(re01,'re06666')
    re06[0].irregularVary('NPassive',1)
    re06[0].irregularVary('zstart',[4.99],3)
    re06[0].irregularVary('zrelax',[5.0],3)
    re06[0].irregularVary('accScaleLength',.05)
    re06[0].vary('Mh0',1.0e10,1.0e13,9,1,4)
    re06[0].vary('R',5,50,9,1,4)
    re06[0].irregularVary('fg0',.9999)
    re06[0].irregularVary('fcool',.05)
    re06[0].irregularVary('alphaMRI',0)
    re06[0].irregularVary('muNorm',0.0)
    re06[0].irregularVary('ZIGM',.00002)
    re06[0].irregularVary('whichAccretionProfile', 2)
    re06[0].irregularVary('widthAccretionProfile', 0.6)
    re06[0].irregularVary('dbg',2**4+2**1+2**0)

    # Adding some stochasticity before messing around with previous expt.
    re07=NewSetOfExperiments(re01,'re07')
    re07[0].irregularVary('NPassive',1)
    re07[0].irregularVary('zstart',[4.8],3)
    re07[0].irregularVary('zrelax',[5.0],3)
    re07[0].irregularVary('accScaleLength',.05)
    re07[0].vary('Mh0',1.0e10,1.0e13,200,1,4)
    re07[0].vary('R',5,50,200,1,4)
    re07[0].vary('whichAccretionHistory',-300,-101,0,4)
    re07[0].irregularVary('alphaMRI',0)
    re07[0].irregularVary('muNorm',0.0)

    # Use params from toy model.
    re08=NewSetOfExperiments(re01,'re08')
    re08[0].irregularVary('NPassive',1)
    re08[0].irregularVary('zstart',[4.99],3)
    re08[0].irregularVary('zrelax',[5.0],3)
    re08[0].irregularVary('accScaleLength',.05)
    re08[0].vary('Mh0',1.0e10,1.0e13,9,1,4)
    re08[0].vary('R',5,50,9,1,4)
    re08[0].irregularVary('fg0',.9999)
    re08[0].irregularVary('fcool',.05)
    re08[0].irregularVary('alphaMRI',0)
    re08[0].vary('muNorm',22,.21,9,1,4)
    re08[0].irregularVary('ZIGM',.00002)
    re08[0].irregularVary('dbg',2**4+2**1+2**0)

    re09=NewSetOfExperiments(re08[0],'re09')
    re09[0].irregularVary('dbg',2**4+2**1+2**0+2**12)

    # Modified the code to use mu = .5 (Mh/10^12)^(-2/3)
    re10=NewSetOfExperiments(re08[0],'re10')
    re10[0].irregularVary('accCeiling',0.6)
    re10[0].vary('R',15,100,9,1,4)
    re10[0].irregularVary('accScaleLength',0.1)
    re10[0].vary('fcool',0.05/2,0.05,9,1,4)
    #re10[0].irregularVary('accNorm',.1)
    #re10[0].irregularVary('dbg',2**4+2**1+2**0+2**

    # sample to study MS.
    re11=NewSetOfExperiments(re01,'re11')
    re11[0].vary('whichAccretionHistory',-300,-101,200,0,4)
    re11[0].vary('R', 15, 100, 200, 1, 4)
    re11[0].vary('fcool', 0.05/2, 0.05, 200, 1, 4)
    re11[0].vary('Mh0',1.0e10, 1.0e13, 200, 1, 4)
    re11[0].vary('muNorm', 22, .21, 200, 1, 4)
    re11[0].irregularVary('fscatter', .45)
    re11[0].irregularVary('NChanges', list(np.random.binomial(40,.25,size=200)) ,4)
    re11[0].irregularVary('accCeiling',0.6)
    re11[0].irregularVary('accScaleLength',0.1)
    re11[0].irregularVary('NPassive',1)
    re11[0].irregularVary('zstart',[4.99],3)
    re11[0].irregularVary('zrelax',[5.0],3)
    re11[0].irregularVary('fg0',.9999)
    re11[0].irregularVary('alphaMRI',0)
    re11[0].irregularVary('ZIGM',.00002)
    re11[0].irregularVary('dbg',2**4+2**1+2**0)

    # more reasonable ZIGM - are galaxies more in equilibrium?
    re12=NewSetOfExperiments(re10[0], 're12')
    re12[0].irregularVary('ZIGM',.002)
    re12[0].irregularVary('accCeiling',0.4)
    re12[0].irregularVary('accScaleLength',0.1)

    # MW progenitors
    #re13=NewSetOfExperiments(re01[0], 're13')

    # 
    re14=NewSetOfExperiments(re01, 're14')
    re14[0].irregularVary('xmin', [.00031, .001, .0031, .01, .031])
    re14[0].irregularVary('zstart',[4.95],3)
    re14[0].irregularVary('zrelax',[5.0],3)
    re14[0].irregularVary('dbg',2**4+2**1+2**0)


    re15 = NewSetOfExperiments(re01,'re15')
    re15[0].irregularVary('zstart',[4.95],3)
    re15[0].irregularVary('zrelax',[5.0],3)
    re15[0].irregularVary('dbg',2**4+2**1+2**0)
    re15[0].irregularVary('Mh0',[1.0e11,1.0e12,1.0e13,1.0e14])
    re15[0].irregularVary('accScaleLength',[.01,.03,.05,.1,.2])
    re15[0].irregularVary('concentrationRandomFactor',[-.3,-.1,0.0,.1,.3])


    #from mcmc_individual import emceeParameterSpaceToGidgetExperiment
    #favoriteParams = [  2.83269124e-01,   9.30881877e-03,   1.82351732e-01,   1.50469698e+00,
    #           3.24674422e-01,   1.85339104e+00,   7.43781644e-03,   1.94868075e-01,
    #              4.05944370e+12,   1.38101233e-01,  -2.36399004e-01,  -5.50757004e-01,
    #                 5.94584202e-01,  -6.06652441e-01,   8.88202578e+00,   3.92808177e-01,
    #                   -2.84901649e+00]

    #re16 = emceeParameterSpaceToGidgetExperiment(favoriteParams,'re16')[0]
    #re16.irregularVary("Noutputs",200)
    #allModels['re16']=re16

    # Barro plot...
    re17=NewSetOfExperiments(re01,'re17')
    re17[0].irregularVary('zstart',4.95)
    re17[0].irregularVary('zrelax',5.0)
    re17[0].irregularVary('dbg',2**4+2**1+2**0)
    re17[0].vary('whichAccretionHistory',-300,-101,200,0,4)
    re17[0].irregularVary('R', 10)
    re17[0].irregularVary('fcool', .8)
    re17[0].vary('Mh0',1.0e12, 1.0e13, 200, 1, 4)
    re17[0].irregularVary('muNorm', 0.5)
    re17[0].irregularVary('fscatter', .45)
    re17[0].irregularVary('NChanges', list(np.random.binomial(40,.25,size=200)) ,4)
    re17[0].irregularVary('accCeiling',0.6)
    re17[0].irregularVary('accScaleLength',0.1)
    re17[0].irregularVary('NPassive',1)
    re17[0].irregularVary('eta',0.5)

    re18=NewSetOfExperiments(re17,'re18')
    re18[0].irregularVary('R',30)
    re18[0].irregularVary('Noutputs',300)
    re18[0].vary('Mh0',3.0e12, 1.0e13, 200, 1, 4)
    re18[0].irregularVary('yREC',.02)
    re18[0].irregularVary('kappaMetals',.5)

    re19a=NewSetOfExperiments(re18,'re19a')
    re19a[0].irregularVary('accScaleLength', .01)
    re19a[0].irregularVary('R',10)

    re19b=NewSetOfExperiments(re18,'re19b')
    re19b[0].irregularVary('accScaleLength', .04)
    re19b[0].irregularVary('R',20)

    re19c=NewSetOfExperiments(re18,'re19c')
    re19c[0].irregularVary('accScaleLength', .09)
    re19c[0].irregularVary('R',30)

    re20=NewSetOfExperiments(re01,'re20')
    re20[0].irregularVary('Noutputs',600)
    re20[0].irregularVary('zstart',3.95)
    re20[0].irregularVary('zrelax',4.0)
    re20[0].irregularVary('dbg',2**4+2**1+2**0 )
    asls = np.array([.012,.027,.042,.057,.072])
    re20[0].irregularVary('accScaleLength',list(asls), 5)
    re20[0].irregularVary('R', list(asls * 20/0.012), 5)
    re20[0].irregularVary('fcool', .8)
    re20[0].irregularVary('Mh0', [1.0e13])
    re20[0].irregularVary('muNorm', 1.5)
    re20[0].irregularVary('muFgScaling', 0.4)
    re20[0].irregularVary('muColScaling', 0)
    re20[0].irregularVary('fscatter', .45)
    re20[0].irregularVary('accCeiling',0.6)
    re20[0].irregularVary('NPassive',1)
    re20[0].irregularVary('eta',0.5)

    re21=NewSetOfExperiments(re20,'re21')
    re21[0].irregularVary('dbg', 2**4+2**1+2**0 + 2**12 )

    re22=NewSetOfExperiments(re20,'re22')
    re22[0].irregularVary('accScaleLength', list(asls*4), 5)
    re22[0].irregularVary('fixedQ',1.5)
    re22[0].irregularVary('whichAccretionProfile', 2)
    re22[0].irregularVary('widthAccretionProfile', 0.5)
    re22[0].irregularVary('TOL',1.0e-4)

    re23=NewSetOfExperiments(re20,'re23')
    re23[0].irregularVary('Qlim',.05)
    re23[0].irregularVary('fixedQ',.05)

    re30=NewSetOfExperiments(re20,'re30')
    re30[0].irregularVary('Noutputs',600)
    re30[0].irregularVary('zstart',3.95)
    re30[0].irregularVary('zrelax',4.0)
    re30[0].irregularVary('dbg',2**4+2**1+2**0 + 2**14 )
    asls = np.array([.012,.027,.042,.057,.072])
    re30[0].irregularVary('accScaleLength',.042 )
    mhl = np.power(10.0, np.linspace(10,13,200))
    re30[0].irregularVary('R', list(.042 * 20/0.012 * np.power(mhl/1.0e12,1.0/3.0) ), 6)
    re30[0].irregularVary('fcool', .8)
    re30[0].irregularVary('Mh0', list(mhl), 6)
    re30[0].irregularVary('muNorm', list(1.5*np.power(mhl/1.0e12, -2.0/3.0)), 6)
    re30[0].irregularVary('muFgScaling', 0.4)
    re30[0].irregularVary('muColScaling', 0)
    re30[0].irregularVary('fscatter', .45)
    re30[0].irregularVary('accCeiling',0.6)
    re30[0].irregularVary('NPassive',1)
    re30[0].irregularVary('NChanges',30)
    re30[0].irregularVary('eta',0.5)
    re30[0].vary('whichAccretionHistory',-300,-101,200,0,6)


    # Same as re30 (scatter in accr. rate) PLUS scatter in scale length
    re31=NewSetOfExperiments(re20,'re31')
    re31[0].irregularVary('Noutputs',600)
    re31[0].irregularVary('zstart',3.95)
    re31[0].irregularVary('zrelax',4.0)
    re31[0].irregularVary('dbg',2**4+2**1+2**0 + 2**14 )
    asls = np.random.normal( np.random.normal(size=200) )*(0.042-0.027) + 0.042
    re31[0].irregularVary('accScaleLength', list(asls), 6)
    mhl = np.power(10.0, np.linspace(10,13,200))
    re31[0].irregularVary('R', list(asls * 25/0.012 * np.power(mhl/1.0e12,1.0/3.0) ), 6)
    re31[0].irregularVary('fcool', .8)
    re31[0].irregularVary('Mh0', list(mhl), 6)
    re31[0].irregularVary('muNorm', list(1.5*np.power(mhl/1.0e12, -2.0/3.0)), 6)
    re31[0].irregularVary('muFgScaling', 0.4)
    re31[0].irregularVary('muColScaling', 0)
    re31[0].irregularVary('fscatter', .45)
    re31[0].irregularVary('accCeiling',0.6)
    re31[0].irregularVary('NPassive',1)
    re31[0].irregularVary('NChanges',30)
    re31[0].irregularVary('eta',0.5)
    re31[0].vary('whichAccretionHistory',-300,-101,200,0,6)
    successTables=[]


    ## Try to actually get 1st order galaxy scaling relations right.
    ## Use low-ish time resolution and mass spacing, no scatter.
    ## Use relations from appendix of Hayward & Hopkins
    def Moster(Mh, mparams):
        M10, M11, N10, N11, beta10, beta11, gamma10, gamma11 = mparams
        zti = 4.0
        logM1z = M10 + M11*zti/(zti+1.0)
        Nz = N10 + N11*zti/(zti+1.0)
        betaz = beta10 + beta11*zti/(zti+1.0)
        gammaz = gamma10 + gamma11*zti/(zti+1.0)
        M1 = np.power(10.0, logM1z)
        eff = 2.0*Nz / (np.power(Mh/M1,-betaz) + np.power(Mh/M1,gammaz))
        return eff
    central = np.array([11.590, 1.195, 0.0351, -0.0247, 1.376, -0.826, 0.608, 0.329])
    Mhz0 = np.power(10.0, np.linspace(9.5, 12.3, 12))
    Mhz4 = Mhz0/(10.0 * np.power(Mhz0/1.0e12,0.14)) # very roughly...
    eff = Moster(Mhz4,central)
    mst = eff*Mhz4 # mstar according to the moster relation. ## at z=4 !!
    f0 = 1.0/(1.0 + np.power(mst/10.0**9.15,0.4)) # from Hayward & Hopkins (2015) eq. B2
    tau4 = 12.27/(12.27+1.60) # fractional lookback time at z=4
    fgz4 = f0*np.power(1.0 - tau4*(1.0-np.power(f0,1.5)), -2.0/3.0)
    reff4 = 5.28*np.power(mst/1.0e10, 0.25)*np.power(1.0+4.0,-0.6) # kpc (eq B3) at z=4
    ZHayward = -8.69 + 9.09*np.power(1.0+4.0,-0.017) - 0.0864*np.power(np.log10(mst) - 11.07*np.power(1.0+4.0,0.094),2.0)
    ZHayward = np.power(10.0, ZHayward) * 0.02
    re40 = NewSetOfExperiments(re01,'re40')
    re40[0].irregularVary('fg0', list(fgz4), 5)
    re40[0].irregularVary('Noutputs',100)
    re40[0].irregularVary('nx', 300)
    re40[0].irregularVary('zstart',3.95)
    re40[0].irregularVary('zrelax',4.0)
    re40[0].irregularVary('dbg',2**4+2**1+2**0 )
    re40[0].irregularVary('accScaleLength',0.042)
    re40[0].irregularVary('R', list(reff4*51.0 ), 5)
    re40[0].irregularVary('xmin', .00003)
    re40[0].irregularVary('Mh0', list(Mhz0), 5) 
    re40[0].irregularVary('muNorm', list(.3*np.power(Mhz0/1.0e12,-0.6)), 5)
    fcools = 1.0/(1.0-fgz4) * mst/(0.17*Mhz4)
    re40[0].irregularVary('fcool', list(fcools), 5)
    re40[0].irregularVary('muFgScaling', 0.5)
    re40[0].irregularVary('muColScaling', 0.6)
    re40[0].irregularVary('fscatter', .45)
    re40[0].irregularVary('accCeiling',0.8)
    re40[0].irregularVary('NPassive',1)
    re40[0].irregularVary('eta',0.5)
    re40[0].irregularVary('yREC',0.04)
    re40[0].irregularVary('fixedQ', 1.25)
    re40[0].irregularVary('Qlim', 1.75)
    re40[0].irregularVary('concentrationRandomFactor', 0.7) ## units of dex! 
    re40[0].irregularVary('kappaMetals', list(.1*np.power(Mhz0/3.0e12,2.0/3.0)), 5)
    re40[0].irregularVary('ZIGM', list(ZHayward), 5)



    Mhz0 = np.power(10.0, np.linspace(9.5, 12.3, 240))
    Mhz4 = Mhz0/(10.0 * np.power(Mhz0/1.0e12,0.14)) # very roughly...
    eff = Moster(Mhz4,central)
    mst = eff*Mhz4 # mstar according to the moster relation. ## at z=4 !!
    f0 = 1.0/(1.0 + np.power(mst/10.0**9.15,0.4)) # from Hayward & Hopkins (2015) eq. B2
    tau4 = 12.27/(12.27+1.60) # fractional lookback time at z=4
    fgz4 = f0*np.power(1.0 - tau4*(1.0-np.power(f0,1.5)), -2.0/3.0)
    reff4 = 5.28*np.power(mst/1.0e10, 0.25)*np.power(1.0+4.0,-0.6) # kpc (eq B3) at z=4
    ZHayward = -8.69 + 9.09*np.power(1.0+4.0,-0.017) - 0.0864*np.power(np.log10(mst) - 11.07*np.power(1.0+4.0,0.094),2.0)
    ZHayward = np.power(10.0, ZHayward) * 0.02
    re41 = NewSetOfExperiments(re01,'re41')
    re41[0].irregularVary('fg0', list(fgz4), 5)
    re41[0].irregularVary('Noutputs',200)
    re41[0].irregularVary('zstart',3.95)
    re41[0].irregularVary('zrelax',4.0)
    re41[0].irregularVary('dbg',2**4+2**1+2**0 )
    re41[0].irregularVary('accScaleLength',0.052)
    re41[0].irregularVary('R', list(np.power(reff4/reff4[-1],-0.1)*25), 5)
    re41[0].irregularVary('Mh0', list(Mhz0), 5) 
    re41[0].irregularVary('muNorm', list(.2*np.power(Mhz0/1.0e12,-0.6)), 5)
    re41[0].irregularVary('fcool', list(1.0/(1.0-fgz4) * mst/(0.17*Mhz4)), 5)
    re41[0].irregularVary('muFgScaling', -0.3)
    re41[0].irregularVary('muColScaling', 0.2)
    re41[0].irregularVary('fscatter', .45)
    re41[0].irregularVary('accCeiling',0.5)
    re41[0].irregularVary('NPassive',1)
    re41[0].irregularVary('eta',0.5)
    re41[0].irregularVary('yREC',0.03)
    re41[0].irregularVary('fixedQ', 1.25)
    re41[0].irregularVary('Qlim', 1.75)
    re41[0].irregularVary('kappaMetals', list(np.power(Mhz0/3.0e12,1.0/3.0)), 5)
    re41[0].irregularVary('ZIGM', list(ZHayward), 5)
    asls = np.random.normal( np.random.normal(size=240) )*(0.042-0.027) + 0.052
    re41[0].irregularVary('accScaleLength', list(asls), 5)
    re41[0].irregularVary('NChanges', list(np.random.binomial(19,.53,size=240)), 5)
    re41[0].vary('whichAccretionHistory',-340,-101,240,0,5)



    ## Try to set up some galaxies that look sort of like the enzo sims!
    ## Best guesses for many parameters based on gidgetmcmc fits, e.g. eta=0.5
    ## For the mass loading factor and xi, choose values based on the results
    ## of the simulations themselves. Note that these are for the 5 kpc run.
    dw01 = NewSetOfExperiments(re01, 'dw01')
    dw01[0].irregularVary('fg0', .95)
    dw01[0].irregularVary('Noutputs', 200)
    dw01[0].irregularVary('zstart', 3.95)
    dw01[0].irregularVary('zrelax', 4.0)
    dw01[0].irregularVary('dbg', 2**4+2**1+2**0)
    dw01[0].irregularVary('accScaleLength',0.052)
    dw01[0].irregularVary('R', 20)
    dw01[0].irregularVary('Mh0', 1.0e10) 
    dw01[0].irregularVary('muNorm', 6)
    dw01[0].irregularVary('fcool', 5.0e-4/.18)
    dw01[0].irregularVary('muFgScaling', 0)
    dw01[0].irregularVary('muColScaling', 0)
    dw01[0].irregularVary('accCeiling',0.5)
    dw01[0].irregularVary('NPassive',1)
    dw01[0].irregularVary('eta',0.5)
    dw01[0].irregularVary('yREC',0.03)
    dw01[0].irregularVary('xiREC',[.7,.8,.9])
    dw01[0].irregularVary('fixedQ', 2)
    dw01[0].irregularVary('Qlim', 3)
    dw01[0].irregularVary('kappaMetals', .1)
    dw01[0].irregularVary('ZIGM', 0.0006)
    dw01[0].irregularVary('whichAccretionHistory',0)
    dw01[0].irregularVary('alphaMRI',1.0e-4)

    # Try to tweak the above set of disks to look a bit more like the simulations.
    dw02=NewSetOfExperiments(dw01, 'dw02')
    dw02[0].irregularVary('xiREC',[0,.7,.8,.9])
    dw02[0].irregularVary('accScaleLength', [.026, .052, .104])
    dw02[0].irregularVary('accCeiling',.95)
    dw02[0].irregularVary('fcool', 2.0e-4/0.18)

    # A few more tweaks, plus... In dw02 above, I find that the SFR is essentially the same for all 12 simulations.
    # Examining them in a bit more detail suggests that this is because hte inner regions of the disks are gravitationally unstable.
    # Assuming this is true, perhaps the enzo sims haven't had enough time to adjust their gas profiles accordingly. To make the comparison
    # fair and see if we can get different rates of star formation, how about essentially turning off GI? Just to check what will happen
    dw03 = NewSetOfExperiments(dw02, 'dw03')
    dw03[0].irregularVary('accCeiling', 0.1)
    dw03[0].irregularVary('fixedQ', 0.1 )
    dw03[0].irregularVary('Qlim', 0.2 )
    # Some results: lower sfr. With this I realized that fH2min is still active in the code(!).

    # Correct the fH2min thing.
    dw04 = NewSetOfExperiments(dw03, 'dw04')
    dw04[0].irregularVary('accCeiling', 0.5)
    dw04[0].irregularVary('fH2Min', 0)
    dw04[0].irregularVary('ZIGM', 0.001)
    dw04[0].irregularVary('accScaleLength', [.013, .026, .052, .104, .208] )
    dw04[0].irregularVary('xiREC', [0, .3, .6] )
    dw04[0].irregularVary('muNorm', [1, 6])
    # Result: now we get quite large differences in SFR as we expected based on the 3D sims. How to proceed? Consider turning GI back on, and try to set up two different models that end up at about the same place as the sims at z=0

    # These models are:
    #  Weak ej feedback +       perfect mixing      + preventative feedback
    #  Intermediate feedback +  imperfect mixing    + no preventative 
    #  Strong feedback +        perfect mixing      + no preventative 
    dw05=NewSetOfExperiments(dw04, 'dw05')
    dw05[0].irregularVary( 'muNorm', [0.5, 6, 60], 3)
    dw05[0].irregularVary( 'accScaleLength', .2 )
    dw05[0].irregularVary( 'xiREC', [0, .6, 0] , 3)
    dw05[0].irregularVary( 'accCeiling', [0.2, 1, 1] , 3)



    # re52 and re53 are the same, but 53 is fed with multidark
    Mhz0 = np.power(10.0, np.linspace(11.5, 13.3, 300))
    Mhz4 = Mhz0/(10.0 * np.power(Mhz0/1.0e12,0.14)) # very roughly...
    eff = Moster(Mhz4,central)
    mst = eff*Mhz4 # mstar according to the moster relation. ## at z=4 !!
    f0 = 1.0/(1.0 + np.power(mst/10.0**9.15,0.4)) # from Hayward & Hopkins (2015) eq. B2
    tau4 = 12.27/(12.27+1.60) # fractional lookback time at z=4
    fgz4 = f0*np.power(1.0 - tau4*(1.0-np.power(f0,1.5)), -2.0/3.0)
    reff4 = 5.28*np.power(mst/1.0e10, 0.25)*np.power(1.0+4.0,-0.6) # kpc (eq B3) at z=4
    ZHayward = -8.69 + 9.09*np.power(1.0+4.0,-0.017) - 0.0864*np.power(np.log10(mst) - 11.07*np.power(1.0+4.0,0.094),2.0)
    ZHayward = np.power(10.0, ZHayward) * 0.02
    re51 = NewSetOfExperiments(re01,'re53')
    re51[0].irregularVary('fg0', list(fgz4), 5)
    re51[0].irregularVary('Noutputs',200)
    re51[0].irregularVary('zstart',3.98)
    re51[0].irregularVary('zrelax',4.0)
    re51[0].irregularVary('dbg',2**4+2**1+2**0 )
    re51[0].irregularVary('accScaleLength',0.052)
    re51[0].irregularVary('R', list(np.power(reff4/reff4[-1],-0.1)*25), 5)
    re51[0].irregularVary('Mh0', list(Mhz0), 5) 
    re51[0].irregularVary('muNorm', list(.2*np.power(Mhz0/1.0e12,-0.6)), 5)
    re51[0].irregularVary('fcool', list(1.0/(1.0-fgz4) * mst/(0.17*Mhz4)), 5)
    re51[0].irregularVary('muFgScaling', -0.3)
    re51[0].irregularVary('muColScaling', 0.2)
    re51[0].irregularVary('fscatter', 1.0)
    re51[0].irregularVary('accCeiling',0.5)
    re51[0].irregularVary('NPassive',1)
    re51[0].irregularVary('eta',0.5)
    re51[0].irregularVary('yREC',0.03)
    re51[0].irregularVary('fixedQ', 1.25)
    re51[0].irregularVary('Qlim', 1.75)
    re51[0].irregularVary('kappaMetals', list(np.power(Mhz0/3.0e12,1.0/3.0)), 5)
    re51[0].irregularVary('ZIGM', list(ZHayward), 5)
    asls = np.random.normal( np.random.normal(size=len(Mhz0)) )*(0.042-0.027) + 0.052
    re51[0].irregularVary('accScaleLength', list(asls), 5)
    #re51[0].irregularVary('NChanges', list(np.random.binomial(19,.53,size=240)), 5)
    re51[0].irregularVary('NChanges', 301)
    #re51[0].vary('whichAccretionHistory',-340,-101,240,0,5)
    re51[0].irregularVary('whichAccretionHistory',-413)
    #re51[0].irregularVary('bolshoiWeight', bolshoiSize/4)
    bolweights = bolshoiSize * np.random.random(size=len(Mhz0))
    re51[0].irregularVary('bolshoiWeight', [int(bolweights[i]) for i in range(len(bolweights))], 5)

    # re54 is very similar to those above, but now fed with the ordinary Bouche accretion history ----------- this is also a good experiment: old-school variations in accretion histories to verify that our method of constructing them from multidark is reasonable.
    Mhz0 = np.power(10.0, np.linspace(11.5, 13.3, 300))
    Mhz4 = Mhz0/(10.0 * np.power(Mhz0/1.0e12,0.14)) # very roughly...
    eff = Moster(Mhz4,central)
    mst = eff*Mhz4 # mstar according to the moster relation. ## at z=4 !!
    f0 = 1.0/(1.0 + np.power(mst/10.0**9.15,0.4)) # from Hayward & Hopkins (2015) eq. B2
    tau4 = 12.27/(12.27+1.60) # fractional lookback time at z=4
    fgz4 = f0*np.power(1.0 - tau4*(1.0-np.power(f0,1.5)), -2.0/3.0)
    reff4 = 5.28*np.power(mst/1.0e10, 0.25)*np.power(1.0+4.0,-0.6) # kpc (eq B3) at z=4
    ZHayward = -8.69 + 9.09*np.power(1.0+4.0,-0.017) - 0.0864*np.power(np.log10(mst) - 11.07*np.power(1.0+4.0,0.094),2.0)
    ZHayward = np.power(10.0, ZHayward) * 0.02
    re54 = NewSetOfExperiments(re01,'re54')
    re54[0].irregularVary('fg0', list(fgz4), 5)
    re54[0].irregularVary('Noutputs',200)
    re54[0].irregularVary('zstart',3.98)
    re54[0].irregularVary('zrelax',4.0)
    re54[0].irregularVary('dbg',2**4+2**1+2**0 )
    re54[0].irregularVary('accScaleLength',0.052)
    re54[0].irregularVary('R', list(np.power(reff4/reff4[-1],-0.1)*25), 5)
    re54[0].irregularVary('Mh0', list(Mhz0), 5) 
    re54[0].irregularVary('muNorm', list(.2*np.power(Mhz0/1.0e12,-0.6)), 5)
    re54[0].irregularVary('fcool', list(1.0/(1.0-fgz4) * mst/(0.17*Mhz4)), 5)
    re54[0].irregularVary('muFgScaling', -0.3)
    re54[0].irregularVary('muColScaling', 0.2)
    re54[0].irregularVary('fscatter', 1.0)
    re54[0].irregularVary('accCeiling',0.5)
    re54[0].irregularVary('NPassive',1)
    re54[0].irregularVary('eta',0.5)
    re54[0].irregularVary('yREC',0.03)
    re54[0].irregularVary('fixedQ', 1.25)
    re54[0].irregularVary('Qlim', 1.75)
    re54[0].irregularVary('kappaMetals', list(np.power(Mhz0/3.0e12,1.0/3.0)), 5)
    re54[0].irregularVary('ZIGM', list(ZHayward), 5)
    asls = np.random.normal( np.random.normal(size=len(Mhz0)) )*(0.042-0.027) + 0.052
    re54[0].irregularVary('accScaleLength', list(asls), 5)
    #re54[0].irregularVary('NChanges', list(np.random.binomial(19,.53,size=240)), 5)
    re54[0].irregularVary('NChanges', 301)
    #re54[0].vary('whichAccretionHistory',-340,-101,240,0,5)
    re54[0].irregularVary('whichAccretionHistory',0)
    #re54[0].irregularVary('bolshoiWeight', bolshoiSize/4)
    bolweights = bolshoiSize * np.random.random(size=len(Mhz0))
    re54[0].irregularVary('bolshoiWeight', [int(bolweights[i]) for i in range(len(bolweights))], 5)





    # re55 - fix up the run a bit. First, try to get rid of the high redshift cases where r_* is unresolved.
    Ngal = 15
    Mhz0 = np.power(10.0, np.linspace(11.5, 13.3, Ngal))
    Mhz4 = Mhz0/(.75*33.3 * np.power(Mhz0/1.5e13,0.359)) # very roughly... We know for Mh0 = 3e11, Mhz4 =4e10, and same for Mh0=2e13->Mhz4=6e11. Using those 4 numbers and assuming a powerlaw, we get this relation.
    eff = Moster(Mhz4,central)
    mst = eff*Mhz4 # mstar according to the moster relation. ## at z=4 !!
    f0 = 1.0/(1.0 + np.power(mst/10.0**9.15,0.4)) # from Hayward & Hopkins (2015) eq. B2
    tau4 = 12.27/(12.27+1.60) # fractional lookback time at z=4
    fgz4 = f0*np.power(1.0 - tau4*(1.0-np.power(f0,1.5)), -2.0/3.0)
    reff4 = 5.28*np.power(mst/1.0e10, 0.25)*np.power(1.0+4.0,-0.6) # kpc (eq B3) at z=4
    ZHayward = -8.69 + 9.09*np.power(1.0+4.0,-0.017) - 0.0864*np.power(np.log10(mst) - 11.07*np.power(1.0+4.0,0.094),2.0)
    ZHayward = np.power(10.0, ZHayward) * 0.02
    re55 = NewSetOfExperiments(re01,'re55')
    re55[0].irregularVary('fg0', list(fgz4), 5)
    re55[0].irregularVary('Noutputs',200)
    re55[0].irregularVary('zstart',3.98)
    re55[0].irregularVary('zrelax',4.0)
    re55[0].irregularVary('dbg',2**4+2**1+2**0 )
    #re55[0].irregularVary('accScaleLength',0.104) # twice the canonical value I've been using
    re55[0].irregularVary('R', list(np.power(reff4/reff4[-1],0.2)*40), 5)
    re55[0].irregularVary('Mh0', list(Mhz0), 5) 
    re55[0].irregularVary('muNorm', list(.2*np.power(Mhz0/1.0e12,-0.2)), 5)
    re55[0].irregularVary('fcool', list(1.0/(1.0-fgz4) * mst/(0.17*Mhz4)), 5)
    re55[0].irregularVary('muFgScaling', -0.1)
    re55[0].irregularVary('muColScaling', 0.1)
    re55[0].irregularVary('fscatter', 1.0)
    re55[0].irregularVary('accCeiling',0.5)
    re55[0].irregularVary('NPassive',1)
    re55[0].irregularVary('eta',0.5)
    re55[0].irregularVary('xmin',0.005)
    re55[0].irregularVary('yREC',0.03)
    re55[0].irregularVary('fixedQ', 1.25)
    re55[0].irregularVary('Qlim', 1.75)
    re55[0].irregularVary('kappaMetals', list(np.power(Mhz0/3.0e12,1.0/3.0)), 5)
    re55[0].irregularVary('ZIGM', list(ZHayward), 5)
    width = (0.042-0.027)/2.0
    asls = np.random.normal( np.random.normal(size=len(Mhz0)) )*width + 0.104
    re55[0].irregularVary('accScaleLength', list(asls), 5)
    #re51[0].irregularVary('NChanges', list(np.random.binomial(19,.53,size=240)), 5)
    re55[0].irregularVary('NChanges', 301)
    #re51[0].vary('whichAccretionHistory',-340,-101,240,0,5)
    re55[0].irregularVary('whichAccretionHistory',-413)
    #re51[0].irregularVary('bolshoiWeight', bolshoiSize/4)
    bolweights = bolshoiSize * np.random.random(size=len(Mhz0))
    re55[0].irregularVary('bolshoiWeight', [int(bolweights[i]) for i in range(len(bolweights))], 5)




    # re56 - fix up the run a bit. First, try to get rid of the high redshift cases where r_* is unresolved.
    Ngal = 15
    Mhz0 = np.power(10.0, np.linspace(11.5, 13.3, Ngal))
    Mhz4 = Mhz0/(.75*33.3 * np.power(Mhz0/1.5e13,0.359)) # very roughly... We know for Mh0 = 3e11, Mhz4 =4e10, and same for Mh0=2e13->Mhz4=6e11. Using those 4 numbers and assuming a powerlaw, we get this relation.
    eff = Moster(Mhz4,central)
    mst = eff*Mhz4 # mstar according to the moster relation. ## at z=4 !!
    f0 = 1.0/(1.0 + np.power(mst/10.0**9.15,0.4)) # from Hayward & Hopkins (2015) eq. B2
    tau4 = 12.27/(12.27+1.60) # fractional lookback time at z=4
    fgz4 = f0*np.power(1.0 - tau4*(1.0-np.power(f0,1.5)), -2.0/3.0)
    reff4 = 5.28*np.power(mst/1.0e10, 0.25)*np.power(1.0+4.0,-0.6) # kpc (eq B3) at z=4
    ZHayward = -8.69 + 9.09*np.power(1.0+4.0,-0.017) - 0.0864*np.power(np.log10(mst) - 11.07*np.power(1.0+4.0,0.094),2.0)
    ZHayward = np.power(10.0, ZHayward) * 0.02
    re56 = NewSetOfExperiments(re01,'re56')
    re56[0].irregularVary('fg0', list(fgz4), 5)
    re56[0].irregularVary('Noutputs',200)
    re56[0].irregularVary('zstart',3.98)
    re56[0].irregularVary('zrelax',4.0)
    re56[0].irregularVary('dbg',2**4+2**1+2**0+2**13 )
    #re56[0].irregularVary('accScaleLength',0.104) # twice the canonical value I've been using
    re56[0].irregularVary('R', list(np.power(reff4/reff4[-1],0.2)*40), 5)
    re56[0].irregularVary('Mh0', list(Mhz0), 5) 
    re56[0].irregularVary('muNorm', list(.2*np.power(Mhz0/1.0e12,-0.2)), 5)
    re56[0].irregularVary('fcool', list(1.0/(1.0-fgz4) * mst/(0.17*Mhz4)), 5)
    re56[0].irregularVary('muFgScaling', -0.1)
    re56[0].irregularVary('muColScaling', 0.1)
    re56[0].irregularVary('fscatter', 1.0)
    re56[0].irregularVary('accCeiling',0.5)
    re56[0].irregularVary('NPassive',1)
    re56[0].irregularVary('eta',0.5)
    re56[0].irregularVary('xmin',0.005)
    re56[0].irregularVary('yREC',0.03)
    re56[0].irregularVary('fixedQ', 1.25)
    re56[0].irregularVary('Qlim', 1.75)
    re56[0].irregularVary('kappaMetals', list(np.power(Mhz0/3.0e12,1.0/3.0)), 5)
    re56[0].irregularVary('ZIGM', list(ZHayward), 5)
    width = (0.042-0.027)/2.0
    asls = np.random.normal( np.random.normal(size=len(Mhz0)) )*width + 0.104
    re56[0].irregularVary('accScaleLength', list(asls), 5)
    #re51[0].irregularVary('NChanges', list(np.random.binomial(19,.53,size=240)), 5)
    re56[0].irregularVary('NChanges', 301)
    #re56[0].vary('whichAccretionHistory',-340,-101,240,0,5)
    re56[0].irregularVary('whichAccretionHistory',-413)
    #re56[0].irregularVary('bolshoiWeight', bolshoiSize/4)
    bolweights = bolshoiSize * np.random.random(size=len(Mhz0))
    re56[0].irregularVary('bolshoiWeight', [int(bolweights[i]) for i in range(len(bolweights))], 5)


    def setKnownProperties( Mhz0, theExperiment, widthReductionFactor=1 ):
        Mhz0 = np.array(Mhz0)
        Mhz4 = Mhz0/(.75*33.3 * np.power(Mhz0/1.5e13,0.359)) # very roughly... We know for Mh0 = 3e11, Mhz4 =4e10, and same for Mh0=2e13->Mhz4=6e11. Using those 4 numbers and assuming a powerlaw, we get this relation.
        eff = Moster(Mhz4,central)
        mst = eff*Mhz4 # mstar according to the moster relation. ## at z=4 !!
        f0 = 1.0/(1.0 + np.power(mst/10.0**9.15,0.4)) # from Hayward & Hopkins (2015) eq. B2
        tau4 = 12.27/(12.27+1.60) # fractional lookback time at z=4
        fgz4 = f0*np.power(1.0 - tau4*(1.0-np.power(f0,1.5)), -2.0/3.0)
        reff4 = 5.28*np.power(mst/1.0e10, 0.25)*np.power(1.0+4.0,-0.6) # kpc (eq B3) at z=4
        ZHayward = -8.69 + 9.09*np.power(1.0+4.0,-0.017) - 0.0864*np.power(np.log10(mst) - 11.07*np.power(1.0+4.0,0.094),2.0)
        ZHayward = np.power(10.0, ZHayward) * 0.02
        weight1 = np.exp(-Mhz0/1.0e12)  #the ad-hoc reductions in fg and fcool make things bad for high-mass galaxies. weight1 is for tiny galaxies.
        weight2 = 1-weight1
        rat4 = 1.0/(1.0/fgz4 - 1.0)
        rat4 *= 2.0 # double the gas content
        fgUsed =1.0/(1.0/rat4 + 1.0)*(1.0*weight1+1.0*weight2) 
        theExperiment.irregularVary( 'fg0', list(fgUsed), 5)
        theExperiment.irregularVary( 'Mh0', list(Mhz0), 5)
        fcools = list(1.0/(1.0-fgUsed) * mst/(0.17*Mhz4) * (0.8*weight1+1.0*weight2) ) # The factor of 0.3 is a fudge factor to keep the galaxies near Moster for longer, and maybe shift them to be a bit more in line with what we would expect for e.g. the SF MS.
        theExperiment.irregularVary('fcool', fcools, 5)
        theExperiment.irregularVary('NChanges', 1001)

        #theExperiment.irregularVary('kappaMetals', list(np.power(Mhz0/3.0e12,1.0/3.0)), 5)
        #width = 0.015/widthReductionFactor # From mid-bottom panel of fig 6 of Danovich et al (2015)
        width = 0.4/widthReductionFactor 
        #width = 0.001 # just for debugging
        #asls =  np.random.normal( np.random.normal(size=len(Mhz0)) )*width + 0.16
        asls = 0.141*np.power(10.0, np.random.normal(size=len(Mhz0))*width)
        if len(Mhz0)==1:
            asls = np.array([asls])
        asls = np.clip(asls, 0.005,np.inf)
        theExperiment.irregularVary('accScaleLength', list(asls), 5)
        #theExperiment.irregularVary( 'R', list(np.power(reff4/reff4[-1],0.2)*60), 5)
        #theExperiment.irregularVary( 'R', list( np.power(reff4/reff4[-1],1.0)*70* asls/0.042 ) , 5)
        theExperiment.irregularVary( 'R', list( np.power(reff4/reff4[-1],1.0)*50* asls/0.042 ) , 5)
        #bolweights = bolshoiSize * np.random.random(size=len(Mhz0))
        bolweights =  np.random.random(size=len(Mhz0))
        #theExperiment.irregularVary('bolshoiWeight', [int(bolweights[i]) for i in range(len(bolweights))], 5)
        theExperiment.irregularVary('bolshoiWeight', list(bolweights) ,5)
        theExperiment.irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7)
        theExperiment.irregularVary('Noutputs',400)
        theExperiment.irregularVary('zstart',3.98)
        theExperiment.irregularVary('zrelax',4.0)
        theExperiment.irregularVary('muNorm', list(.005*np.power(Mhz0/1.0e12,-1.0)), 5)
        theExperiment.irregularVary('muFgScaling', -0.1)
        theExperiment.irregularVary('muColScaling', .6)
        theExperiment.irregularVary('fscatter', 1.0)
        theExperiment.irregularVary('accCeiling',1.0)
        theExperiment.irregularVary('NPassive',8)
        theExperiment.irregularVary('eta',1.5)
        theExperiment.irregularVary('xmin',0.001)
        theExperiment.irregularVary('yREC',0.03)
        theExperiment.irregularVary( 'nx', 256 ) # FFT o'clock.
        ZLee = np.power(10.0, 5.65 + 0.3*np.log10(mst) - 8.7 ) # Z in Zsun
        theExperiment.irregularVary('ZIGM', list(0.05*ZLee*0.02), 5)



    # re57 - continue to debug newly-discovered issue with rotation curves
    Ngal = 15
    Mhz0 = np.power(10.0, np.linspace(11.5, 13.3, Ngal))
    Mhz4 = Mhz0/(.75*33.3 * np.power(Mhz0/1.5e13,0.359)) # very roughly... We know for Mh0 = 3e11, Mhz4 =4e10, and same for Mh0=2e13->Mhz4=6e11. Using those 4 numbers and assuming a powerlaw, we get this relation.
    eff = Moster(Mhz4,central)
    mst = eff*Mhz4 # mstar according to the moster relation. ## at z=4 !!
    f0 = 1.0/(1.0 + np.power(mst/10.0**9.15,0.4)) # from Hayward & Hopkins (2015) eq. B2
    tau4 = 12.27/(12.27+1.60) # fractional lookback time at z=4
    fgz4 = f0*np.power(1.0 - tau4*(1.0-np.power(f0,1.5)), -2.0/3.0)
    reff4 = 5.28*np.power(mst/1.0e10, 0.25)*np.power(1.0+4.0,-0.6) # kpc (eq B3) at z=4
    ZHayward = -8.69 + 9.09*np.power(1.0+4.0,-0.017) - 0.0864*np.power(np.log10(mst) - 11.07*np.power(1.0+4.0,0.094),2.0)
    ZHayward = np.power(10.0, ZHayward) * 0.02
    re57 = NewSetOfExperiments(re01,'re57')
    re57[0].irregularVary('fg0', list(fgz4), 5)
    re57[0].irregularVary('Noutputs',200)
    re57[0].irregularVary('zstart',3.98)
    re57[0].irregularVary('zrelax',4.0)
    re57[0].irregularVary('dbg',2**4+2**1+2**0+2**13 )
    #re57[0].irregularVary('accScaleLength',0.104) # twice the canonical value I've been using
    re57[0].irregularVary('R', list(np.power(reff4/reff4[-1],0.2)*60), 5)
    re57[0].irregularVary('Mh0', list(Mhz0), 5) 
    re57[0].irregularVary('muNorm', list(.2*np.power(Mhz0/1.0e12,-0.2)), 5)
    re57[0].irregularVary('fcool', list(1.0/(1.0-fgz4) * mst/(0.17*Mhz4)), 5)
    re57[0].irregularVary('muFgScaling', -0.1)
    re57[0].irregularVary('muColScaling', 0.1)
    re57[0].irregularVary('fscatter', 1.0)
    re57[0].irregularVary('accCeiling',0.5)
    re57[0].irregularVary('NPassive',1)
    re57[0].irregularVary('eta',0.5)
    re57[0].irregularVary('xmin',0.005)
    re57[0].irregularVary('yREC',0.03)
    re57[0].irregularVary('fixedQ', 1.25)
    re57[0].irregularVary('Qlim', 1.75)
    re57[0].irregularVary('kappaMetals', list(np.power(Mhz0/3.0e12,1.0/3.0)), 5)
    re57[0].irregularVary('ZIGM', list(ZHayward), 5)
    width = (0.042-0.027)/2.0
    asls = np.random.normal( np.random.normal(size=len(Mhz0)) )*width + 0.052
    re57[0].irregularVary('accScaleLength', list(asls), 5)
    #re51[0].irregularVary('NChanges', list(np.random.binomial(19,.53,size=240)), 5)
    re57[0].irregularVary('NChanges', 301)
    #re56[0].vary('whichAccretionHistory',-340,-101,240,0,5)
    re57[0].irregularVary('whichAccretionHistory',-413)
    #re56[0].irregularVary('bolshoiWeight', bolshoiSize/4)
    bolweights = bolshoiSize * np.random.random(size=len(Mhz0))
    re57[0].irregularVary('bolshoiWeight', [int(bolweights[i]) for i in range(len(bolweights))], 5)


    # re58: try turning off GI - confirm that it's the cause of the oscillations.
    re58= NewSetOfExperiments(re57,'re58')
    re58[0].irregularVary( 'fixedQ', 0.1)

    # re59
    re59 = NewSetOfExperiments(re58,'re59')
    re59[0].irregularVary( 'fixedQ', .01)
    re59[0].irregularVary( 'Qlim', 0.015 )
    
    # re60 - turn off stars basically. Confirm that the instability still occurs in a gas-only disk. If it does, as we expect, then we can check whether it can be killed with a large alpha viscosity.
    re60 = NewSetOfExperiments(re57, 're60')
    re60[0].irregularVary( 'Qlim', 0 )
    re60[0].irregularVary( 'fixedQ', 1.5 )
    re60[0].irregularVary( 'fg0', .999999 )
    re60[0].irregularVary( 'epsff', 1.0e-7 )
    re60[0].irregularVary( 'muNorm', 0)

    # re61 - now check that we can kill the oscillation with high alpha.
    re61 = NewSetOfExperiments(re60, 're61')
    re61[0].irregularVary( 'alphaMRI', 0.2 )

    re62 = NewSetOfExperiments( re57, 're62' )
    re62[0].irregularVary( 'nx', 256 ) # FFT o'clock.


    re63 = NewSetOfExperiments( re62, 're63')
    re63[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7)


    re64 = NewSetOfExperiments ( re63, 're64')
    # A straight-up copy of re63. The C cde has been altered to reduce ksupress and take its log before passing it to the DFT. The former should do something to reduce hte oscillations still visible in vrot and the latter should hopefully do something to suppress the large spike at large radii in vrot? IDK.

    re65=NewSetOfExperiments(re64, 're65')
    # ksuppress is still 30, but now we try squaring the exponent.  Hmm. in the final version of re65, ksuppress=10. That actually works.

    # In this experiment we've finally added ksuppress as an externally-specfiable param. 
    # We're going to vary it over huge values of ksuppress in a situation (Q crit values very low) where the instability doesn't exist
    # just to check the effect of the fourier suppression on the reconstructed shape of col and colst, which we are now writing to disk.
    re66 = NewSetOfExperiments( re01, 're66' )
    setKnownProperties( [1.0e12] , re66[0])
    re66[0].irregularVary( 'ksuppress', [5, 20, 80, 320, 1200] )
    re66[0].irregularVary( 'Qlim', 1.0e-5 )
    re66[0].irregularVary( 'fixedQ', 1.0e-6 )

    re67 = NewSetOfExperiments( re01, 're67' )
    setKnownProperties(  np.power(10.0, np.linspace(11.5, 13.3, Ngal)) , re67[0])
    re67[0].irregularVary( 'ksuppress', 10.0 )

    # more galaxies
    re68 = NewSetOfExperiments( re01, 're68' )
    setKnownProperties( np.power(10.0, np.linspace(11.0, 13.3, 200)), re68[0])
    re68[0].irregularVary( 'ksuppress', 10.0 )

    # clip the negative reff's in the previous sample
    re69 = NewSetOfExperiments( re01, 're69' )
    setKnownProperties( np.power(10.0, np.linspace(11.0, 13.3, 200)), re69[0])
    re69[0].irregularVary( 'ksuppress', 10.0 )

    #  Enforce agreement with observations in IC's (dbg 10)
    # ... to debug that isue, try to get things working the way they are
    re70 = NewSetOfExperiments( re01, 're70' )
    setKnownProperties( np.power(10.0, np.linspace(11.0, 13.3, 20)), re70[0])
    re70[0].irregularVary( 'ksuppress', 5.0 )
    re70[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 )

    # Holy cow.. why is re70 so unstable?! Let's just turn off GI for a minute to double-check that it's the cause
    re71 = NewSetOfExperiments( re01, 're71' )
    setKnownProperties( np.power(10.0, np.linspace(11.0, 13.3, 20)), re71[0] )
    re71[0].irregularVary( 'ksuppress', 5.0 )
    re71[0].irregularVary( 'Qlim', 1.0e-5 )
    re71[0].irregularVary( 'fixedQ', 1.0e-6 )
    re71[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 )


    # Yep, what a shocker
    # This one seems to create a weird artificial peak. Too much kpower?
    re72 = NewSetOfExperiments( re01, 're72' )
    setKnownProperties( np.power(10.0, np.linspace(11.0, 13.3, 20)), re72[0] )
    re72[0].irregularVary( 'ksuppress', 5.0 )
    re72[0].irregularVary('kpower', 4.0)
    re72[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 )


    re73 = NewSetOfExperiments( re01, 're73' )
    setKnownProperties( np.power(10.0, np.linspace(11,13.3,20)), re73[0] )
    re73[0].irregularVary('ksuppress', 20.0 )
    re73[0].irregularVary('kpower', 2.0)
    re73[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 )

    re74 = NewSetOfExperiments(re01, 're74' )
    setKnownProperties( np.power(10.0, np.linspace(11,13.3,20)), re74[0] )
    re74[0].irregularVary('ksuppress', 10.0 )
    re74[0].irregularVary('kpower', 2.0)
    re74[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 )


    # Now that we've smoothed vPhi forcefully to make these runs stable, let's re-do with realistic scatter in accr. and scale length
    # also include a reasonable ZIGM distribution!
    re75 = NewSetOfExperiments(re01, 're75' )
    setKnownProperties( np.power(10.0, np.linspace(11,13.3,20)), re75[0], widthReductionFactor=1 )
    re75[0].irregularVary('whichAccretionHistory', -344)
    re75[0].irregularVary('ksuppress', 10.0 )
    re75[0].irregularVary('kpower', 2.0)
    re75[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 )
    re75[0].irregularVary('concentrationRandomFactor', .5 )


    # re75 is kind of fascinating. The lowest-mass galaxies have real trouble increasing their stellar mass. The metallicity gradients are kind of nuts (they have peaks at low radii). Let's try the following series of runs to understand metallicity gradients a bit better:
    # re76: same as re75, but take out the stochasticity in size and accretion radius
    # re77: re76, but take out metal mixing
    # re78: re76, but take out radial gas flow
    # re79: re76, but take out mass loading
    re76 = NewSetOfExperiments(re01, 're76' )
    setKnownProperties( np.power(10.0, np.linspace(11,13.3,20)), re76[0], widthReductionFactor=100.0 )
    re76[0].irregularVary('whichAccretionHistory', 0)
    re76[0].irregularVary('ksuppress', 10.0 )
    re76[0].irregularVary('kpower', 2.0)
    re76[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 )
    re76[0].irregularVary('concentrationRandomFactor', .5 )

    re77 = NewSetOfExperiments(re01, 're77' )
    setKnownProperties( np.power(10.0, np.linspace(11,13.3,20)), re77[0], widthReductionFactor=100.0 )
    re77[0].irregularVary('whichAccretionHistory', 0)
    re77[0].irregularVary('ksuppress', 10.0 )
    re77[0].irregularVary('kpower', 2.0)
    re77[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 )
    re77[0].irregularVary('concentrationRandomFactor', .5 )
    re77[0].irregularVary('kappaMetals',0)

    re78 = NewSetOfExperiments(re01, 're78' )
    setKnownProperties( np.power(10.0, np.linspace(11,13.3,20)), re78[0], widthReductionFactor=100.0 )
    re78[0].irregularVary('whichAccretionHistory', 0)
    re78[0].irregularVary('ksuppress', 10.0 )
    re78[0].irregularVary('kpower', 2.0)
    re78[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 )
    re78[0].irregularVary('concentrationRandomFactor', .5 )
    re78[0].irregularVary('fixedQ',1.0e-5)

    re79 = NewSetOfExperiments(re01, 're79' )
    setKnownProperties( np.power(10.0, np.linspace(11,13.3,20)), re79[0], widthReductionFactor=100.0 )
    re79[0].irregularVary('whichAccretionHistory', 0)
    re79[0].irregularVary('ksuppress', 10.0 )
    re79[0].irregularVary('kpower', 2.0)
    re79[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 )
    re79[0].irregularVary('concentrationRandomFactor', .5 )
    re79[0].irregularVary('muNorm', 0)


    # Make some adjustments - larger MLF, larger accretion radii, reduction in fcool.
    re80 = NewSetOfExperiments(re01, 're80')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 13.3, 20)), re80[0], widthReductionFactor=100.0 )
    re80[0].irregularVary('whichAccretionHistory', 0)
    re80[0].irregularVary('ksuppress', 10.0 )
    re80[0].irregularVary('kpower', 2.0)
    re80[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 )

    # Same as re81, but add the scatter back in.
    re81 = NewSetOfExperiments(re01, 're81')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 13.3, 200)), re81[0], widthReductionFactor=1.0 )
    re81[0].irregularVary('whichAccretionHistory', -112)
    re81[0].irregularVary('ksuppress', 10.0 )
    re81[0].irregularVary('kpower', 2.0)
    re81[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 )

    # Same as re82, but switch DM sims. In re81 there's a weird /tri/modality in accretion rates.
    # OK, mystery solved. You need to specify the correct NChanges.
    re82 = NewSetOfExperiments(re01, 're82')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 13.3, 200)), re82[0], widthReductionFactor=1.0 )
    re82[0].irregularVary('whichAccretionHistory', -112)
    re82[0].irregularVary('ksuppress', 10.0 )
    re82[0].irregularVary('kpower', 2.0)
    re82[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 )

    # OK, I've found two issues. One is that MBulge in gidget proper is initialized too large by a factor of 2pi. That's been corrected. I've also altered the MLF prescription so that fg = col/(col+colst+colDM). In re83 I just re-run re80. In re84 I try out just straight-up Creasey fits for the MLF.
    # Make some adjustments - larger MLF, larger accretion radii, reduction in fcool.
    re83 = NewSetOfExperiments(re01, 're83')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 13.3, 20)), re83[0], widthReductionFactor=100.0 )
    re83[0].irregularVary('whichAccretionHistory', 0)
    re83[0].irregularVary('ksuppress', 10.0 )
    re83[0].irregularVary('kpower', 2.0)
    re83[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 )

    re84 = NewSetOfExperiments(re01, 're84')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 13.3, 20)), re84[0], widthReductionFactor=100.0 )
    re84[0].irregularVary('whichAccretionHistory', 0)
    re84[0].irregularVary('ksuppress', 10.0 )
    re84[0].irregularVary('kpower', 2.0)
    re84[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 )
    re84[0].irregularVary('muNorm', 13)
    re84[0].irregularVary('muFgScaling', 0.16)
    re84[0].irregularVary('muColScaling', 1.15)

    # At this point we add a Mquench = 10^12 Msun hard-codd. In re86, also check what happens if we turn on the ancient likely-wrong prescription for stellar mass return
    re85 = NewSetOfExperiments(re01, 're85')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 13.3, 20)), re85[0], widthReductionFactor=100.0 )
    re85[0].irregularVary('whichAccretionHistory', 0)
    re85[0].irregularVary('ksuppress', 10.0 )
    re85[0].irregularVary('kpower', 2.0)
    re85[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 )

    re86 = NewSetOfExperiments(re01, 're86')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 13.3, 20)), re86[0], widthReductionFactor=100.0 )
    re86[0].irregularVary('whichAccretionHistory', 0)
    re86[0].irregularVary('ksuppress', 10.0 )
    re86[0].irregularVary('kpower', 2.0)
    re86[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 + 2**6 )

    # Steepen dependence of outflows on halo mass and increase epsin to bring us back up to M_*-M_h
    re87 = NewSetOfExperiments(re01, 're87')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 13.3, 10)), re87[0], widthReductionFactor=100.0 )
    re87[0].irregularVary('whichAccretionHistory', 0)
    re87[0].irregularVary('ksuppress', 10.0 )
    re87[0].irregularVary('kpower', 2.0)
    re87[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 )

    re88 = NewSetOfExperiments(re01, 're88')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 13.3, 20)), re88[0], widthReductionFactor=100.0 )
    re88[0].irregularVary('whichAccretionHistory', 0)
    re88[0].irregularVary('ksuppress', 10.0 )
    re88[0].irregularVary('kpower', 2.0)
    re88[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 +2**6)
    re88[0].irregularVary('RfREC', 0.1)

    # Just re-run re87, but in the code chance epsin when Mh>Mquench to be epsin*=0.1
    re89=NewSetOfExperiments(re87,'re89')

    # in KnownProperties, increase scale lengths
    re90=NewSetOfExperiments(re87, 're90')

    # again slightly larger scale lengths, a bit steeper MLF mass-dependence, and lower initial values of f_g and f_cool
    re91=NewSetOfExperiments(re87, 're91')

    # a little bit more on the scale lengths. Keep the adjusted f_g and f_cool from re91 for low-mass galaxies, but up the initial values for high-mass galaxies [this makes some physical sense because those galaxies should do most of their SF earlier
    re92=NewSetOfExperiments(re87, 're92')

    # dial back on lengths, increase weighting effects
    re93=NewSetOfExperiments(re87, 're93')

    # Adjust feedback: reduce overall normalization from .5 to .2, increase strength of scaling with fg and column density
    re94=NewSetOfExperiments(re87, 're94')

    # re93->re94 increase global MLF by like a factor of 10, so let's knock down the normalization by a factor of 10.
    re95=NewSetOfExperiments(re87, 're95')

    # 95 was pretty good (at least for SMHM)! Adjust weighted IC's -- high initial gas fractions for high-mass galaxies, and lower fcools for low-mass galaxies
    re96=NewSetOfExperiments(re87, 're96')

    # Features I don't like about 96: 1: really large difference between low-mass and high-mass galaxies in IC's. 2: SMHM has halos w/ too little stellar mass at z~1-2 near and above Mh~10^12,  3: odd up-turn in gas fraction at high-mass end 4: Generally too-low metallicity, especially for low-mass galaxies
    # So here we: soften the transition a bit, bump up the quenching mass, scale metllicity with current disk metallicity.
    re97=NewSetOfExperiments(re87, 're97')
    re97[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 + 2**5 ) # Add in dbg.opt(5) - scale incoming metallicity with current metallicity.

    # Lower the accretion efficiency above the quenching limit from 0.3 to 0.15 to address high SM in SMHM at high end
    # Increase avg accretion scale length from 0.12 to 0.14 to address small galaxy sizes (SM-r*) and too-high Sigma1's
    # Increase initial fg to increase high-z SF, while decreasing initial fcool's to compensate hopefully?
    re98=NewSetOfExperiments(re87, 're98')
    re98[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 + 2**5 ) 

    # Lower accr at M>Mq from .15 to .05; increase fg's from 0.8 to 1.0 of their nominal value; increase fcool from .7 to .8 for low-mass galaxies
    re99=NewSetOfExperiments(re87, 're99')
    re99[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 + 2**5 ) 

    # Loewr accr at M>Mq from .05 to .01, increase fcool from .8 to .9, decrease Mq from 3 to 2.
    rf01=NewSetOfExperiments(re87, 'rf01')
    rf01[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 + 2**5 ) 

    # In an effort to lower Sigma1, increase mu scaling with col, bump down quenching mass
    rf02=NewSetOfExperiments(re87, 'rf02')
    rf02[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 + 2**5 ) 

    # Shallower scaling of mu w/ halo mass and col. Z accretion now correctly scales with current disk metallicity
    rf03=NewSetOfExperiments(re87, 'rf03')
    rf03[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 + 2**5 ) 

    # Raised Q and Qlim a bit.
    rf04=NewSetOfExperiments(re87, 'rf04')
    rf04[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 + 2**5 ) 


    # reduce xmin from .005 to .001. Lower Q and Qlim (was dumb to raise them... derp)
    rf05=NewSetOfExperiments(re87, 'rf05')
    rf05[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 + 2**5 ) 

    #  Make stars follow full velocity dispersion instead of turbulent only, when formed.
    # Also step down the gas fraction at high masses and the gas feeding efficiency above Mq.
    rf06=NewSetOfExperiments(re87, 'rf06')
    rf06[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 )  # full v.d.

    # Halve number of galaxis to speed up iterations, up interior edge radius a bit to avoid numerical instability
    # Quarter the initial radius of the galaxy - i.e. r_disk,ic = r_acc,ic / 4.0 instead of 1.0
    rf07 = NewSetOfExperiments(re87, 'rf07')
    rf07[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 )  # full v.d.

    # Decouple initial col and colst.
    # Bump up fg at high masses, lower fc at low masses, bump up Q's to increase inward flow (and maybe sfr's?)
    rf08 = NewSetOfExperiments(re87, 'rf08')
    rf08[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 )  # full v.d.

    # Raise Mq again, bump up scale lengths a little
    rf09 = NewSetOfExperiments(re87, 'rf09')
    rf09[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 )  # full v.d.

    # Slightly lower MLF normalization
    rf10 = NewSetOfExperiments(re87, 'rf10')
    rf10[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 )  # full v.d.

    # Tone down the large difference in scale radii beteen ic's
    rf11 = NewSetOfExperiments(re87, 'rf11')
    rf11[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 )  # full v.d.

    rf12 = NewSetOfExperiments(re01, 'rf12')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 13.3, 100)), rf12[0], widthReductionFactor=1.0 )
    rf12[0].irregularVary('whichAccretionHistory', -113)
    rf12[0].irregularVary('ksuppress', 10.0 )
    rf12[0].irregularVary('kpower', 2.0)
    rf12[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 )  # full v.d.

    # Go back to our more limited sample. Also, at this point we've finally added the parameters MQuench, epsquench, and muQuench as run-time params. The final version of the above had MQuench ~ 2e12, epsquench~0.3, and muQuench=0. This should be pretty similar to rf11
    rf13 = NewSetOfExperiments(re01, 'rf13')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 13.7, 10)), rf13[0], widthReductionFactor=100.0 )
    rf13[0].irregularVary('whichAccretionHistory', 0)
    rf13[0].irregularVary('ksuppress', 10.0 )
    rf13[0].irregularVary('kpower', 2.0)
    rf13[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 )  # full v.d.
    rf13[0].irregularVary('MQuench', 2.0e12)
    rf13[0].irregularVary('epsquench', 0.3)

    rf14 = NewSetOfExperiments(re01, 'rf14')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 13.7, 10)), rf14[0], widthReductionFactor=100.0 )
    rf14[0].irregularVary('whichAccretionHistory', 0)
    rf14[0].irregularVary('ksuppress', 10.0 )
    rf14[0].irregularVary('kpower', 2.0)
    rf14[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 )  # full v.d.
    rf14[0].irregularVary('MQuench', 2.0e12)
    rf14[0].irregularVary('epsquench', 1.0)
    rf14[0].irregularVary('muQuench', 2.0)

    rf15 = NewSetOfExperiments(re01, 'rf15')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 13.7, 10)), rf15[0], widthReductionFactor=100.0 )
    rf15[0].irregularVary('whichAccretionHistory', 0)
    rf15[0].irregularVary('ksuppress', 10.0 )
    rf15[0].irregularVary('kpower', 2.0)
    rf15[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 )  # full v.d.
    rf15[0].irregularVary('MQuench', 2.0e12)
    rf15[0].irregularVary('epsquench', 1.0)
    rf15[0].irregularVary('muQuench', 5.0)

    rf16 = NewSetOfExperiments(re01, 'rf16')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 13.7, 10)), rf16[0], widthReductionFactor=100.0 )
    rf16[0].irregularVary('whichAccretionHistory', 0)
    rf16[0].irregularVary('ksuppress', 10.0 )
    rf16[0].irregularVary('kpower', 2.0)
    rf16[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 )  # full v.d.
    rf16[0].irregularVary('MQuench', 8.0e12)
    rf16[0].irregularVary('epsquench', 1.0)
    rf16[0].irregularVary('muQuench', 4.0)


    # for comparison to 16 --- just do a run with no quenching.
    rf17 = NewSetOfExperiments(re01, 'rf17')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 13.7, 10)), rf17[0], widthReductionFactor=100.0 )
    rf17[0].irregularVary('whichAccretionHistory', 0)
    rf17[0].irregularVary('ksuppress', 10.0 )
    rf17[0].irregularVary('kpower', 2.0)
    rf17[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 )  # full v.d.
    rf17[0].irregularVary('MQuench', 8.0e14)
    rf17[0].irregularVary('epsquench', 1.0)
    rf17[0].irregularVary('muQuench', 4.0)

    # rf17 with scatter. Check Genzel analysis on galaxies that do not experience quenching
    rf18 = NewSetOfExperiments(re01, 'rf18')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 13.7, 150)), rf18[0], widthReductionFactor=1.0 )
    rf18[0].irregularVary('whichAccretionHistory', -142)
    rf18[0].irregularVary('ksuppress', 10.0 )
    rf18[0].irregularVary('kpower', 2.0)
    rf18[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 )  # full v.d.
    rf18[0].irregularVary('MQuench', 8.0e14)
    rf18[0].irregularVary('epsquench', 1.0)
    rf18[0].irregularVary('muQuench', 4.0)

    #rf18, except the scatter is generated internally by GIDGET, rather than input using Bolshoi
    # Add in fscatter=0.3 (realistic-ish), and 2**2 to debug... oops. actually the 2**2 turns ON readIn
    # So this ended up being another bolshoi-based sim with an artificially-reduced scatter
    rf19 = NewSetOfExperiments(re01, 'rf19')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 13.7, 150)), rf19[0], widthReductionFactor=1.0 )
    rf19[0].irregularVary('whichAccretionHistory', -142)
    rf19[0].irregularVary('ksuppress', 10.0 )
    rf19[0].irregularVary('kpower', 2.0)
    rf19[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 + 2**5 + 2**16+2**2 )  
    rf19[0].irregularVary('fscatter', 0.4)
    rf19[0].irregularVary('MQuench', 8.0e14)
    rf19[0].irregularVary('epsquench', 1.0)
    rf19[0].irregularVary('muQuench', 4.0)

    rf20 = NewSetOfExperiments(re01, 'rf20')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 13.7, 150)), rf20[0], widthReductionFactor=1.0 )
    rf20[0].irregularVary('whichAccretionHistory', -142)
    rf20[0].irregularVary('ksuppress', 10.0 )
    rf20[0].irregularVary('kpower', 2.0)
    rf20[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 )  
    rf20[0].irregularVary('fscatter', 0.4)
    rf20[0].irregularVary('MQuench', 8.0e14)
    rf20[0].irregularVary('epsquench', 1.0)
    rf20[0].irregularVary('muQuench', 4.0)

    # Return to the mean case, and check that we can still reproduce SMHM etc with a quenching model.
    rf21 = NewSetOfExperiments(re01, 'rf21')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 13.7, 15)), rf21[0], widthReductionFactor=100.0 )
    rf21[0].irregularVary('whichAccretionHistory', 0)
    rf21[0].irregularVary('ksuppress', 10.0 )
    rf21[0].irregularVary('kpower', 2.0)
    rf21[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 )  
    rf21[0].irregularVary('fscatter', 0.4)
    rf21[0].irregularVary('MQuench', 6.0e12)
    rf21[0].irregularVary('epsquench', 1.0)
    rf21[0].irregularVary('muQuench', 4.0)

    # The above was reasonably successful with increased mu above quenching limit. Now try to get similar success with epsquench instead
    rf22 = NewSetOfExperiments(re01, 'rf22')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 13.7, 15)), rf22[0], widthReductionFactor=100.0 )
    rf22[0].irregularVary('whichAccretionHistory', 0)
    rf22[0].irregularVary('ksuppress', 10.0 )
    rf22[0].irregularVary('kpower', 2.0)
    rf22[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 )  
    rf22[0].irregularVary('fscatter', 0.4)
    rf22[0].irregularVary('MQuench', 2.0e12)
    rf22[0].irregularVary('epsquench', 0.1)
    rf22[0].irregularVary('muQuench', 0.0)

    # OK, updated the code to reflect transparently the use of new parameters.
    rf23 = NewSetOfExperiments(re01, 'rf23')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 13.7, 15)), rf23[0], widthReductionFactor=100.0 )
    rf23[0].irregularVary('whichAccretionHistory', 0)
    rf23[0].irregularVary('ksuppress', 10.0 )
    rf23[0].irregularVary('kpower', 2.0)
    rf23[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 )  
    rf23[0].irregularVary('fscatter', 0.4)
    rf23[0].irregularVary('MQuench', 2.0e12)
    rf23[0].irregularVary('epsquench', 0.1)
    rf23[0].irregularVary('muQuench', 0.0)
    rf23[0].irregularVary('gaScaleReduction', 1.2 )
    rf23[0].irregularVary('stScaleReduction', 3.0 )
    rf23[0].irregularVary('ZMix', 0.1)
    
    # Add variation in both accr. rate and galaxy size
    rf24 = NewSetOfExperiments(re01, 'rf24')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 14.2, 250)), rf24[0], widthReductionFactor=1.0 )
    rf24[0].irregularVary('whichAccretionHistory', -132)
    rf24[0].irregularVary('ksuppress', 10.0 )
    rf24[0].irregularVary('kpower', 2.0)
    rf24[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 + 2**2)  
    rf24[0].irregularVary('fscatter', 1.0)
    rf24[0].irregularVary('MQuench', 2.0e12)
    rf24[0].irregularVary('epsquench', 0.1)
    rf24[0].irregularVary('muQuench', 0.0)
    rf24[0].irregularVary('gaScaleReduction', 1.2 )
    rf24[0].irregularVary('stScaleReduction', 3.0 )
    rf24[0].irregularVary('ZMix', 0.1)


    # Back to small sample for a sec - try out  increased alpha viscosity to fill in holes.
    rf25 = NewSetOfExperiments(re01, 'rf25')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 13.7, 15)), rf25[0], widthReductionFactor=100.0 )
    rf25[0].irregularVary('whichAccretionHistory', 0)
    rf25[0].irregularVary('ksuppress', 10.0 )
    rf25[0].irregularVary('kpower', 2.0)
    rf25[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 )  
    rf25[0].irregularVary('fscatter', 0.4)
    rf25[0].irregularVary('MQuench', 2.0e12)
    rf25[0].irregularVary('epsquench', 0.1)
    rf25[0].irregularVary('muQuench', 0.0)
    rf25[0].irregularVary('gaScaleReduction', 1.2 )
    rf25[0].irregularVary('stScaleReduction', 3.0 )
    rf25[0].irregularVary('ZMix', 0.1)
    rf25[0].irregularVary('alphaMRI', 0.1)

    rf26 = NewSetOfExperiments(re01, 'rf26')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 13.7, 15)), rf26[0], widthReductionFactor=100.0 )
    rf26[0].irregularVary('whichAccretionHistory', 0)
    rf26[0].irregularVary('ksuppress', 10.0 )
    rf26[0].irregularVary('kpower', 2.0)
    rf26[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 )  
    rf26[0].irregularVary('fscatter', 0.4)
    rf26[0].irregularVary('MQuench', 2.0e12)
    rf26[0].irregularVary('epsquench', 0.1)
    rf26[0].irregularVary('muQuench', 0.0)
    rf26[0].irregularVary('gaScaleReduction', 1.2 )
    rf26[0].irregularVary('stScaleReduction', 3.0 )
    rf26[0].irregularVary('ZMix', 0.1)
    rf26[0].irregularVary('alphaMRI', 0.1)
    rf26[0].irregularVary('Qlim', 1.25)
    rf26[0].irregularVary('fixedQ', 1.2)

    # Try decreasing the initial stellar size. Helps a bit.
    rf27 = NewSetOfExperiments(re01, 'rf27')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 14.1, 15)), rf27[0], widthReductionFactor=100.0 )
    rf27[0].irregularVary('whichAccretionHistory', 0)
    rf27[0].irregularVary('ksuppress', 10.0 )
    rf27[0].irregularVary('kpower', 2.0)
    rf27[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 )  
    rf27[0].irregularVary('fscatter', 0.4)
    rf27[0].irregularVary('MQuench', 4.0e12)
    rf27[0].irregularVary('epsquench', 0.1)
    rf27[0].irregularVary('muQuench', 0.0)
    rf27[0].irregularVary('gaScaleReduction', 1.2 )
    rf27[0].irregularVary('stScaleReduction', 5.0 )
    rf27[0].irregularVary('ZMix', 0.1)
    rf27[0].irregularVary('alphaMRI', 0.1)
    rf27[0].irregularVary('Qlim', 1.25)
    rf27[0].irregularVary('fixedQ', 1.2)

    # Try decreasing the accretion radii!
    rf28 = NewSetOfExperiments(re01, 'rf28')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 14.1, 15)), rf28[0], widthReductionFactor=100.0 )
    rf28[0].irregularVary('whichAccretionHistory', 0)
    rf28[0].irregularVary('ksuppress', 10.0 )
    rf28[0].irregularVary('kpower', 2.0)
    rf28[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 )  
    rf28[0].irregularVary('fscatter', 0.4)
    rf28[0].irregularVary('MQuench', 4.0e12)
    rf28[0].irregularVary('epsquench', 0.1)
    rf28[0].irregularVary('muQuench', 0.0)
    rf28[0].irregularVary('gaScaleReduction', 1.2 )
    rf28[0].irregularVary('stScaleReduction', 5.0 )
    rf28[0].irregularVary('ZMix', 0.1)
    rf28[0].irregularVary('alphaMRI', 0.1)
    rf28[0].irregularVary('Qlim', 1.25)
    rf28[0].irregularVary('fixedQ', 1.2)

    # Try increasing Q again
    rf29 = NewSetOfExperiments(re01, 'rf29')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 14.1, 15)), rf29[0], widthReductionFactor=100.0 )
    rf29[0].irregularVary('whichAccretionHistory', 0)
    rf29[0].irregularVary('ksuppress', 10.0 )
    rf29[0].irregularVary('kpower', 2.0)
    rf29[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 )  
    rf29[0].irregularVary('fscatter', 0.4)
    rf29[0].irregularVary('MQuench', 4.0e12)
    rf29[0].irregularVary('epsquench', 0.1)
    rf29[0].irregularVary('muQuench', 0.0)
    rf29[0].irregularVary('gaScaleReduction', 1.2 )
    rf29[0].irregularVary('stScaleReduction', 5.0 )
    rf29[0].irregularVary('ZMix', 0.05)
    rf29[0].irregularVary('alphaMRI', 0.1)
    rf29[0].irregularVary('Qlim', 2.25)
    rf29[0].irregularVary('fixedQ', 2.2)

    # That went poorly
    rf30 = NewSetOfExperiments(re01, 'rf30')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 14.1, 15)), rf30[0], widthReductionFactor=100.0 )
    rf30[0].irregularVary('whichAccretionHistory', 0)
    rf30[0].irregularVary('ksuppress', 10.0 )
    rf30[0].irregularVary('kpower', 2.0)
    rf30[0].irregularVary('dbg',2**4+2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 )  
    rf30[0].irregularVary('fscatter', 0.4)
    rf30[0].irregularVary('MQuench', 4.0e12)
    rf30[0].irregularVary('epsquench', 0.1)
    rf30[0].irregularVary('muQuench', 0.0)
    rf30[0].irregularVary('gaScaleReduction', 1.2 )
    rf30[0].irregularVary('stScaleReduction', 5.0 )
    rf30[0].irregularVary('ZMix', 0.05)
    rf30[0].irregularVary('alphaMRI', 0.1)
    rf30[0].irregularVary('Qlim', 1.35)
    rf30[0].irregularVary('fixedQ', 1.3)

    ## Try out iterative fH2 -- approx version doesn't have consistent RH2??
    rf31 = NewSetOfExperiments(re01, 'rf31')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 14.1, 15)), rf31[0], widthReductionFactor=100.0 )
    rf31[0].irregularVary('whichAccretionHistory', 0)
    rf31[0].irregularVary('ksuppress', 10.0 )
    rf31[0].irregularVary('kpower', 2.0)
    rf31[0].irregularVary('dbg',2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 )  
    rf31[0].irregularVary('fscatter', 0.4)
    rf31[0].irregularVary('MQuench', 4.0e12)
    rf31[0].irregularVary('epsquench', 0.1)
    rf31[0].irregularVary('muQuench', 0.0)
    rf31[0].irregularVary('gaScaleReduction', 1.2 )
    rf31[0].irregularVary('stScaleReduction', 5.0 )
    rf31[0].irregularVary('ZMix', 0.05)
    rf31[0].irregularVary('alphaMRI', 0.1)
    rf31[0].irregularVary('Qlim', 1.35)
    rf31[0].irregularVary('fixedQ', 1.3)

    ## Try out iterative fH2 -- approx version doesn't have consistent RH2??
    rf32 = NewSetOfExperiments(re01, 'rf32')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 14.1, 15)), rf32[0], widthReductionFactor=100.0 )
    rf32[0].irregularVary('whichAccretionHistory', 0)
    rf32[0].irregularVary('ksuppress', 10.0 )
    rf32[0].irregularVary('kpower', 2.0)
    rf32[0].irregularVary('dbg',2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 )  
    rf32[0].irregularVary('fscatter', 0.4)
    rf32[0].irregularVary('MQuench', 4.0e12)
    rf32[0].irregularVary('epsquench', 0.1)
    rf32[0].irregularVary('muQuench', 0.0)
    rf32[0].irregularVary('gaScaleReduction', 1.2 )
    rf32[0].irregularVary('stScaleReduction', 5.0 )
    rf32[0].irregularVary('ZMix', 0.05)
    rf32[0].irregularVary('alphaMRI', 0.1)
    rf32[0].irregularVary('Qlim', 1.35)
    rf32[0].irregularVary('fixedQ', 1.3)

    rf33 = NewSetOfExperiments(re01, 'rf33')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 14.1, 15)), rf33[0], widthReductionFactor=100.0 )
    rf33[0].irregularVary('whichAccretionHistory', 0)
    rf33[0].irregularVary('ksuppress', 10.0 )
    rf33[0].irregularVary('kpower', 2.0)
    rf33[0].irregularVary('dbg',2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 )  
    rf33[0].irregularVary('fscatter', 0.4)
    rf33[0].irregularVary('MQuench', 4.0e12)
    rf33[0].irregularVary('epsquench', 0.1)
    rf33[0].irregularVary('muQuench', 0.0)
    rf33[0].irregularVary('gaScaleReduction', 1.2 )
    rf33[0].irregularVary('stScaleReduction', 3.0 )
    rf33[0].irregularVary('ZMix', 0.05)
    rf33[0].irregularVary('alphaMRI', 0.1)
    rf33[0].irregularVary('Qlim', 1.35)
    rf33[0].irregularVary('fixedQ', 1.3)

    rf34 = NewSetOfExperiments(re01, 'rf34')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 14.1, 15)), rf34[0], widthReductionFactor=100.0 )
    rf34[0].irregularVary('whichAccretionHistory', 0)
    rf34[0].irregularVary('ksuppress', 10.0 )
    rf34[0].irregularVary('kpower', 2.0)
    rf34[0].irregularVary('dbg',2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 )  
    rf34[0].irregularVary('fscatter', 0.4)
    rf34[0].irregularVary('MQuench', 2.0e12)
    rf34[0].irregularVary('epsquench', 0.1)
    rf34[0].irregularVary('muQuench', 0.0)
    rf34[0].irregularVary('gaScaleReduction', 1.0 )
    rf34[0].irregularVary('stScaleReduction', 1.0 )
    rf34[0].irregularVary('ZMix', 0.05)
    rf34[0].irregularVary('alphaMRI', 0.1)
    rf34[0].irregularVary('Qlim', 1.35)
    rf34[0].irregularVary('fixedQ', 1.3)

    rf35 = NewSetOfExperiments(re01, 'rf35')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 14.1, 15)), rf35[0], widthReductionFactor=100.0 )
    rf35[0].irregularVary('whichAccretionHistory', 0)
    rf35[0].irregularVary('ksuppress', 10.0 )
    rf35[0].irregularVary('kpower', 2.0)
    rf35[0].irregularVary('dbg',2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 )  
    rf35[0].irregularVary('fscatter', 0.4)
    rf35[0].irregularVary('MQuench', 4.0e12)
    rf35[0].irregularVary('epsquench', 0.0)
    rf35[0].irregularVary('muQuench', 5.0)
    rf35[0].irregularVary('gaScaleReduction', 1.0 )
    rf35[0].irregularVary('stScaleReduction', 1.0 )
    rf35[0].irregularVary('ZMix', 0.05)
    rf35[0].irregularVary('alphaMRI', 0.1)
    rf35[0].irregularVary('Qlim', 1.35)
    rf35[0].irregularVary('fixedQ', 1.3)
    rf35[0].irregularVary('TOL', 1.0e-5)

    rf36 = NewSetOfExperiments(re01, 'rf36')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 14.1, 9)), rf36[0], widthReductionFactor=100.0 )
    rf36[0].irregularVary('whichAccretionHistory', 0)
    rf36[0].irregularVary('ksuppress', 10.0 )
    rf36[0].irregularVary('kpower', 2.0)
    rf36[0].irregularVary('dbg',2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 )  
    rf36[0].irregularVary('fscatter', 0.4)
    rf36[0].irregularVary('MQuench', 4.0e12)
    rf36[0].irregularVary('epsquench', 0.0)
    rf36[0].irregularVary('muQuench', 5.0)
    rf36[0].irregularVary('gaScaleReduction', 1.0 )
    rf36[0].irregularVary('stScaleReduction', 1.0 )
    rf36[0].irregularVary('ZMix', 0.05)
    rf36[0].irregularVary('alphaMRI', 0.1)
    rf36[0].irregularVary('Qlim', 1.35)
    rf36[0].irregularVary('fixedQ', 1.3)
    rf36[0].irregularVary('TOL', 1.0e-4)


    rf37 = NewSetOfExperiments(re01, 'rf37')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 14.1, 9)), rf37[0], widthReductionFactor=100.0 )
    rf37[0].irregularVary('whichAccretionHistory', 0)
    rf37[0].irregularVary('ksuppress', 10.0 )
    rf37[0].irregularVary('kpower', 2.0)
    rf37[0].irregularVary('dbg',2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 )  
    rf37[0].irregularVary('fscatter', 0.4)
    rf37[0].irregularVary('MQuench', 4.0e12)
    rf37[0].irregularVary('epsquench', 0.1)
    rf37[0].irregularVary('accCeiling', 0.5)
    rf37[0].irregularVary('muQuench', 0.0)
    rf37[0].irregularVary('gaScaleReduction', 1.0 )
    rf37[0].irregularVary('stScaleReduction', 1.0 )
    rf37[0].irregularVary('ZMix', 0.05)
    rf37[0].irregularVary('alphaMRI', 0.1)
    rf37[0].irregularVary('Qlim', 1.35)
    rf37[0].irregularVary('fixedQ', 1.3)
    rf37[0].irregularVary('TOL', 4.0e-4)

    rf38 = NewSetOfExperiments(re01, 'rf38')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 14.1, 9)), rf38[0], widthReductionFactor=100.0 )
    rf38[0].irregularVary('whichAccretionHistory', -112)
    rf38[0].irregularVary('ksuppress', 10.0 )
    rf38[0].irregularVary('kpower', 2.0)
    rf38[0].irregularVary('dbg',2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 + 2**2 )  
    rf38[0].irregularVary('fscatter', 0.4)
    rf38[0].irregularVary('MQuench', 4.0e12)
    rf38[0].irregularVary('epsquench', 0.01)
    rf38[0].irregularVary('accCeiling', 0.5)
    rf38[0].irregularVary('muQuench', 0.0)
    rf38[0].irregularVary('gaScaleReduction', 1.0 )
    rf38[0].irregularVary('stScaleReduction', 1.0 )
    rf38[0].irregularVary('ZMix', 0.05)
    rf38[0].irregularVary('alphaMRI', 0.1)
    rf38[0].irregularVary('Qlim', 1.35)
    rf38[0].irregularVary('fixedQ', 1.3)
    rf38[0].irregularVary('TOL', 4.0e-4)

    rf39 = NewSetOfExperiments(re01, 'rf39')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 14.1, 9)), rf39[0], widthReductionFactor=100.0 )
    rf39[0].irregularVary('whichAccretionHistory', -112)
    rf39[0].irregularVary('ksuppress', 10.0 )
    rf39[0].irregularVary('kpower', 2.0)
    rf39[0].irregularVary('dbg',2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 + 2**2 )  
    rf39[0].irregularVary('fscatter', 1.0)
    rf39[0].irregularVary('MQuench', 2.0e12)
    rf39[0].irregularVary('epsquench', 0.001)
    rf39[0].irregularVary('accCeiling', 0.5)
    rf39[0].irregularVary('muQuench', 0.0)
    rf39[0].irregularVary('gaScaleReduction', 1.0 )
    rf39[0].irregularVary('stScaleReduction', 1.0 )
    rf39[0].irregularVary('ZMix', 0.5)
    rf39[0].irregularVary('alphaMRI', 0.05)
    rf39[0].irregularVary('Qlim', 1.35)
    rf39[0].irregularVary('fixedQ', 1.3)
    rf39[0].irregularVary('TOL', 4.0e-4)


    # Add a few more galaxies, try out Dekel & Birnboim quenching threshold.
    rf40 = NewSetOfExperiments(re01, 'rf40')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 14.1, 29)), rf40[0], widthReductionFactor=100.0 )
    rf40[0].irregularVary('whichAccretionHistory', -112)
    rf40[0].irregularVary('ksuppress', 10.0 )
    rf40[0].irregularVary('kpower', 2.0)
    rf40[0].irregularVary('dbg',2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 + 2**2 )  
    rf40[0].irregularVary('fscatter', 1.0)
    rf40[0].irregularVary('MQuench', 2.0e12)
    rf40[0].irregularVary('epsquench', 0.001)
    rf40[0].irregularVary('accCeiling', 0.5)
    rf40[0].irregularVary('muQuench', 0.0)
    rf40[0].irregularVary('gaScaleReduction', 1.0 )
    rf40[0].irregularVary('stScaleReduction', 1.0 )
    rf40[0].irregularVary('ZMix', 0.5)
    rf40[0].irregularVary('alphaMRI', 0.05)
    rf40[0].irregularVary('Qlim', 1.35)
    rf40[0].irregularVary('fixedQ', 1.3)
    rf40[0].irregularVary('TOL', 4.0e-4)

    # Decrease accr efficiency in quenched galaxies, bump up ZMix.
    rf41 = NewSetOfExperiments(re01, 'rf41')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 14.1, 29)), rf41[0], widthReductionFactor=2.0 )
    rf41[0].irregularVary('whichAccretionHistory', -112)
    rf41[0].irregularVary('ksuppress', 10.0 )
    rf41[0].irregularVary('kpower', 2.0)
    rf41[0].irregularVary('dbg',2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 + 2**2 )  
    rf41[0].irregularVary('fscatter', 1.0)
    rf41[0].irregularVary('MQuench', 2.0e12)
    rf41[0].irregularVary('epsquench', 0.0001)
    rf41[0].irregularVary('accCeiling', 0.5)
    rf41[0].irregularVary('muQuench', 0.0)
    rf41[0].irregularVary('gaScaleReduction', 1.0 )
    rf41[0].irregularVary('stScaleReduction', 3.0 )
    rf41[0].irregularVary('ZMix', 0.8)
    rf41[0].irregularVary('alphaMRI', 0.05)
    rf41[0].irregularVary('Qlim', 1.35)
    rf41[0].irregularVary('fixedQ', 1.3)
    rf41[0].irregularVary('TOL', 4.0e-4)

    # reduce the scatter in asl a bit. Bump up metallicity in low-mass galaxies
    rf42 = NewSetOfExperiments(re01, 'rf42')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 14.1, 19)), rf42[0], widthReductionFactor=5.0 )
    rf42[0].irregularVary('whichAccretionHistory', -112)
    rf42[0].irregularVary('ksuppress', 10.0 )
    rf42[0].irregularVary('kpower', 2.0)
    rf42[0].irregularVary('dbg',2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 + 2**2 )  
    rf42[0].irregularVary('fscatter', 1.0)
    rf42[0].irregularVary('MQuench', 2.0e12)
    rf42[0].irregularVary('epsquench', 0.00001)
    rf42[0].irregularVary('accCeiling', 0.5)
    rf42[0].irregularVary('muQuench', 0.0)
    rf42[0].irregularVary('gaScaleReduction', 1.0 )
    rf42[0].irregularVary('stScaleReduction', 3.0 )
    rf42[0].irregularVary('ZMix', 0.8)
    rf42[0].irregularVary('alphaMRI', 0.05)
    rf42[0].irregularVary('Qlim', 1.35)
    rf42[0].irregularVary('fixedQ', 1.3)
    rf42[0].irregularVary('TOL', 4.0e-4)


    # up number of galaxies given start time of computation. Try out a two-phase quenching. STart tracking MHalo instead of putting accreted stars in bulge. STILL need to alter colHI modification as appropriate, but that can be done in post
    rf43 = NewSetOfExperiments(re01, 'rf43')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 14.1, 39)), rf43[0], widthReductionFactor=5.0 )
    rf43[0].irregularVary('whichAccretionHistory', -112)
    rf43[0].irregularVary('ksuppress', 10.0 )
    rf43[0].irregularVary('kpower', 2.0)
    rf43[0].irregularVary('dbg',2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 + 2**2 )  
    rf43[0].irregularVary('fscatter', 1.0)
    rf43[0].irregularVary('MQuench', 2.0e12)
    rf43[0].irregularVary('epsquench', 0.00001)
    rf43[0].irregularVary('accCeiling', 0.5)
    rf43[0].irregularVary('muQuench', 0.0)
    rf43[0].irregularVary('gaScaleReduction', 1.0 )
    rf43[0].irregularVary('stScaleReduction', 3.0 )
    rf43[0].irregularVary('ZMix', 0.8)
    rf43[0].irregularVary('alphaMRI', 0.05)
    rf43[0].irregularVary('Qlim', 1.35)
    rf43[0].irregularVary('fixedQ', 1.3)
    rf43[0].irregularVary('TOL', 4.0e-4)

    # quenching during cold streams was a bit too much. Try again! Lower slope of initial metallicity.
    rf44 = NewSetOfExperiments(re01, 'rf44')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 14.1, 19)), rf44[0], widthReductionFactor=5.0 )
    rf44[0].irregularVary('whichAccretionHistory', -112)
    rf44[0].irregularVary('ksuppress', 10.0 )
    rf44[0].irregularVary('kpower', 2.0)
    rf44[0].irregularVary('dbg',2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 + 2**2 )  
    rf44[0].irregularVary('fscatter', 1.0)
    rf44[0].irregularVary('MQuench', 2.0e12)
    rf44[0].irregularVary('epsquench', 0.00001)
    rf44[0].irregularVary('accCeiling', 0.5)
    rf44[0].irregularVary('muQuench', 0.0)
    rf44[0].irregularVary('gaScaleReduction', 1.0 )
    rf44[0].irregularVary('stScaleReduction', 3.0 )
    rf44[0].irregularVary('ZMix', 0.5)
    rf44[0].irregularVary('alphaMRI', 0.05)
    rf44[0].irregularVary('Qlim', 1.35)
    rf44[0].irregularVary('fixedQ', 1.3)
    rf44[0].irregularVary('TOL', 4.0e-4)

    # Add in delay time for mergers, up metallicity for low-mass galaxies
    rf45 = NewSetOfExperiments(re01, 'rf45')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 14.1, 19)), rf45[0], widthReductionFactor=5.0 )
    rf45[0].irregularVary('whichAccretionHistory', -112)
    rf45[0].irregularVary('ksuppress', 10.0 )
    rf45[0].irregularVary('kpower', 2.0)
    rf45[0].irregularVary('dbg',2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 + 2**2 )  
    rf45[0].irregularVary('fscatter', 1.0)
    rf45[0].irregularVary('MQuench', 2.0e12)
    rf45[0].irregularVary('epsquench', 0.00001)
    rf45[0].irregularVary('accCeiling', 0.5)
    rf45[0].irregularVary('muQuench', 0.0)
    rf45[0].irregularVary('gaScaleReduction', 1.0 )
    rf45[0].irregularVary('stScaleReduction', 3.0 )
    rf45[0].irregularVary('ZMix', 0.5)
    rf45[0].irregularVary('alphaMRI', 0.05)
    rf45[0].irregularVary('Qlim', 1.35)
    rf45[0].irregularVary('fixedQ', 1.3)
    rf45[0].irregularVary('TOL', 7.0e-4)

    # Cut off unresolved mergers.
    rf46 = NewSetOfExperiments(re01, 'rf46')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 14.1, 19)), rf46[0], widthReductionFactor=5.0 )
    rf46[0].irregularVary('whichAccretionHistory', -112)
    rf46[0].irregularVary('ksuppress', 10.0 )
    rf46[0].irregularVary('kpower', 2.0)
    rf46[0].irregularVary('dbg',2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 + 2**2 )  
    rf46[0].irregularVary('fscatter', 1.0)
    rf46[0].irregularVary('MQuench', 2.0e12)
    rf46[0].irregularVary('epsquench', 0.00001)
    rf46[0].irregularVary('accCeiling', 0.5)
    rf46[0].irregularVary('muQuench', 0.0)
    rf46[0].irregularVary('gaScaleReduction', 1.0 )
    rf46[0].irregularVary('stScaleReduction', 3.0 )
    rf46[0].irregularVary('ZMix', 0.5)
    rf46[0].irregularVary('alphaMRI', 0.05)
    rf46[0].irregularVary('Qlim', 1.35)
    rf46[0].irregularVary('fixedQ', 1.3)
    rf46[0].irregularVary('TOL', 7.0e-4)

    # Up the cutoff for resolved mergers a bit.
    rf47 = NewSetOfExperiments(re01, 'rf47')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 14.1, 39)), rf47[0], widthReductionFactor=5.0 )
    rf47[0].irregularVary('whichAccretionHistory', -112)
    rf47[0].irregularVary('ksuppress', 10.0 )
    rf47[0].irregularVary('kpower', 2.0)
    rf47[0].irregularVary('dbg',2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 + 2**2 )  
    rf47[0].irregularVary('fscatter', 1.0)
    rf47[0].irregularVary('MQuench', 2.0e12)
    rf47[0].irregularVary('epsquench', 0.00001)
    rf47[0].irregularVary('accCeiling', 0.5)
    rf47[0].irregularVary('muQuench', 0.0)
    rf47[0].irregularVary('gaScaleReduction', 1.0 )
    rf47[0].irregularVary('stScaleReduction', 3.0 )
    rf47[0].irregularVary('ZMix', 0.5)
    rf47[0].irregularVary('alphaMRI', 0.05)
    rf47[0].irregularVary('Qlim', 1.35)
    rf47[0].irregularVary('fixedQ', 1.3)
    rf47[0].irregularVary('TOL', 7.0e-4)

    # Bump resolved merger cut back down to realistic value. Impose restriction that selected tree must have halo mass within half a dex of simulated halo mass. If requested mass lies outside populated and resolved range in sim, use maximum or minimum dex of halo masses.
    # Also reduce initial gas scale length, up initial metallicity a bit.
    rf48 = NewSetOfExperiments(re01, 'rf48')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 14.1, 19)), rf48[0], widthReductionFactor=5.0 )
    rf48[0].irregularVary('whichAccretionHistory', -112)
    rf48[0].irregularVary('ksuppress', 10.0 )
    rf48[0].irregularVary('kpower', 2.0)
    rf48[0].irregularVary('dbg',2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 + 2**2 )  
    rf48[0].irregularVary('fscatter', 1.0)
    rf48[0].irregularVary('MQuench', 2.0e12)
    rf48[0].irregularVary('epsquench', 0.00001)
    rf48[0].irregularVary('accCeiling', 0.5)
    rf48[0].irregularVary('muQuench', 0.0)
    rf48[0].irregularVary('gaScaleReduction', 2.0 )
    rf48[0].irregularVary('stScaleReduction', 3.0 )
    rf48[0].irregularVary('ZMix', 0.5)
    rf48[0].irregularVary('alphaMRI', 0.05)
    rf48[0].irregularVary('Qlim', 1.35)
    rf48[0].irregularVary('fixedQ', 1.3)
    rf48[0].irregularVary('TOL', 7.0e-4)


    # Expand mass range a bit. Reduce initial scale lengths a bit. Uncap the metal diffusion coefficient.
    rf49 = NewSetOfExperiments(re01, 'rf49')
    setKnownProperties( np.power(10.0, np.linspace(9.5, 15.1, 19)), rf49[0], widthReductionFactor=5.0 )
    rf49[0].irregularVary('whichAccretionHistory', -112)
    rf49[0].irregularVary('ksuppress', 10.0 )
    rf49[0].irregularVary('kpower', 2.0)
    rf49[0].irregularVary('dbg',2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 + 2**2 )  
    rf49[0].irregularVary('fscatter', 1.0)
    rf49[0].irregularVary('MQuench', 2.0e12)
    rf49[0].irregularVary('epsquench', 0.00001)
    rf49[0].irregularVary('accCeiling', 0.5)
    rf49[0].irregularVary('muQuench', 0.0)
    rf49[0].irregularVary('gaScaleReduction', 3.0 )
    rf49[0].irregularVary('stScaleReduction', 4.0 )
    rf49[0].irregularVary('ZMix', 0.5)
    rf49[0].irregularVary('alphaMRI', 0.05)
    rf49[0].irregularVary('Qlim', 1.35)
    rf49[0].irregularVary('fixedQ', 1.3)
    rf49[0].irregularVary('TOL', 7.0e-4)


    # Stronger enforcement of Q=Qf basically
    rf50 = NewSetOfExperiments(re01, 'rf50')
    setKnownProperties( np.power(10.0, np.linspace(9.5, 15.1, 19)), rf50[0], widthReductionFactor=5.0 )
    rf50[0].irregularVary('whichAccretionHistory', -112)
    rf50[0].irregularVary('ksuppress', 10.0 )
    rf50[0].irregularVary('kpower', 2.0)
    rf50[0].irregularVary('dbg',2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 + 2**2 )  
    rf50[0].irregularVary('fscatter', 1.0)
    rf50[0].irregularVary('MQuench', 2.0e12)
    rf50[0].irregularVary('epsquench', 0.00001)
    rf50[0].irregularVary('accCeiling', 0.5)
    rf50[0].irregularVary('muQuench', 0.0)
    rf50[0].irregularVary('gaScaleReduction', 3.0 )
    rf50[0].irregularVary('stScaleReduction', 4.0 )
    rf50[0].irregularVary('ZMix', 0.5)
    rf50[0].irregularVary('alphaMRI', 0.05)
    rf50[0].irregularVary('Qlim', 1.35)
    rf50[0].irregularVary('fixedQ', 1.3)
    rf50[0].irregularVary('TOL', 7.0e-4)

    # THE ONLY THING WE'RE DOING HERE IS RE-CAPPING KAPPAMETALS.
    rf51 = NewSetOfExperiments(re01, 'rf51')
    setKnownProperties( np.power(10.0, np.linspace(9.5, 15.1, 19)), rf51[0], widthReductionFactor=5.0 )
    rf51[0].irregularVary('whichAccretionHistory', -112)
    rf51[0].irregularVary('ksuppress', 10.0 )
    rf51[0].irregularVary('kpower', 2.0)
    rf51[0].irregularVary('dbg',2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 + 2**2 )  
    rf51[0].irregularVary('fscatter', 1.0)
    rf51[0].irregularVary('MQuench', 2.0e12)
    rf51[0].irregularVary('epsquench', 0.00001)
    rf51[0].irregularVary('accCeiling', 0.5)
    rf51[0].irregularVary('muQuench', 0.0)
    rf51[0].irregularVary('gaScaleReduction', 3.0 )
    rf51[0].irregularVary('stScaleReduction', 4.0 )
    rf51[0].irregularVary('ZMix', 0.5)
    rf51[0].irregularVary('alphaMRI', 0.05)
    rf51[0].irregularVary('Qlim', 1.35)
    rf51[0].irregularVary('fixedQ', 1.3)
    rf51[0].irregularVary('TOL', 7.0e-4)

    # Attempt to improve stability - increase SigSt floor, decrease eta, decrease number of passive populations.
    rf52 = NewSetOfExperiments(re01, 'rf52')
    setKnownProperties( np.power(10.0, np.linspace(9.5, 15.1, 19)), rf52[0], widthReductionFactor=5.0 )
    rf52[0].irregularVary('whichAccretionHistory', -112)
    rf52[0].irregularVary('ksuppress', 10.0 )
    rf52[0].irregularVary('kpower', 2.0)
    rf52[0].irregularVary('dbg',2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 + 2**2 )  
    rf52[0].irregularVary('fscatter', 1.0)
    rf52[0].irregularVary('MQuench', 2.0e12)
    rf52[0].irregularVary('epsquench', 0.00001)
    rf52[0].irregularVary('accCeiling', 0.5)
    rf52[0].irregularVary('muQuench', 0.0)
    rf52[0].irregularVary('gaScaleReduction', 3.0 )
    rf52[0].irregularVary('stScaleReduction', 4.0 )
    rf52[0].irregularVary('ZMix', 0.5)
    rf52[0].irregularVary('alphaMRI', 0.05)
    rf52[0].irregularVary('Qlim', 1.35)
    rf52[0].irregularVary('fixedQ', 1.3)
    rf52[0].irregularVary('TOL', 7.0e-4)
    rf52[0].irregularVary('minSigSt', 10.0)

    # Try some more on stability - time step this time
    rf53 = NewSetOfExperiments(re01, 'rf53')
    setKnownProperties( np.power(10.0, np.linspace(9.5, 15.1, 19)), rf53[0], widthReductionFactor=5.0 )
    rf53[0].irregularVary('whichAccretionHistory', -112)
    rf53[0].irregularVary('ksuppress', 10.0 )
    rf53[0].irregularVary('kpower', 2.0)
    rf53[0].irregularVary('dbg',2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 + 2**2 )  
    rf53[0].irregularVary('fscatter', 1.0)
    rf53[0].irregularVary('MQuench', 2.0e12)
    rf53[0].irregularVary('epsquench', 0.00001)
    rf53[0].irregularVary('accCeiling', 0.5)
    rf53[0].irregularVary('muQuench', 0.0)
    rf53[0].irregularVary('gaScaleReduction', 3.0 )
    rf53[0].irregularVary('stScaleReduction', 4.0 )
    rf53[0].irregularVary('ZMix', 0.5)
    rf53[0].irregularVary('alphaMRI', 0.05)
    rf53[0].irregularVary('Qlim', 1.35)
    rf53[0].irregularVary('fixedQ', 1.3)
    rf53[0].irregularVary('TOL', 1.0e-4)
    rf53[0].irregularVary('minSigSt', 10.0)

    # Exactly the same as rf54, but we've made stricter cuts on the halos we're allowed to use to avoid ridiculously large merged halo masses.
    rf54 = NewSetOfExperiments(rf53, 'rf54')

    # Narrow the mass range again. Bump up the scale lengths. Bump up Q's
    rf55 = NewSetOfExperiments(re01, 'rf55')
    setKnownProperties( np.power(10.0, np.linspace(8.5, 14.1, 19)), rf55[0], widthReductionFactor=5.0 )
    rf55[0].irregularVary('whichAccretionHistory', -112)
    rf55[0].irregularVary('ksuppress', 10.0 )
    rf55[0].irregularVary('kpower', 2.0)
    rf55[0].irregularVary('dbg',2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 + 2**2 )  
    rf55[0].irregularVary('fscatter', 1.0)
    rf55[0].irregularVary('MQuench', 2.0e12)
    rf55[0].irregularVary('epsquench', 1.0e-5)
    rf55[0].irregularVary('accCeiling', 0.5)
    rf55[0].irregularVary('muQuench', 0.0)
    rf55[0].irregularVary('gaScaleReduction', 3.0 )
    rf55[0].irregularVary('stScaleReduction', 4.0 )
    rf55[0].irregularVary('ZMix', 0.5)
    rf55[0].irregularVary('alphaMRI', 0.05)
    rf55[0].irregularVary('Qlim', 1.95)
    rf55[0].irregularVary('fixedQ', 1.9)
    rf55[0].irregularVary('TOL', 6.0e-4)
    rf55[0].irregularVary('minSigSt', 10.0)
    
    # Increase gas accretion ceiling, increase initial metallicity slope
    rf56 = NewSetOfExperiments(re01, 'rf56')
    setKnownProperties( np.power(10.0, np.linspace(8.5, 14.1, 19)), rf56[0], widthReductionFactor=5.0 )
    rf56[0].irregularVary('whichAccretionHistory', -112)
    rf56[0].irregularVary('ksuppress', 10.0 )
    rf56[0].irregularVary('kpower', 2.0)
    rf56[0].irregularVary('dbg',2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 + 2**2 )  
    rf56[0].irregularVary('fscatter', 1.0)
    rf56[0].irregularVary('MQuench', 2.0e12)
    rf56[0].irregularVary('epsquench', 1.0e-5)
    rf56[0].irregularVary('accCeiling', 1.0)
    rf56[0].irregularVary('muQuench', 0.0)
    rf56[0].irregularVary('gaScaleReduction', 3.0 )
    rf56[0].irregularVary('stScaleReduction', 4.0 )
    rf56[0].irregularVary('ZMix', 0.1)
    rf56[0].irregularVary('alphaMRI', 0.05)
    rf56[0].irregularVary('Qlim', 1.95)
    rf56[0].irregularVary('fixedQ', 1.9)
    rf56[0].irregularVary('TOL', 6.0e-4)
    rf56[0].irregularVary('minSigSt', 10.0)


    # Narrow mass range - no more tiny dwarfs. Lower Q limits, reduce the scaleReduction parameters
    rf57 = NewSetOfExperiments(re01, 'rf57')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 14.1, 19)), rf57[0], widthReductionFactor=5.0 )
    rf57[0].irregularVary('whichAccretionHistory', -112)
    rf57[0].irregularVary('ksuppress', 10.0 )
    rf57[0].irregularVary('kpower', 2.0)
    rf57[0].irregularVary('dbg',2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 + 2**2 )  
    rf57[0].irregularVary('fscatter', 1.0)
    rf57[0].irregularVary('MQuench', 2.0e12)
    rf57[0].irregularVary('epsquench', 1.0e-5)
    rf57[0].irregularVary('accCeiling', 1.0)
    rf57[0].irregularVary('muQuench', 0.0)
    rf57[0].irregularVary('gaScaleReduction', 1.5 )
    rf57[0].irregularVary('stScaleReduction', 2.0 )
    rf57[0].irregularVary('ZMix', 0.1)
    rf57[0].irregularVary('alphaMRI', 0.05)
    rf57[0].irregularVary('Qlim', 1.35)
    rf57[0].irregularVary('fixedQ', 1.3)
    rf57[0].irregularVary('TOL', 6.0e-4)
    rf57[0].irregularVary('minSigSt', 10.0)

    # Bump up accretion scale lengths
    rf58 = NewSetOfExperiments(re01, 'rf58')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 14.1, 19)), rf58[0], widthReductionFactor=5.0 )
    rf58[0].irregularVary('whichAccretionHistory', -112)
    rf58[0].irregularVary('ksuppress', 10.0 )
    rf58[0].irregularVary('kpower', 2.0)
    rf58[0].irregularVary('dbg',2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 + 2**2 )  
    rf58[0].irregularVary('fscatter', 1.0)
    rf58[0].irregularVary('MQuench', 2.0e12)
    rf58[0].irregularVary('epsquench', 1.0e-3)
    rf58[0].irregularVary('accCeiling', 1.0)
    rf58[0].irregularVary('muQuench', 0.0)
    rf58[0].irregularVary('gaScaleReduction', 1.5 )
    rf58[0].irregularVary('stScaleReduction', 2.0 )
    rf58[0].irregularVary('ZMix', 0.1)
    rf58[0].irregularVary('alphaMRI', 0.05)
    rf58[0].irregularVary('Qlim', 1.35)
    rf58[0].irregularVary('fixedQ', 1.3)
    rf58[0].irregularVary('TOL', 6.0e-4)
    rf58[0].irregularVary('minSigSt', 10.0)


    # Bump up initial gas fractions
    rf59 = NewSetOfExperiments(re01, 'rf59')
    setKnownProperties( np.power(10.0, np.linspace(10.5, 14.1, 19)), rf59[0], widthReductionFactor=5.0 )
    rf59[0].irregularVary('whichAccretionHistory', -112)
    rf59[0].irregularVary('ksuppress', 10.0 )
    rf59[0].irregularVary('kpower', 2.0)
    rf59[0].irregularVary('dbg',2**1+2**0+2**13 + 2**7 + 2**5 + 2**16 + 2**2 )  
    rf59[0].irregularVary('fscatter', 1.0)
    rf59[0].irregularVary('MQuench', 2.0e12)
    rf59[0].irregularVary('epsquench', 1.0e-3)
    rf59[0].irregularVary('accCeiling', 1.0)
    rf59[0].irregularVary('muQuench', 0.0)
    rf59[0].irregularVary('gaScaleReduction', 1.5 )
    rf59[0].irregularVary('stScaleReduction', 2.0 )
    rf59[0].irregularVary('ZMix', 0.1)
    rf59[0].irregularVary('alphaMRI', 0.05)
    rf59[0].irregularVary('Qlim', 1.35)
    rf59[0].irregularVary('fixedQ', 1.3)
    rf59[0].irregularVary('TOL', 6.0e-4)
    rf59[0].irregularVary('minSigSt', 10.0)

    logVars = [ 1, 1, 1, 1, 0, 0, 1, 1, 0, 1, 1, 1, 1, 0, 0, 1, 0]
#    emceeparams = [-0.95820208,  0.12281711,  0.1966165,  -0.78667301,  0.00973009, 3.31282354, 0.10012698,  0.04621494,  0.55814651,  0.98668778,  0.18025846, -0.71183777, -0.29659053,  0.28670522,  0.9971759,   1.66382228,  0.42225522]
#    for i,lg in enumerate(logVars):
#        if lg==1:
#            emceeparams[i]=10.0**emceeparams[i]
#    rf60 = experFromBroadMCMC(emceeparams, name='rf60')
#
#
#    emceeparams = [-0.94768456, 0.33098108, -0.6839395, 0.81062651, 0.85924765, -0.78581627, 0.15923048, -0.07639685, 0.4621238, -0.01500173, 0.14515758, -2.04099439, -2.26236079, 0.41038537, 0.1742757, 1.35731629, 0.57266408]
#    for i,lg in enumerate(logVars):
#        if lg==1:
#            emceeparams[i]=10.0**emceeparams[i]
#    rf61 = experFromBroadMCMC(emceeparams, name='rf61')
#
#    emceeparams = [-0.54814292, 0.2800687, 0.82856872, -0.30015427, -1.13556896, -0.13497688, -0.57514515, -0.10468448, 0.23392629, -0.0296846, -0.38837726, -0.8771524, -6.868443, 0.90627398, -0.04635603, -1.14274305, 0.56011981]
#    for i,lg in enumerate(logVars):
#        if lg==1:
#            emceeparams[i]=10.0**emceeparams[i]
#    rf62 = experFromBroadMCMC(emceeparams, name='rf62')

    #emceeparams = [0.26995166, 1.70114322, 2.30873267, 0.27856887, 0.33193819, -0.24731145, 1.6723297, 2.45477307, 0.50113889, 1.51510048, 1.5418113, 0.044828, 0.01765032, 0.55969964, 0.42431146, 1.19370591, 0.20405244 ]
    emceeparams = [ 1.67282517e-01,   4.28844668e+00,   1.36805656e+00,   2.69675101e+00, -4.16293369e-01,  -1.14871782e-01,   3.43607914e+00,   3.00678314e+00, 1.73255938e-01,   1.18432465e+00,   1.46326173e+00,   5.22146369e-02, 4.15303418e-03,   4.87055898e-01,   3.25786672e-01,   7.03059668e-01,
   3.20891765e-01]
    #for i,lg in enumerate(logVars):
    #    if lg==1:
    #        emceeparams[i]=10.0**emceeparams[i]
    #rf63 = experFromBroadMCMC(emceeparams, name='rf63')

    # include 0.3 dex scatter in accretion radius
    #rf64 = experFromBroadMCMC(emceeparams, name='rf64')

    # include 0.1 dex scatter in accretion radius
    #rf65 = experFromBroadMCMC(emceeparams, name='rf65')


    # include 0.15 dex scatter in accretion radius
    #rf66 = experFromBroadMCMC(emceeparams, name='rf66')

#    # steepen dependence of muNorm on halo mass.
#    emceeparams = [ 1.67282517e-01,   4.28844668e+00,   1.36805656e+00,   2.69675101e+00, -4.16293369e-01,  -1.14871782e-01,   3.43607914e+01,   3.00678314e+00, 1.73255938e-01,   1.18432465e+00,   1.46326173e+00,   5.22146369e-02, 4.15303418e-03,   4.87055898e-01,   3.25786672e-01,   7.03059668e-01,
#   3.20891765e-01]
#    #rf67 = experFromBroadMCMC(emceeparams, name='rf67')
#
#
#    emceeparams = [  1.81771436e-01, 2.40347748e+00, 2.49619543e+00, 1.76206344e+00, 3.28755338e-02, -5.28290494e-01, 5.98066114e+00, 3.66100610e-01, 3.90118770e-01, 1.09498184e+00, 1.43065291e+00, 4.29138804e-02, 3.80797987e-03, 3.81670627e-01, 2.04179431e-01, 2.74669519e+00, 3.51085258e-01] 
#    #rf68 = experFromBroadMCMC(emceeparams, name='rf68')
#
#    emceeparams = [2.48980815e-01, 2.53913046e+00, 1.94713503e+00,  1.73487193e+00, 1.22752777e-01, 1.89173574e-01, 8.57394429e+01, -9.46127811e-01, 3.09692786e+00, 6.24628784e-01, 1.15853145e+00, 1.62254103e+00, 1.03954926e-01, 8.14383174e-03, 6.01172382e-01, 3.44383014e-01, 2.96100846e+00, 3.88973404e-01]
#    rf69 = experFromBroadMCMC(emceeparams, name='rf69')
#
#    emceeparams = [1.73170283e-01,   2.14054038e+00,   1.83573302e+00,  2.61271723e+00, 7.30987984e-01, 1.32267757e+00, 2.24417353e+00,  -5.28408649e-01, 1.24067677e+00, 7.51881042e-01, 1.43512791e+00,   1.22244535e+00, 1.21011874e-01, 4.10263377e-04, 4.81557504e-01, 3.69617294e-01, 5.54974644e-01, 3.58057205e-01 ]
#    rf70 = experFromBroadMCMC(emceeparams, name='rf70')
#
#    emceeparams[-3] = -0.1 # adjust the offset in the concentration relation
#    rf71 = experFromBroadMCMC(emceeparams, name='rf71')
#
#    emceeparams[7] = -0.4284  # adjust the scaling of MLF with halo mass
#    rf72 = experFromBroadMCMC(emceeparams, name='rf72')
#
#
#    # the optimizer found a better fit!
#    emceeparams = [0.11179691,  3.97940566,  1.11597102,  3.81029117,  1.07708097,  2.34905049,
#  0.21486323, -1.94169391,  1.24917886,  0.90404624,  2.59248226,  1.12908429,
#  0.06523725,  0.04544116,  0.31328032,  0.32170412,  0.57426263,  0.02801333]
#    rf73 = experFromBroadMCMC(emceeparams, name='rf73')
#
#    rf74 = NewSetOfExperiments( rf73, 'rf74')[0]
#    rf74.irregularVary('RfREC', 0.9)
#    rf74.irregularVary('dbg', 2**4 + 2**2 + 2**1 + 2**0 + 2**13 + 2**7 + 2**6)
#
#    ## same run, but now we've altered a few bits of the code to disitnguish between instantaneous and asymptotic RfREC.
#    rf75=NewSetOfExperiments(rf74, 'rf75')[0]
#
#    # go from 4 to 20 passive stellar populations to get finer gradation of mass return
#    rf76=NewSetOfExperiments(rf75, 'rf76')[0]
#
#
#
#
#    ### first optimizer result from broad10, same as the last except with non-instantaneous recylcing.
#    #emceeparams = [1.51177585e-01, 2.13587733e+00, 1.72771535e+00, 2.48777103e+00, 5.14946703e-01, 1.42377424e+00, 6.24287175e+00, -1.64962558e+00, 4.31974567e+00, 8.94772733e-01, 1.43807107e+00, 1.51001976e+00, 5.53001724e-02, 2.83883300e-03, 3.29797917e-01, 2.69280628e-01, 2.41255451e+00, 4.63265827e-01]
#    #rf77 = experFromBroadMCMC(emceeparams, name='rf77')
#
#    # re-run the best fit from previous optimizer with updated recycling parameters
#    rf78 = NewSetOfExperiments(rf74, 'rf78')



    #emceeparams = [2.49902380e-01, 2.54581984e+00, 2.96576075e+00, 4.75811993e+00, -2.18843374e+00, 3.60160191e-01, 1.48198009e+00, -1.72415498e+00, 1.22109246e+00, 3.75604390e-01, 8.34320543e-01, 1.63031433e+00, 4.20094711e-02, 1.78703468e-03, 8.51316293e-01, 3.20449127e-01, 4.13447168e+00, 2.42702440e-01, 3.27507640e-01 ]
    #emceeparams = [ 1.41977729e-01,   2.03502540e+00,   2.02360753e+00,   2.01127027e+00, 2.56584739e-02,  -1.89348632e-02,   1.07203799e+00,  -9.80149073e-01, 1.00975501e+00,   4.99324933e-01,   1.50177845e+00,   1.48359195e+00, 4.94927969e-02,  9.79999389e-04,  9.98857856e-01,   2.85701876e-01, 9.59552777e-01,   9.02414277e-05,   9.91998674e-03] 
    #rf79 = experFromBroadMCMC(emceeparams, name='rf79')

#    emceeparams = [ 0.3512968,   3.91202004,  3.41454232,  3.22847406, -0.52552445,  2.60129093, 4.40972677, -1.47069249,  1.25916476,  0.63954234,  1.82215254,  1.46210786, 0.05488134,  0.04106005,  0.24240757,  0.47092227,  2.25026276,  0.36920633, 0.01555641, 0.0, 2.0e12 ] # 0.8
#    rf80 = experFromBroadMCMC(emceeparams, name='rf80')
#
#    emceeparams = [ 0.3512968,   3.91202004,  3.41454232,  3.22847406, -0.52552445,  2.60129093, 4.40972677, -1.47069249,  1.25916476,  0.63954234,  1.82215254,  1.46210786, 0.05488134,  0.04106005,  0.24240757,  0.47092227,  2.25026276,  0.36920633, 0.01555641, 1.0, 2.0e12 ] # 0.8
#    rf81 = experFromBroadMCMC(emceeparams, name='rf81')
#
#    emceeparams = [ 0.3512968,   3.91202004,  3.41454232,  3.22847406, -0.52552445,  2.60129093, 4.40972677, -1.47069249,  1.25916476,  0.63954234,  1.82215254,  1.46210786, 0.05488134,  0.04106005,  0.24240757,  0.47092227,  2.25026276,  0.36920633, 0.01555641, .5, 2.0e12 ] # 0.8
#    rf82 = experFromBroadMCMC(emceeparams, name='rf82')
#
#    ## awk... fixed duplicate dbg statements, some issues in c code.
#    rf83 = experFromBroadMCMC(emceeparams, name='rf83')
#
#    ## fix bug in IA rate.
#    rf84 = experFromBroadMCMC(emceeparams, name='rf84')
#
#    emceeparams = [  1.80232948e-01,   1.14976039e+00,   5.40065364e+00,   1.69857050e+00, -9.44813987e-01,  -8.53922447e-01,   9.47551915e-03,  -3.08660831e+00, 7.75058114e-01,   5.11183715e-01,   1.18276323e+00,   2.94992317e+00, 4.68548647e-02,   2.79680127e-04,   1.08525619e-01,   1.54925443e-01, 4.15764357e+00,   3.28062195e-01,   9.12530440e-03,  0, 2.83422259e+11] # , 6.86571666e-01]
#    rf85 = experFromBroadMCMC(emceeparams, name='rf85')
#
#    emceeparams = [  1.39192613e-01,   2.06852503e+00,   1.47353675e+00,   1.97365750e+00, 5.37224908e-01,   1.17595949e+00,   1.08963518e+00,  -5.08071210e-01, 1.01502597e+00,   5.17380183e-02,   5.36199804e+00,   1.25992157e+00, 6.23709052e-02,   1.72535928e-04,   9.15648977e-01,   1.06622955e-01, 5.88668979e+00,   1.79678213e-01,   6.00854464e-03,   0.00000000e+00, 9.18293025e+11] #,   3.53606946e-01]
#    rf86 = experFromBroadMCMC(emceeparams, name='rf86')
#
#    # decrease rf87 to match up with what's going on with the gas.
#    rf87 = experFromBroadMCMC(emceeparams, name='rf87')
#
#
#    emceeparams = [  1.16493377e-01,   6.85441565e-01,   2.53454237e+00,   4.66205970e+00, 7.21672391e-01,  -9.65895952e-01,   3.31207773e+00,  -8.40086055e-01, 5.10900160e+00,   4.37085835e-01,   2.12261668e+00,   1.59251012e+00, 8.54462905e-02,   3.48195437e-03,   4.07820701e-01,   1.84455124e-01, 6.85178180e-01,   2.17577982e-01,   8.94197775e-03,   2.00963528e-01, 1.18649645e+12] #,   5.11828699e-01]
#    rf88 = experFromBroadMCMC(emceeparams, name='rf88')
#
#    # less violent heating. Does it work?
#    rf89 = experFromBroadMCMC(emceeparams, name='rf89')
#
#    rf90 = experFromBroadMCMC(emceeparams, name='rf90')
#
#    emceeparams = [ 1.35219791e-01,   2.18557429e+00,   2.64537791e+00,   5.22921628e+00, 7.76397971e-01,  -5.92566917e-01,   4.60624871e+00,  -6.51806325e-01, 1.27517630e+00,   3.39500593e-01,   2.42629432e+00,   1.42712530e+00, 7.97661535e-02,   1.86516526e-02,   4.71407757e-01,   5.44052515e-02, 4.15950062e-01,   3.89348706e-01,   8.46125736e-03,   7.44191600e-01, 2.14946325e+12 ] #,   5.00755873e-01]
#    rf91 = experFromBroadMCMC(emceeparams, name='rf91')
#
#    # add in momentum from SNe
#    rf92 = experFromBroadMCMC(emceeparams, name='rf92')
#
#    # double IA rate
#    rf93 = experFromBroadMCMC(emceeparams, name='rf93')
#
#    # further increase IA. Also add <p/m_*>/(3000 km/s) as a free parameter, decrease NPassive to 10, add back in dsigdt from delayed recycling
#    rf94 = experFromBroadMCMC(emceeparams, name='rf94')

##############
#    emceeparams = [  1.12948059e-01,   5.17252188e+00,   4.98785782e+00,   3.76997443e+00, 1.27319781e+00,  -5.05380872e-01,   5.81396593e-01,  -7.70427023e-01, 3.79841077e+00,   7.61617353e-01,  2.73556160e+00,   1.05424389e+00, 8.16552083e-02,   9.47362160e-02,  9.15940841e-01,  -4.43847562e-02, 3.17327192e+00,   1.66311313e-01,  7.80310015e-03,   1.16103936e+00, 8.16145236e+11,   1.43163698e+00] #,  2.16543541e-01] 
#    rf95 = experFromBroadMCMC(emceeparams, name='rf95')
#
#    emceeparams = [  1.27320109e-01,   2.03198583e+00,   2.81638895e+00,   4.10604035e+00, 7.75410463e-01,   6.55527688e-01,   4.14957777e+00,  -8.91390146e-01, 1.28767238e+00,   6.07316687e-01,   1.62578010e+00,   1.87730986e+00, 3.96195724e-02,   1.24754293e-02,   5.32537819e-01,   2.72661354e-01, 1.08239087e+00,   4.54374209e-01,   1.31894607e-02,   3.62871290e-01, 1.01579812e+12,   9.34901039e-01] # ,   5.82330509e-01]
#    rf96 = experFromBroadMCMC(emceeparams, name='rf96')
#
#
#    ### the result of many days of emcee'ing. Last best model before we switch which relations we're fitting to
#    emceeparams = [  1.51204987e-01, 2.90753988e+00, 2.53590703e+00, 2.55515229e+00, -4.19954509e-01, 8.13925341e-01, 1.68172107e+01, -7.55461620e-01, 1.56570776e+00, 6.18467765e-01, 1.80706415e+00, 1.90444545e+00, 5.13267388e-02, 1.24866660e-02, 5.13130919e-01, 2.46723930e-01, 1.11665310e+00, 3.86496244e-01, 1.15092140e-02, 4.00102520e-01, 1.11230673e+12, 1.32207901e+00] #, 4.82545535e-01]
#    rf97 = experFromBroadMCMC(emceeparams, name='rf97')
#
#    # A few days of emcee'ing with the new relations
#    emceeparams = [  1.73825694e-01,   2.96491086e+00,   2.50420523e+00,   3.19211065e+00, 3.23198361e-01,   1.44217502e+00,   8.68582876e+00,  -1.85280903e+00, 1.24252315e+00,   7.14531454e-01,   1.32442901e+00,   1.90499136e+00, 1.15474744e-01,   9.79676001e-03,   4.52515600e-01,   3.60500105e-01, 2.87259564e+00,   2.82952826e-01,   9.21833546e-03,   4.13450538e-01, 1.59343292e+12,   6.39769810e-01] #,   3.81237447e-01]
#    rf98 = experFromBroadMCMC(emceeparams, name='rf98')
#
#    emceeparams = [  1.76149012e-01,   2.71385761e+00,   2.43095960e+00,   2.56258037e+00, -5.22815474e-01,  -7.30050429e-01,   5.96476522e+00,  -1.95328561e+00, 1.13920495e+00,   6.26490351e-01,   1.57867191e+00,   1.77166604e+00, 6.13678555e-02,   6.36513703e-03,   5.42225312e-01,   1.54471933e-01, 1.69720803e+00,   4.65370474e-01,   1.28680215e-02,   4.79132819e-01, 1.64818086e+12,   9.93276414e-01]#   5.41798936e-01]
#    rf99 = experFromBroadMCMC(emceeparams, name='rf99')
#
#    emceeparams = [  1.85266281e-01,   2.79794991e+00,   2.54853720e+00,   2.51613844e+00, -1.19166589e-01,   5.32796165e-01,   1.51824583e+01,  -2.00867324e+00, 1.10001494e+00,   5.74663846e-01,   2.14006294e+00,   2.23154719e+00, 4.64459910e-02,   3.85768179e-03,   5.02682083e-01,   2.46641441e-01, 1.11958517e+00,   3.74532154e-01,   1.62304725e-02,   3.58278877e-01, 1.47395287e+12,   1.60148443e+00,  4.75410472e-01]
#    rf100 = experSuiteFromBroadMCMC(emceeparams, 'rf100')
#
#    rf100fid = experFromBroadMCMC(emceeparams[:-1], name='rf100fid')
#
#    # Drastically lower enInjFac to see its effects.
#    emceeparams[-2] = 0.4
#    rf101 = experFromBroadMCMC(emceeparams[:-1], name='rf101')
#    
#    
#    # a new favorite?
#    emceeparams = [  1.73507751e-01,   2.62295799e+00,   4.82741016e+00,  3.82417131e+00, -1.27362280e+00,  -4.24929960e-02,   2.48449788e+00,  -2.09622781e+00, 9.68969135e-01,   5.55439266e-01,   3.05669853e+00,   1.94043358e+00, 6.19135068e-02,   1.49455605e-02,   6.72660290e-01,   2.01754396e-01, 9.60097006e-01,   2.16515446e-01,   9.10342168e-03,   4.68792610e-01, 1.76369189e+12,   1.51166802e+00] #,   5.68709729e-01]
#    rf102 = experFromBroadMCMC(emceeparams, name='rf102')
#
#    # If we ignore the prior...
#    emceeparams = [  1.76948118e-01,   3.32946101e+00,   3.62603234e+00,   2.77719403e+00, -8.74364524e-02,  -5.96788852e-01,   4.51930901e+01,  -1.41681696e+00, 2.20558201e+00,   4.12333598e-01,   1.84774957e+00,   1.93770620e+00, 1.10370814e-01,   2.73787964e-02,   4.07730492e-01,   1.58351852e-01, 2.46275879e+00,   5.99749929e-01,   1.41721075e-02,   6.10882377e-01, 3.50207946e+12,   9.47220561e-01] #   4.98249559e-01]
#    rf103 = experFromBroadMCMC(emceeparams, name='rf103')
#
#    # new favorite regardless of prior!
#    emceeparams = [  1.72012859e-01, 2.66125590e+00, 2.53303333e+00, 2.57911719e+00, 2.52859522e-01, 1.55999029e+00, 4.25882949e+01, -7.70370596e-01, 1.25275257e+00, 4.79130366e-01, 1.93540669e+00, 2.26556567e+00, 4.77998874e-02, 8.03224171e-03, 5.88022909e-01, 1.68901831e-01, 1.43436905e+00, 3.90167366e-01, 8.18311797e-03, 2.95868494e-01, 2.22674061e+12, 8.60764574e-01]#   5.65977320e-01]
#    rf104 = experFromBroadMCMC(emceeparams, name='rf104')
#
#
#    emceeparams = [  1.72012859e-01, 2.66125590e+00, 2.53303333e+00, 2.57911719e+00, 2.52859522e-01, 1.55999029e+00, 4.25882949e+01, -7.70370596e-01, 1.25275257e+00, 4.79130366e-01, 1.93540669e+00, 2.26556567e+00, 4.77998874e-02, 8.03224171e-03, 5.88022909e-01, 1.68901831e-01, 1.43436905e+00, 3.90167366e-01, 8.18311797e-03, 2.95868494e-01, 2.22674061e+12, 8.60764574e-01, 5.65977320e-01]
#    rf105 = experSuiteFromBroadMCMC(emceeparams, 'rf105')
#
#    rf106 = experFromBroadMCMC(emceeparams[:-1], 'rf106') ## 104 with more galaxies
#
#    # New favorite after another week of fake emcee'ing
#    emceeparams = [ 1.10322088e-01, 1.80024732e+00, 3.32947161e+00, 1.19564513e+00, 3.86749403e-01, 2.00715127e-02, 8.13224850e+00, -9.33680236e-01, 2.15900682e+00, 5.47992636e-01, 1.74040208e+00, 1.86303401e+00, 8.18885710e-02, 6.45012428e-02, 4.83035351e-01, 3.13063917e-01, 1.52606712e+00, 2.64851123e-01, 4.49792373e-03, 7.35643672e-01, 1.44936594e+12, 7.07431782e-01, 5.32829088e-01]
#    accHistories= list(np.random.random(30))
#    rf107 = experFromBroadMCMC(emceeparams[:-1], 'rf107', accHistories=accHistories) # fiducial run w/ best params
#
#    rf108 = experFromBroadMCMC(emceeparams[:-1], 'rf108', accHistories=None, ngal=300) # fiducial run w/ best params, and way more galaxies for display purposes
#
#    rf109 = experSuiteFromBroadMCMC(emceeparams, 'rf109', accHistories=accHistories) # vary, but keep the accretion histories the same

    emceeparams = [ 9.71927492e-02, 2.39575167e+00, 1.65636256e+00, 3.67255159e+00, -1.12973995e-01, -3.85559567e-01, 1.20989755e+01, -5.00418729e-01, 8.52150558e-01, 2.76607985e-01, 3.49289586e+00, 1.25506559e+00, 7.21157422e-02, 1.10167363e-03, 5.19270812e-01, -5.90627188e-02, 9.28387452e-01, 2.44104897e-01, 9.26267841e-03, 6.21561009e-01, 8.11079253e+11, 2.11803502e+00, -1.38868912e-01, 6.25674577e-01]
    rf110 = experFromBroadMCMC(emceeparams[:-1], 'rf110')

    emceeparams = [ 1.33010836e-01, 1.31714334e+00, 1.83799976e+00, 3.42329017e+00, -9.01222517e-01, 3.28311257e-01, 2.12089398e+01, -6.05880013e-01, 6.58061592e-01, 5.33827439e-01, 2.08666328e+00, 1.95270546e+00, 4.71171595e-02, 1.35239736e-03, 6.85192309e-01, -1.09599775e-01, 1.00636454e+00, 1.74155775e-01, 8.53514642e-03, 4.00511772e-01, 1.11512757e+12, 2.22619895e+00, -1.30586821e-01, 3.94384422e-01]
    rf111 = experFromBroadMCMC(emceeparams[:-1], 'rf111')

    # run for a bit longer -- fakemcmc17c 
    emceeparams = [ 1.44656471e-01, 1.94694047e+00, 2.46300115e+00, 2.52780687e+00, 4.14257376e-02, -9.24764117e-02, 6.03022138e+00, -1.71412505e+00, 2.75050207e+00, 5.03191815e-01, 2.64146528e+00, 2.93923418e+00, 4.93805277e-02, 1.33649809e-02, 6.30847392e-01, 7.70793830e-02, 6.40127324e-01, 2.75077929e-01, 1.67309700e-02, 4.98795340e-01, 1.93406046e+12, 7.82157806e-01, -1.59310290e-01, 5.93635084e-01] 
    rf112 = experFromBroadMCMC(emceeparams[:-1], 'rf112')

    emceeparams = [1.21990575e-01, 2.25750440e+00, 1.42283492e+00, 2.38779672e+00, -2.20443849e+00, 1.07448541e+00, 2.26876611e+00, -1.11338069e+00, 1.91939912e+00, 4.52858032e-01, 1.84182587e+00, 2.26660250e+00, 7.71741216e-02, 1.21665083e-02, 4.95477220e-01, 2.57736306e-01, 1.06866306e+00, 5.03555469e-01, 8.98255341e-03, 3.51823670e-01, 6.57947163e+11, 9.73425083e-01, -1.69906882e-01, 3.10019810e-01]
    rf113fid = experFromBroadMCMC(emceeparams[:-1], 'rf113fid')

    #### a few runners-up
    posteriors = np.array([[  1.41770654e-01,   2.45050659e+00,   2.61690983e+00,   2.63513509e+00,   3.22385410e-01,   5.25370163e-01,   4.11019928e+00,  -5.56706799e-01,   1.62770773e+00,   4.38315726e-01,   2.43862201e+00,   2.64597948e+00,   5.00168386e-02,   8.37982476e-03,   4.57828445e-01,   2.16816496e-01,   1.24032620e+00,   3.66206876e-01,   1.16197763e-02,   5.13078077e-01,   2.45445719e+12,   1.46320093e+00,  -1.88561103e-02,   3.74693962e-01],
    [  1.43471049e-01,   2.11586724e+00,   2.85565807e+00,   1.83463928e+00,   4.97074915e-02,   1.20947662e+00,   2.96755583e+00,  -7.51240372e-01,   2.73899696e+00,   6.10208444e-01,   2.38562845e+00,   2.03582376e+00,   6.21513309e-02,   4.34744165e-03,   5.12119376e-01,   1.04256577e-01,   2.12898835e+00,   4.94798946e-01,   1.02598907e-02,   3.47843175e-01,   1.36955173e+12,   1.18497000e+00,  -1.67926958e-01,   4.96547952e-01],
    [  2.04486864e-01,   2.88120002e+00,   3.25719889e+00,   2.66263057e+00,   2.27151192e-01,   5.25564583e-01,   3.42627948e+00,  -1.03353919e+00,   2.00688887e+00,   6.06262384e-01,   2.37107780e+00,   2.22078909e+00,   6.92269496e-02,   1.32278564e-02,   6.33401611e-01,   3.32810752e-01,   1.58332202e+00,   2.94782593e-01,   1.12429678e-02,   2.47279896e-01,   2.29634718e+12,   1.51504655e+00,  -5.87451991e-02,   5.61659119e-01],
    [  1.75968697e-01,   2.63077357e+00,   2.71140824e+00,   1.98690602e+00,   3.02698953e-01,   7.64297819e-01,   6.24096647e+00,  -1.15052330e+00,   2.38752909e+00,   6.95205531e-01,   2.13169580e+00,   2.27084757e+00,   7.66656260e-02,   9.82512104e-03,   6.55021191e-01,   2.21648159e-01,   1.68354039e+00,   3.57178264e-01,   8.93852873e-03,   3.99091464e-01,   1.98464589e+12,   1.45645035e+00,  -8.54418687e-02,   5.85790120e-01],
    [  1.50001597e-01,   6.63368287e-01,   3.46505862e+00,   5.29186501e-01,  -1.02397187e-01,  -1.33669354e-01,   6.30395899e+01,  -1.52932101e+00,   1.06459709e+00,   7.95051593e-01,   3.78107677e+00,   2.54264572e+00,   3.39551038e-02,   1.18020216e-03,   8.32316414e-01,   2.55190390e-01,   2.30751383e+00,   1.91278415e-01,   2.68669899e-02,   4.71418276e-01,   2.28803783e+11,   5.72407369e-01,  -1.32584911e-01,   8.54109282e-01],
    [  1.45906622e-01,   1.75985998e+00,   2.42484834e+00,   2.18460823e+00,   1.71358687e-01,  -1.26060221e+00,   3.30462760e+00,  -9.17273308e-010,   1.27074217e+00,   5.94169090e-01,   2.43907682e+00,   1.59752000e+00,   4.92771728e-02,   1.36675462e-02,   4.83738660e-01,   8.73159481e-02,   1.38621386e+00,   3.28886393e-01,   1.21186695e-02,   3.55451628e-01,   1.29547055e+12,   1.21522829e+00,  -8.24133283e-02,   4.62554955e-01],
     [  1.60878849e-01,   2.62023173e+00,   2.37961236e+00,   1.90923724e+00,  -2.17309742e+00,  -2.21250594e-01,   1.55357515e+00,  -1.26347273e+00,   2.47687330e+00,   4.64731828e-01,   1.59314023e+00,   2.39710092e+00,   7.55143918e-02,   1.38945365e-02,   5.36957565e-01,   3.50458248e-01,   1.41354094e+00,   3.66901507e-01,   8.88629028e-03,   1.66394318e-01,   1.16081408e+12,   1.04401821e+00,  -2.28896855e-01,   5.86472929e-01],
     [  1.02767464e-01,   2.82837515e+00,   2.39027386e+00,   2.28921240e+00,  -9.66654109e-01,  -2.51765156e+00,   1.78508338e+00,  -1.10373036e+00,   1.26654765e+00,   7.95578969e-01,   1.95478174e+00,   2.63760284e+00,   5.25470711e-02,   2.29941424e-03,   3.80650455e-01,   2.82853531e-01,   9.08476705e-01,   4.28674852e-01,   8.97324258e-03,   8.24456568e-01,   6.90571984e+11,   8.86126290e-01,  -1.07351512e-01,   8.39403757e-01],
     [  1.60220601e-01,   2.81426435e+00,   1.78223572e+00,   1.95563642e+00,  -5.48371939e-01,  -2.61916907e-02,   4.00486058e+00,  -1.07005557e+00,   1.57033180e+00,   4.69179408e-01,   2.26715714e+00,   2.50807400e+00,   6.75841381e-02,   6.02409794e-03,   4.79563831e-01,   3.22839595e-01,   2.12140409e+00,   3.97247225e-01,   1.01925116e-02,   5.68737281e-01,   9.74726404e+11,   1.50490111e+00,  -5.43194737e-02,   3.71735915e-01]])
    rf113s=[]
    for k in range(9):
        rf113s.append( experFromBroadMCMC( posteriors[k,:-1], 'rf113'+letter(k,caps=True) ) )

    # estimate of the maximum posterior.
    emceeparams = [0.147451569889, 2.52941811659, 2.59034734186, 2.41120695741, -0.124283831858, -0.0523679435879, 9.35680382698, -0.974822093888, 1.89905286619, 0.511551421578, 2.0337488747, 2.02929369251, 0.0642244458824, 0.00988965146683, 0.509787819545, 0.279394476293, 1.74417214913, 0.342311450585, 0.0107366934282, 0.414472066814, 1.50430105103e+12, 1.21653967757, -0.028389697679, 0.497607252288]
    rf114 = experFromBroadMCMC( emceeparams[:-1], 'rf114')

    rf115 = experFromBroadMCMC( emceeparams[:-1], 'rf115', ngal=300) # width=0.1

    rf116 = experFromBroadMCMC( emceeparams[:-1], 'rf116', ngal=300) # width=0.001
    emceeparams = [0.149354276683, 2.29662827501, 2.79461671253, 1.97030789668, -0.124779535863, -0.0488095925623, 9.71985730149, -0.994430586699, 1.64437693632, 0.521861050335, 2.25575165221, 2.36521228877, 0.0601717224014, 0.00894463492218, 0.450958746716, 0.223457898757, 1.29673596724, 0.359099545607, 0.0114868234909, 0.364120399959, 1.34581599878e+12, 1.14437611734, -0.0312772437184, 0.454205538279]

    rf117 = experFromBroadMCMC( emceeparams[:-1], 'rf117', ngal=30)

    ### Fix the accretion histories of all three experiments to allow apples-to-apples comparison
    accHistories= list(np.random.random(40))

    emceeparams = [0.12955226356, 2.47373940813, 2.45479617854, 1.46323139728, -0.114507760639, -0.0419071281768, 8.99557830256, -0.899780053776, 1.59620080732, 0.610633513105, 2.58555895865, 2.69249662202, 0.0766829856229, 0.00732827711296, 0.354912135951, 0.06588656943, 0.590831834975, 0.386774120664, 0.0121818106422, 0.360005554607, 1.06333400606e+12, 1.30297939675, -0.0481094079431, 0.426468518444] # Kmeans 0
    rf118 = experFromBroadMCMC( emceeparams[:-1], 'rf118', ngal=40, accHistories=accHistories) # width=0.001

    emceeparams = [0.155779370657, 3.70192939049, 2.3629243098, 1.15023842296, -0.124671403875, -0.0373178013245, 11.5634324148, -0.842827324362, 1.90546918808, 0.456758964804, 2.24636720205, 3.46337887487, 0.0527242301223, 0.00834119522375, 0.421595165404, 0.0588460822552, 1.74955679152, 0.342803545981, 0.0204463371468, 0.19660364412, 1.4775553159e+12, 0.51641100428, -0.0481071097317, 0.458174209253]
    rf119 = experFromBroadMCMC( emceeparams[:-1], 'rf119', ngal=40, accHistories=accHistories) # width=0.001

    emceeparams = [0.162500882765, 3.59747256894, 2.35890853613, 1.29374687757, -0.103928997055, -0.0447959320133, 13.2897283764, -1.14236258863, 1.68882319248, 0.355225019885, 3.09085746781, 3.7273269975, 0.0569144720645, 0.0095654880823, 0.552984634226, 0.0816554804364, 0.467859289986, 0.334822554197, 0.0188438745643, 0.169488299946, 1.37840935586e+12, 1.05381473757, -0.0428919442171, 0.318971861461]
    rf120 = experFromBroadMCMC( emceeparams[:-1], 'rf120', ngal=40, accHistories=accHistories) # width=0.001


    ### SAME as rf118, but more galaxies, and a realistic scatter in alphaR!
    emceeparams = [0.12955226356, 2.47373940813, 2.45479617854, 1.46323139728, -0.114507760639, -0.0419071281768, 8.99557830256, -0.899780053776, 1.59620080732, 0.610633513105, 2.58555895865, 2.69249662202, 0.0766829856229, 0.00732827711296, 0.354912135951, 0.06588656943, 0.590831834975, 0.386774120664, 0.0121818106422, 0.360005554607, 1.06333400606e+12, 1.30297939675, -0.0481094079431, 0.426468518444] # Kmeans 0
    rf121 = experFromBroadMCMC( emceeparams[:-1], 'rf121', ngal=400 ) # width=0.1
    

    emceeparams = [0.102390462957, 2.07863393044, 2.20082341292, 2.29723610003, 0.0, 0.0, 0.104519630718, -0.622466992607, 7.25004582806, 0.503081010769, 1.37816041394, 2.34207773986, 0.0573170771292, 0.0135990238461, 0.540110872095, 0.159253193033, 1.35187143844, 0.318788163305, 0.26577663261, 0.480641566772, 1.64193072254e+12, 1.38002174315, 0.29647549094]
    rf122 = experFromBroadMCMC( emceeparams, 'rf122', ngal=40)

    ### This is taking the favorite result of the previous mcmc, and plugging it into this parameterization as a sanity check.
    emceeparams = [0.12955226356, 2.47373940813, 2.45479617854, 1.46323139728, -0.114507760639, -0.0419071281768, .0899557830256, -0.899780053776, 1.59620080732, 0.610633513105, 2.58555895865, 2.69249662202, 0.0766829856229, 0.00732827711296, 0.354912135951, 0.06588656943, 0.590831834975, 0.386774120664, 0.0121818106422, 0.360005554607, 1.06333400606e+12, 1.30297939675, 0.3] 
    rf124 = experFromBroadMCMC( emceeparams, 'rf124', ngal=40) # 124 is 123 with 100x lower mu0
    rf125 = experFromBroadMCMC( emceeparams, 'rf125', ngal=400) # 124 is 123 with 100x lower mu0

    # result of fakemcmc24 - and co amalgamation
    emceeparams = [0.0443059862284, 0.806495237058, 1.4087606963, 0.869527693096, 0.327075377559, -0.308939479358, 0.0234912805083, -1.12089580649, 33.1828005128, 0.407917555468, 3.02608263739, 3.49498785593, 0.0907902716067, 4.63872357149e-05, 0.464102097423, 0.280240720027, 3.36677341647, 0.187561143417, 0.0218102260209, -0.0156521057259, 2.40360675676e+12, 3.62893109323, 0.195727400353]
    rf126 = experFromBroadMCMC( emceeparams, 'rf126', ngal=40)

    # same as 126, except reduce chi_ESN to 1
    emceeparams = [0.0443059862284, 0.806495237058, 1.4087606963, 0.869527693096, 0.327075377559, -0.308939479358, 0.0234912805083, -1.12089580649, 33.1828005128, 0.407917555468, 3.02608263739, 3.49498785593, 0.0907902716067, 4.63872357149e-05, 0.464102097423, 0.280240720027, 3.36677341647, 0.187561143417, 0.0218102260209, -0.0156521057259, 2.40360675676e+12, 1.0, 0.195727400353]
    rf127 = experFromBroadMCMC( emceeparams, 'rf127', ngal=40)

    # result of fakemcmc24 - and co2 amalgamation
    emceeparams = [0.0907149271263, 0.761600454933, 2.20442557257, 0.426192077362, 0.155223968728, -0.100294656199, 0.0303891177429, -1.4123812033, 4.87364935138, 0.513140027012, 3.63601310775, 4.58975160056, 0.0841687629951, 6.49402673113e-05, 0.375868764738, -0.0826015820612, 2.14390072752, 0.233497821684, 0.0167987278298, -0.0134286210391, 2.29158889284e+12, 2.81011052587, 0.272326583338]
    rf128 = experFromBroadMCMC( emceeparams, 'rf128', ngal=40)

    # 30 steps into fakemcmc24co2aftersplit
    emceeparams = [0.114785922343, 0.656817173378, 2.66103429214, 0.436075435026, 0.112192431035, -0.129416709889, 0.0358907871528, -1.28978511023, 4.18110531509, 0.494182821752, 3.70658492364, 4.94680017104, 0.0801370653293, 6.31417046843e-05, 0.394211795435, -0.165214045377, 3.22479494404, 0.176906243046, 0.0221127418329, -0.0104729675354, 3.13453091307e+12, 2.99361371481, 0.233608662191]
    rf129 = experFromBroadMCMC( emceeparams, 'rf129', ngal=40)

    # 50 steps into fakemcmc25, plus an artificial reduction from ~ -1.0 to -0.7 in alphaMh.
    emceeparams = [0.112916589104, 0.63842335415, 2.50984526904, 0.448082316632, 0.104301163171, -0.131856822965, 0.0360716052922, -0.7, 4.29142270588, 0.511168005255, 3.64258405032, 4.73219935654, 0.0799694888646, 6.65087204525e-05, 0.408508757039, -0.161872545785, 3.25442635693, 0.183656180092, 0.0200517721637, -0.0105144001646, 3.20856474724e+12, 3.09020027961, 0.236742085025]
    rf130 = experFromBroadMCMC( emceeparams, 'rf130', ngal=40)

    ## ~60 steps into fakemcmc25
    emceeparams = [0.113894786374, 0.671606201397, 2.50724549634, 0.546062003219, 0.094368156197, -0.112848097766, 0.0345714839787, -0.426176771365, 4.94145658032, 0.538678882129, 3.98454628212, 5.15197965132, 0.08133192535, 6.2784924053e-05, 0.400288619119, -0.150067876526, 2.77079137969, 0.209569425732, 0.0218331618273, -0.0116329761749, 3.51463541754e+12, 2.54465296635, 0.258963202267]
    rf131 = experFromBroadMCMC( emceeparams,  'rf131', ngal=40)

    ### same as 131, with an artificial reduction to 0 of the log offset SN injection energy
    emceeparams = [0.113894786374, 0.671606201397, 2.50724549634, 0.546062003219, 0.094368156197, -0.112848097766, 0.0345714839787, -0.426176771365, 4.94145658032, 0.538678882129, 3.98454628212, 5.15197965132, 0.08133192535, 6.2784924053e-05, 0.400288619119, -0.150067876526, 2.77079137969, 0.209569425732, 0.0218331618273, -0.0116329761749, 3.51463541754e+12, 1.0, 0.258963202267]
    rf132 = experFromBroadMCMC( emceeparams, 'rf132', ngal=40)

    ### same as 132, with an artificial reduction to 2.5 of the critical Q
    emceeparams = [0.113894786374, 0.671606201397, 2.50724549634, 0.546062003219, 0.094368156197, -0.112848097766, 0.0345714839787, -0.426176771365, 4.94145658032, 0.538678882129, 3.98454628212, 2.5, 0.08133192535, 6.2784924053e-05, 0.400288619119, -0.150067876526, 2.77079137969, 0.209569425732, 0.0218331618273, -0.0116329761749, 3.51463541754e+12, 1.0, 0.258963202267]
    rf133 = experFromBroadMCMC( emceeparams, 'rf133', ngal=40)

    ### same as 132, with an artificial reduction to 1.0 of the critical Q
    emceeparams = [0.113894786374, 0.671606201397, 2.50724549634, 0.546062003219, 0.094368156197, -0.112848097766, 0.0345714839787, -0.426176771365, 4.94145658032, 0.538678882129, 3.98454628212, 1.0, 0.08133192535, 6.2784924053e-05, 0.400288619119, -0.150067876526, 2.77079137969, 0.209569425732, 0.0218331618273, -0.0116329761749, 3.51463541754e+12, 1.0, 0.258963202267]
    rf134 = experFromBroadMCMC( emceeparams, 'rf134', ngal=40)

    onesigma = np.array([ 0.0639699634194, 0.175669345104, 0.194144965124, 0.196740693287, 0.0268951157936, 0.0452487795685, 0.180169700187, 0.208756138113, 0.296881946691, 0.171557030848, 0.157054980687, 0.214853033434, 0.24444032497, 0.196063180653, 0.0976129590677, 0.0745452119358, 0.196819984819, 0.0750604819935, 0.256380811552, 0.00417220030494, 0.238687094513, 0.248586810662, 0.0994240961595])
    dx = np.zeros(len(onesigma))
    dx[0] = onesigma[0] # only adjust the first parameter

    accHistories= list(np.random.random(10))
    emceeparams =  np.array([0.100375945617, 0.613138619039, 3.3021402233, 0.516231938506, 0.0441220425549, -0.128196711652, 0.028206808373, -0.438686312836, 3.38315173023, 0.497178218909, 2.52416835555, 5.45837198968, 0.0702394232504, 5.9214182623e-05, 0.451573935518, -0.154542539198, 3.49195314288, 0.182006429909, 0.0227990477544, -0.00892169395585, 3.64007286294e+12, 0.996089787935, 0.255067003247] ) #, 1.19966654417] 
    rf136 = []
    for k in range(9):
        rf136.append(  experFromBroadMCMC( emceeparams*np.power(10.0,(-4.0+k)*dx/4.0), 'rf136'+str(k), ngal=10, accHistories=accHistories) )

    # take a look at what happens if we reduce radial mixing of metals
    emceeparams[-7] = 0.001
    rf137 = experFromBroadMCMC( emceeparams, 'rf137', accHistories=accHistories, ngal=10)

    # Return to our original value of kappa_Z, but this time the cpp code has been modified to prevent diffusion faster than \sigma*H
    emceeparams[-7] = 3.49195314288
    rf138 = experFromBroadMCMC( emceeparams, 'rf138', accHistories=accHistories, ngal=10)

    # mode of new mcmc with lower kappa_Z prior
    emceeparams = [0.111024857427, 0.651471090758, 3.60369988073, 1.32410848876, 0.00462162773379, -0.155722717901, 0.031880475053, -0.654077470322, 2.37229453732, 0.441016987977, 2.39816792077, 7.49401210998, 0.124550671584, 6.80468433312e-05, 0.599283305526, -0.136486524703, 0.145855283753, 0.172199330299, 0.0298417733283, -0.0164741738978, 2.68739637394e+12, 0.976891038462, 0.453901301973]
    rf139 = experFromBroadMCMC( emceeparams, 'rf139', accHistories=accHistories, ngal=10)

    # mode of new mcmc with narrower prior than emulator training set + joint random forest.
    emceeparams = [0.111745803862, 0.818929938542, 2.92780328018, 0.689587010711, 0.0759295601488, -0.120461318724, 0.0373432928034, -0.447286494649, 4.07357838129, 0.438033563556, 3.05791992511, 4.65041927578, 0.0667650233566, 7.01564802143e-05, 0.629283785624, -0.127203487947, 0.153112902804, 0.21538734542, 0.0207646517441, -0.00861003837926, 2.58750951275e+12, 0.456186615647, 0.257580989521]
    rf140 = experFromBroadMCMC( emceeparams, 'rf140', ngal=20)

    emceeparams = [0.112880634252, 0.850512948862, 2.94324103318, 0.726404182119, 0.0765400107456, -0.113405865243, 0.0379355384555, -0.445309091863, 3.98749021939, 0.429406535455, 2.90270296704, 4.50395986877, 0.0657333353017, 7.19362415873e-05, 0.648057158224, -0.121730154033, 0.154392627919, 0.219206161863, 0.0195372597215, -0.00806271599118, 2.43079764943e+12, 0.444498655945, 0.260298512737] 

    # the emcee run that produced this 'most likely' posterior as an intermediate result was NOT including low-mass halos :-/ RIP
    emceeparams = [0.0745144532323, 0.858069954263, 5.87230260006, 1.96353721838, 0.107385556409, 0.0221126800279, 0.0273660570926, 0.563533677496, 8.51523653643, 0.388320023513, 3.1423891774, 5.85848733881, 0.102879385215, 8.36754857925e-05, 0.612561051121, -0.101195537545, 0.13438834465, 0.180837918126, 0.0163591503975, -0.0139227815788, 3.00305723759e+12, 1.08131222464, 0.368861767907]
    rf141 = experFromBroadMCMC(emceeparams, 'rf141', ngal=20)

    # fakemcmc33 - including lower masses in the likelihood
    emceeparams = [0.0615434193287, 1.0188697904, 2.71537731422, 2.8650882819, 0.126784188369, 0.0185776666524, 0.0224351900625, 0.506267601629, 4.91488161105, 0.431751909881, 3.47660964674, 5.20346226824, 0.0597290394181, 7.90700983682e-05, 0.651026074296, -0.0744182306864, 0.123672492022, 0.259861700898, 0.0114748421283, -0.0143883263752, 2.57979242747e+12, 0.969561683518, 0.404615667626] #, 1.12238263527]
    rf142 = experFromBroadMCMC(emceeparams, 'rf142', ngal=20)

    # fakemcmc32 - don't include the lower masses.
    emceeparams = [0.0911888958652, 1.04655690451, 4.38325072714, 3.2518319456, 0.134721601083, 0.0253339527922, 0.0195856004897, 0.69093945893, 7.42660694634, 0.339106596995, 2.80373921479, 5.26695689595, 0.0622408843234, 8.92190488573e-05, 0.75398793696, -0.101800552071, 0.101885838734, 0.183527349299, 0.00998409814552, -0.0229489863927, 1.76964592889e+12, 1.09092880211, 0.371839664948] #, 1.08803217226]
    rf143 = experFromBroadMCMC(emceeparams, 'rf143', ngal=20)

    # keepin it 1600 - this is fakemcmc34 after ~1600 iterations.
    emceeparams = [0.0696202889818, 2.36010095611, 1.19592519448, 3.80922040118, -0.331287157289, 0.16162232186, 0.0632291452063, 0.112694021741, 3.45596589733, 0.487314812337, 2.29321794439, 2.90572826728, 0.0759838285036, 0.00216076266301, 0.445410559116, 0.213309060707, 0.221933216054, 0.370702662448, 0.00848192935542, -0.10315237063, 2.33494750629e+12, 0.602354295423, 0.304498038927] #, 1.17790054244]
    rf144 = experFromBroadMCMC(emceeparams, 'rf144', ngal=20)

    # for comparison to rf144. This is from iteration ~400, of the same run, i.e. before the big jump.
    emceeparams = [0.0645463323585, 1.24490023205, 1.37016152977, 3.37739992627, -0.333972689602, 0.135411790336, 0.045241077512, -0.101705141014, 1.42370069748, 0.224273418275, 2.01794607053, 2.3362673358, 0.0506343529443, 0.00113506777348, 0.437137064909, 0.158533010722, 0.100937381681, 0.292608054786, 0.0102875271548, -0.00833082266041, 1.05349338052e+12, 0.564760738996, 0.315726762435] #, 1.461132142]
    rf145 = experFromBroadMCMC(emceeparams, 'rf145', ngal=20)

    emceeparams = [0.0956469497757, 1.99285788932, 1.78714981237, 3.85725072693, -0.692176903981, 0.229933457174, 0.496815342413, 0.161039798449, 6.26550400742, 0.524210070726, 1.99388037894, 2.93784500968, 0.0496425558527, 0.00106066317858, 0.680680809064, 0.204087529469, 0.132989260954, 0.388495832368, 0.0101878682016, -0.287335836629, 1.39055446444e+12, 0.785719406143, 0.278149845856] #, 1.16169054047]
    rf146 = experFromBroadMCMC(emceeparams, 'rf146', ngal=20)

    # Just fit to the low masses! But uh, still run iwht the high masses, just to see what happens
    emceeparams = [0.20377959675, 2.87483502867, 2.05176159435, 3.88073551669, -0.785769160474, 0.112272977122, 0.248641010924, -0.0347512596024, 2.20285162759, 0.256418374472, 0.836093042324, 1.13426050696, 0.0965334012358, 0.00189971250816, 0.0119955233538, 0.264882780791, 0.177874824271, 0.54469845242, 0.0107986304816, -0.297241409544, 1.57753338029e+12, 0.761841258858, 0.208645157021]#, 1.23650169849]
    rf147 = experFromBroadMCMC(emceeparams, 'rf147', ngal=20)

    # fakemcmc38 - only low masses, expand prior range to allow model flexibility to not crazily miss SMHM dramatically
    emceeparams = [0.515999947529, 2.1513451284, 3.37498168545, 2.75513209655, -1.1887348189, 0.199053703065, 0.114806918599, -0.341514394344, 1.46255785778, 0.260182805024, 2.5870352537, 1.69162963992, 0.0553965699285, 0.00226329083285, 0.455971884528, 0.440146053141, 0.127098283096, 0.450881309485, 0.016617152179, 0.00839484065324, 2.07362390011e+12, 0.585585599938, 0.189414491515] #, 1.03161566146]
    rf148 = experFromBroadMCMC(emceeparams, 'rf148', ngal=20)
    # 148 went from 8.5 to 13 in logMh0 - this is a bit unfair since the fit was only done from 9 to 11. 149 uses that range to see if the fits look as awful.
    rf149 = experFromBroadMCMC(emceeparams, 'rf149', ngal=20)

    import pickle
    def fairPosteriorSample(bn, pikfilename, nsamp, ngal, mass):
        #accHistories= list(np.random.random(10))
        accHistories = None
        arr = pickle.load(open(pikfilename,'r'))
        exps = []
        # if we've been given a list o f masses, assume we want a different random sample at each mass.
        if hasattr(mass,'__len__'):
            assert len(mass)==nsamp
            masses = mass
        else:
            masses = np.ones(nsamp)*mass
        for i in range(nsamp):
            j = int(np.random.uniform()*np.shape(arr)[0]) # pick a random integer!
            emceeparams = arr[j,:-1]
            exps.append( experFromBroadMCMC(emceeparams, bn+'_'+str(i).zfill(2), ngal=ngal, accHistories=accHistories, mass=masses[i]) )
        return exps


    def systematicPosteriorSample(bn, pikfilename, nsamp, ngal, mass, startSampling=0):
        #accHistories= list(np.random.random(10))
        accHistories = None
        arr = pickle.load(open(pikfilename,'r'))
        exps = []
        # if we've been given a list o f masses, assume we want a different random sample at each mass.
        if hasattr(mass,'__len__'):
            assert len(mass)==nsamp
            masses = mass
        else:
            masses = np.ones(nsamp)*mass
        for i in range(nsamp):
            #j = int(np.random.uniform()*np.shape(arr)[0]) # pick a random integer!
            j = i + startSampling
            emceeparams = arr[j,:-1]
            exps.append( experFromBroadMCMC(emceeparams, bn+'_'+str(i).zfill(2), ngal=ngal, accHistories=accHistories, mass=masses[i]) )
        return exps


    masterparams = np.zeros((160, 23))
    mhs = np.power(10, np.linspace(9.5, 13.15, 160))
    masterparams[:,0] = np.power(10, np.linspace( -0.45, -0.9, 160))
    masterparams[:,1] = [10.0**0.3]*160
    masterparams[:,2] = [10.0**0.3]*160
    masterparams[:,3] = np.power(10, np.linspace( 0.5, -0.1, 160))
    masterparams[:,4] = [0.1]*160
    masterparams[:,5] = [0.5]*160
    masterparams[:,6] = np.power(10, np.linspace( -.25, -1, 160))
    masterparams[:,7] = np.power(10, np.linspace(-1.67,0, 160))
    masterparams[:,8] = np.power(10, np.linspace( 0.5, -2, 160))
    masterparams[:,9] = np.linspace(0.1, 0.4, 160)
    masterparams[:,10] = np.power(10, np.linspace( 0.5, -.1, 160))
    masterparams[:,11] = [3.2]*160
    masterparams[:,12] = [10**-1.6]*160
    masterparams[:,13] = np.power(10, np.linspace(-3,-1.5,160))
    masterparams[:,14] = np.linspace(0.8, 0.4, 160)
    masterparams[:,15] = np.linspace(0, -.2, 160)
    masterparams[:,16] = np.power(10, np.linspace(-1.8, -.5, 160))
    masterparams[:,17] = [0.4]*160
    masterparams[:,18] = [0.02]*160
    masterparams[:,19] = np.linspace(-0.2, -0.4, 160)
    masterparams[:,20] = np.power(10, np.linspace(12,12.7,160))
    masterparams[:,21] = np.power(10, np.linspace(-0.8, -0.4, 160))
    masterparams[:,22] = np.linspace(0.25, 0, 160)
    rf264 = []
    for i in range(160):
        rf264.append( experFromBroadMCMC(masterparams[i,:], 'rf264_'+str(i).zfill(2), ngal=1, accHistories=None, mass=np.log10(mhs[i])) )



    masterparams = np.zeros((160, 23))
    mhs = np.power(10, np.linspace(9.5, 13.15, 160))
    masterparams[:,0] = [0.1]*160 
    masterparams[:,1] = [10.0**0.5]*160
    masterparams[:,2] = [10.0**0.5]*160
    masterparams[:,3] = np.power(10, np.linspace( 0.3, 0.1, 160))
    masterparams[:,4] = [-0.2]*160
    masterparams[:,5] = [0.4]*160
    masterparams[:,6] = np.power(10, np.linspace( -.25, -1, 160))
    masterparams[:,7] = np.power(10, np.linspace(-0.75,0, 160))
    masterparams[:,8] = np.power(10, np.linspace( -0.5, 0, 160))
    masterparams[:,9] = np.linspace(0.5, 1.0, 160)
    masterparams[:,10] = np.power(10, np.linspace( -0.1, -.1, 160))
    masterparams[:,11] = np.power(10, np.linspace(-0.2, 0.3, 160))
    masterparams[:,12] = [10**-1.6]*160
    masterparams[:,13] = np.power(10, np.linspace(-3,-1.5,160))
    masterparams[:,14] = np.linspace(0.9, 0.9, 160)
    masterparams[:,15] = np.linspace(0, -.2, 160)
    masterparams[:,16] = np.power(10, np.linspace(-1.2, -1.2, 160))
    masterparams[:,17] = [0.5]*160
    masterparams[:,18] = [10**-2]*160
    masterparams[:,19] = np.linspace(0.1, -0.6, 160)
    masterparams[:,20] = np.power(10, np.linspace(11.2,12.7,160))
    masterparams[:,21] = np.power(10, np.linspace(-0.8, -0.4, 160))
    masterparams[:,22] = np.linspace(0.6, 0.6, 160)
    rf285 = []
    for i in range(160):
        rf285.append( experFromBroadMCMC(masterparams[i,:], 'rf285_'+str(i).zfill(2), ngal=1, accHistories=None, mass=np.log10(mhs[i])) )



####def experFromBroadMCMC(emceeparams, name=None, ngal=30, accHistories=None, mass=12.0):
####    raccRvir, rstarRed, rgasRed, fg0mult, muColScaling, muFgScaling, muNorm, muMhScaling, ZIGMfac, zmix, eta, Qf, alphaMRI, epsquench, accCeiling, conRF, kZ, xiREC, epsff, initialSlope, mquench, enInjFac, chiZslope = emceeparams

    # some models set up to be similar-ish to Hopkins+ 2010-era isolated galaxies. For reference I've copied the call signature from experFromBroadMCMC above ^
    #MAP = [ 10.0**-0.75, 10.0**0.3, 10.0**0.55, 10.0**0.32, 0.2, 0.1, 10.0**-2.25, -1.45, 10.0**-0.2, 0.58, 10.0**0.5, 10**0.6, 10.0**-1.83, 10.0**-2.05, .99, 0.24, 10.0**-1.7, 0.8, 10.0**-1.65, -0.3, 10.0**11.75,  10.0**-0.5, 0.4] # read off from fig. 1 of Forbes+ 2019 - 01-03
    #MAP = [ 10.0**-1.25, 10.0**0.3, 10.0**0.55, 10.0**0.32, 0.2, 0.1, 10.0**-2.25, -1.45, 10.0**-0.2, 0.58, 10.0**0.5, 1.0, 10.0**-1.83, 10.0**-2.05, .99, 0.24, 10.0**-1.7, 0.8, 10.0**-1.65, -0.3, 10.0**11.75,  10.0**-0.5, 0.4] # modify Q & scalelength of accretion -04-06
    #MAP = [ 10.0**-1.75, 10.0**0.3, 10.0**0.55, 10.0**0.32, 0.2, 0.1, 10.0**-2.25, -1.45, 10.0**-0.2, 0.58, 10.0**0.5, 1.0, 10.0**-1.83, 10.0**-2.05, .99, 0.24, 10.0**-1.7, 0.8, 10.0**-1.65, -0.3, 10.0**11.75,  10.0**-0.5, 0.4] # further reduce scale length. Let's see if we can overshoot  -07-09
    #MAP = [ 10.0**-1.25, 10.0**0.3, 10.0**0.55, 10.0**0.32, 0.2, 0.1, 10.0**-2.25, -1.45, 10.0**-0.2, 0.58, 10.0**0.5, 1.0, 10.0**-1.83, 10.0**-2.05, .99, 0.24, 10.0**-1.7, 0.8, 10.0**-1.65, -0.3, 10.0**11.75,  10.0**-0.5, 0.4] # revert changes to accretion scalelength, try removing accretion heating (in experFromBroadMCMC)
    #MAP = [ 10.0**-1.5, 10.0**0.3, 10.0**0.55, 10.0**0.32, 0.2, 0.1, 10.0**-2.25, -1.45, 10.0**-0.2, 0.58, 1.0, 1.0, 10.0**-1.83, 10.0**-2.05, .99, 0.24, 10.0**-1.7, 0.8, 10.0**-1.65, -0.3, 10.0**11.75,  10.0**-0.5, 0.4] # decrease eta, and compactify a little more -- 13-15
    MAP = [ 10.0**-1.2, 10.0**0.3, 10.0**0.55, 10.0**0.52, 0.2, 0.1, 10.0**-2.25, -1.45, 10.0**-0.5, 0.58, 1.0, 1.0, 10.0**-1.83, 10.0**-2.05, .99, 0.24, 10.0**-1.7, 0.8, 10.0**-2.00, 0.0, 10.0**11.75,  0.1, 0.4] # increase initial gas fraction, decrease initial metallicity, decrease SN strength, decrease epsff, decrease muMhSlope -- used in 18-23. Also we're now just going to adjust zstart and zrelax to their ~actual times to make this whole thing a bit easier
    MAPreducedGI = [ 10.0**-0.75, 10.0**0.3, 10.0**0.55, 10.0**0.32, 0.2, 0.1, 10.0**-2.25, -1.45, 10.0**-0.2, 0.58, 1.5, 2.0, 10.0**-1.83, 10.0**-2.05, .99, 0.24, 10.0**-1.7, 0.8, 10.0**-1.65, -0.3, 10.0**11.75,  10.0**-0.5, 0.4] # read off from fig. 1 of Forbes+ 2019 - 01-03
    hkm16 = experFromBroadMCMC( MAP, name='hkm16', ngal=5, mass=10.4)
    hkm16.irregularVary('zstart', 0.48)
    hkm16.irregularVary('zrelax', 0.5)

    hkm17 = experFromBroadMCMC( MAP, name='hkm17', ngal=5, mass=10.25) # further adjustment
    hkm17.irregularVary('zstart', 0.05)
    hkm17.irregularVary('zrelax', 0.07)

    hkm14 = experFromBroadMCMC( MAP, name='hkm14', ngal=5, mass=12.0)
    hkm15 = experFromBroadMCMC( MAP, name='hkm15', ngal=5, mass=13.0)


    hkm18 = experFromBroadMCMC( MAP, name='hkm18', ngal=5, mass=10.25)
    hkm18.irregularVary('zstart', 0.08)
    hkm18.irregularVary('zrelax', 0.1)

    hkm22 = experFromBroadMCMC( MAP, name='hkm22', ngal=2, mass=12.0)
    hkm22.irregularVary('zstart', 0.08)
    hkm22.irregularVary('zrelax', 0.1)
    hkm23 = experFromBroadMCMC( MAP, name='hkm23', ngal=2, mass=13.0)
    hkm23.irregularVary('zstart', 2.05)
    hkm23.irregularVary('zrelax', 2.07)

    hkm21 = experFromBroadMCMC( MAP, name='hkm21', ngal=2, mass=10.25)
    hkm21.irregularVary('zstart', 0.08)
    hkm21.irregularVary('zrelax', 0.1)
    hkm21.irregularVary('fg0mult', 8.0 ) 
    hkm21.irregularVary('accScaleLength', 10.0**-1.0  )
    hkm21.irregularVary('kappaMetals', 1.0e-8 ) 
    hkm21.irregularVary('stScaleReduction', 0.5)
    hkm21.irregularVary('gaScaleReduction', 0.5)
    hkm21.irregularVary('ZIGMfac', .003)
    hkm21.irregularVary('muNorm', .008)
    hkm21.irregularVary('xiREC', .9) 
    hkm21.irregularVary('ZMix', 0.05) 

    fe20 = experFromBroadMCMC( MAPreducedGI, name='fe20', ngal=20, mass=np.logspace(10,13,20))
    fe21 = experFromBroadMCMC( MAPreducedGI, name='fe21', ngal=20, mass=np.logspace(10,13,20))
    fe21.irregularVary('AccretionHeatingRate', 1.0)


    fe22=NewSetOfExperiments( hkm21, 'fe22')[0] # turn on AccretionHeating
    fe22.irregularVary('AccretionHeatingRate', 1.0)
    fe23=NewSetOfExperiments( hkm22, 'fe23')[0] # turn on AccretionHeating
    fe23.irregularVary('AccretionHeatingRate', 1.0)
    fe24=NewSetOfExperiments( hkm23, 'fe24')[0] # turn on AccretionHeating
    fe24.irregularVary('AccretionHeatingRate', 1.0)

    # so right now we have a 2x2 of [Hopkins, MAP] x [Heating, no Heating]
    # We could also try to come up with a particular situation besides MAP where we expect acc. heating might have some effect.
    # Another possibility is to turn off GI
    # Probably there are also other possibilities!

    ####### IT'S PROBABLY A BAD IDEA TO MODIFY ANYTHING BELOW THIS LINE!!!
    for inputString in modelList: # aModelName will therefore be a string, obtained from the command-line args


        # Get a list of all defined models (allModels.keys())
        # for each such key (aModel) check whether this inputString is contained in its name
        matches = [aModel for aModel in sorted(allModels.keys()) if inputString in aModel]
        if(len(matches) != 0): 
            for model in matches: #if(model in allModels): 
                print ("dbg0",inputString,matches)
                if(not args.xgrid): #local run
                    allModels[model].localRun(args.nproc,args.start)
                else: # write a file to run on the xgrid
                    allModels[model].write('runExperiment_'+model+'.txt')
        else:
            print ("You asked me to run ",inputString," but did not define it in the script.")


    # now all of our processes have been sent off
    nPrev = 0
    while True:
        nStillRunning=HowManyStillRunning(allProcs)
        # has anything changed since the last time we checked?
        if(nStillRunning == nPrev and nStillRunning != 0):
            # do nothing except wait a little bit
            time.sleep(2)
        else:
            nPrev=nStillRunning
            if(nPrev == 0):
                break # we're done!
            print ("Still waiting for ",nPrev, " processes to finish; I'll check every few seconds for changes.")
    print ("All local runs complete!")


    print ("Time elapsed (seconds): ", time.time()-t0)
