;; We'd like to produce some postage stamps.
;; Use the results of variability3, and stitch together
;; N x M set of plots at a particular time.
;; I think this will just involve constructing the 
;; appropriate matrix to send to simpleMovie

FUNCTION GetStampData,fiducialName,comparisonName,whichVariables,whichRedshifts,offsetVars,comparisonNumbers
    expNames = [fiducialName, comparisonName+'a', comparisonName+'b']

    ;; ntime x nx x nvar x nModels
    nModelsMax = 100
    theData = dblarr(n_elements(whichRedshifts),200,n_elements(whichVariables),nModelsMax)
    comparisonNumbers=intarr(n_elements(expNames))

    FOR i=0, n_elements(expNames)-1 DO BEGIN
        nameList = ListValidModels(expNames[i],nModelsMax)
        comparisonNumbers[i] = n_elements(nameList)
        FOR j=0, n_elements(nameList)-1 DO BEGIN
            modelPtr = ReadModels([nameList[j]])
            model = (*(modelPtr[0]))
            offsetModel = 0
            IF(i NE 0) THEN offsetModel = TOTAL(comparisonNumbers[0:i-1])
            theData[*,*,*,j+offsetModel] = model.dataCube[whichRedshifts,*,whichVariables+offsetVars*model.ncolstep-1]
            ptr_free,modelPtr[0]
        ENDFOR

    ENDFOR


    theData = theData[*,*,*,0:TOTAL(comparisonNumbers)-1]

    RETURN, theData

END



PRO postagestamps

    compile_opt idl2
    set_plot,'x'
    device,decomposed=0
    device,retain=2

    columns = 6
    rows = 4
    setct,1,0,0
    fid = 'rw01'
    th=2.0
    chth=1
    cs=.3
    svSinglePlot=2
    whichRedshifts=[201]
    zs=['0']
    ; Radius, Col, Sig, Z, sfrPerAccr, ageAtz0, equilibrium, colPerCrit, BB4, Q
    dummy = GetLabels(keys=[0,1,2,6,23,12,47,49,27,8], names=names, labels=labels, tex=texLabels, base=vars, log=logs, offset=offsets,ranges=ranges)

    stampLabels=[ $
        'racc','kz','kzh','QGI','rIC', $
        'QGIt','mri','mu','eta','rb', $
        'fg0','vcir','epf','zet','Qlim', $
        'fR','fRt','nRC','fcl','bet0', $
        'eff','efft','phi0','fH2m','Tgas', $
        'tSC','ZIGM','Mh0','Mh0+','racct']
    texStampLabels=[ $
        '$r_{acc}$','$\kappa_Z$','$\kappa_Z(H)$','$Q_{GI}$','$r_{IC}$', $
        '$Q_{GI}(\tau)$','$\alpha_{MRI}$','$\mu$','$\eta$','$r_b$',$ 
        '$f_{g,0}$','$v_{circ}$','$\epsilon_\mathrm{ff}$','$\zeta$', '$Q_{lim}$', $
        '$f_R$','$f_R(t)$','$n$','$f_{cool}$','$\beta_0$',$
        '$\epsilon_{in}$','$\epsilon_{in}(t)$','$\phi_0$','$f_{H_2,min}$','$T_{gas}$', $
        '$t_{SC}$','$Z_{IGM}$','$M_{h,0}$','$M_{h,0}(\gamma)$','$r_{acc}(t)$']
    comparisonExperiments= $
        ['rw02','rw03','rw04','rw05','rw34', $
         'rw06','rw07','rw08','rw09','rw10', $
         'rw11','rw12','rw14','rw15','rw16', $
         'rw18','rw19','rw24','rw25','rw26', $
         'rw27','rw28','rw29','rw30','rw31', $
         'rw33','rw38','rw39','rw40','rw53']
     lowRange= $
         ['1-6.6 kpc', '1e-4 : 1e-3', '1e-4 : 1e-3', '1.3-1.9', '1.0-3.2', $
          '1.3-1.9','0-.009','0.1-0.4','0.5-1.5','0-2.5', $
          '0.1-0.45','160-215','.0031-.0095','0.3-0.9','1.8-2.4', $
          '.22-.45','.22-.45','1.0-1.9','.20-.55','-0.5 : .45', $
          '.003-.2','.003-.2','.5-.95','.003-.029','100-6900', $
          '1-1.9', '1/100 - 1/10', '1e10-1e12','1e10-1e12','1-6.6 kpc' $
          ]
     hiRange= $
         ['9.9-20.8 kpc', '1e-3 : 3e-3', '1e-3 : 3e-3', '2.1-3.0', '3.8-20.8', $
          '2.1-3.0','.011-0.1','0.6-2.0','1.5-4.5','3.5-10', $
          '.55-.95','225-250','.0105-.031','1.1-3','2.6-3.0', $
          '.47-.7','.22-.45','2.1-3.0','.65-1.0','.55-.95', $
          '.31-.46','.31-.46','1.05-2','.031-.3','7100-30000', $
          '2.1-4', '1/10-1','1e12-1e13','1e12-1e13','9.9-20.8 kpc' $
          ]
;    keys= [ $
;        0,1,3,4,6,7, $
;        8,9,10,11,12,13, $
;        14,15,17,18,19,20, $
;        22,23,24,26,27,28 $
;        ]
    keys = [ $
         4, 19, 12, 26,  3, 20, $
        10, 17, 23, 13,  6, 27, $
        18,  9, 25,  1,  8, 29, $
        22, 11,  7, 15, 24,  0  $
        ]
    stampLabels = stampLabels[keys]
    texStampLabels=texStampLabels[keys]
    comparisonExperiments=comparisonExperiments[keys]
    lowRange=lowRange[keys]
    hiRange=hiRange[keys]

    ;; collect data from the disk.
    stampList = ptrarr(n_elements(stampLabels), /allocate_heap)
    FOR k=0, n_elements(stampLabels)-1 DO BEGIN
        theData = GetStampData(fid,comparisonExperiments[k],vars,whichRedshifts,offsets,numberOfModels)
    	stamp = {fid:fid, comp:comparisonExperiments[k], $
                 theData:theData,numberOfModels:numberOfModels}
        *(stampList[k]) = stamp
     ENDFOR

    FOR a=0, 100 DO BEGIN

	     makeThePostageStampPlots, stampList, whichRedshifts,vars,zs,th, $
             labels,stampLabels,texLabels,texStampLabels, $
             lowRange, hiRange, $
             names,columns,rows,svSinglePlot,cs,chth,logs,ranges
         stop
    ENDFOR

END

