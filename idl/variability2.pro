;; Given a 4-d array of the form discussed in the procedures below,
;; generate a 2-d array of the form [[min,max], [min,max], ...] for each variable
;; where min and max should encompass the entire data range (for all times and models)
FUNCTION simpleranges,data,wrtxlog
  ranges=dblarr(2,n_elements(data[0,0,*,0]))
  FOR k=0,n_elements(data[0,0,*,0])-1 DO BEGIN ;;; loop over variables
    ;; do the simplest thing: look at the min and the max in the data.
    ranges[*,k] = [MIN(data[*,*,k,*]),MAX(data[*,*,k,*])]

    ;; If the variable is supposed to be plotted logarithmically but the data 
    ;; isn't plottable that way (i.e. <=0 in some places), only plot the valid data.
    IF(ranges[0,k] LE 0.0 AND wrtXlog[k] EQ 1) THEN BEGIN
      flat = data[*,*,k,*]
      ind = WHERE(flat GT 0.0, ct)
      IF(ct NE 0) THEN ranges[0,k] = MIN(flat[ind])
      IF(ranges[1,k] / ranges[0,k] GT 1.0e11) THEN ranges[0,k] = ranges[1,k]*1.0e-11
    ENDIF
    
    ;; Give us a little breathing room: add 10% in each direction for each axis.
    IF(wrtXlog[k] EQ 1) THEN BEGIN
      dexRange = alog10(ranges[1,k]/ranges[0,k])
      ranges[1,k] = ranges[1,k]*(10.0 ^ (dexRange/10.0))
      ranges[0,k] = ranges[0,k]/(10.0 ^ (dexRange/10.0))
    ENDIF
    IF(wrtXlog[k] EQ 0) THEN BEGIN
      linRange = ranges[1,k]-ranges[0,k]
      ranges[1,k] = ranges[1,k] + linRange/10.0
      ranges[0,k] = ranges[0,k] - linRange/10.0
    ENDIF

 
  ENDFOR
  return,ranges
END

;; given an array whose first column indexes time, second column indexes position,
;; fourth column indexes models, and a vector of time labels, and axis labels
;; make one or a few movies! The third column indexes which variable we're plotting.
PRO simpleMovie,data,time,labels,colors,styles,ranges,wrtXlog,name,sv,strt,prev=prev,psym=psym
  lth=1
  chth=1
  IF(sv EQ 3 || sv EQ 4) THEN cg=1 ELSE cg=0
  IF(sv EQ 1) THEN cs=1 ELSE cs=2.8
  IF(sv EQ 4) THEN BEGIN 
    cs=2.5
    chth=2
    lth=5
  ENDIF

  ranges= simpleranges(data,wrtxlog)
;  ranges[*,0] = [MIN(data[*,*,0,*]),MAX(data[*,*,0,*])]
;  IF(ranges[0,0] LE 0.0 AND wrtXlog[0] EQ 1) THEN ranges[0,0] = 1d-8 * ranges[1,0]


  FOR k=1,n_elements(labels)-1 DO BEGIN ;; loop over y-axis variables to be plotted (except the first one, which is just radius!)
    fn=name+"_"+labels[k]
    dn="movie_"+name+"_"+labels[k]
    set_plot,'x'
    IF(sv EQ 3 || sv EQ 4) THEN set_plot,'z'
    IF(cg NE 1) THEN WINDOW,1,XSIZE=1024,YSIZE=1024,RETAIN=2
    IF(sv EQ 3 || sv EQ 4) THEN cgDisplay,1024,1024
    IF(sv EQ 1) THEN mpeg_id=MPEG_OPEN([1024,1024],FILENAME=(fn+".mpg"))
    IF(sv EQ 2 || sv EQ 3 || sv EQ 4) THEN BEGIN
      FILE_MKDIR,dn
    ENDIF
		
;    ranges[*,k] = [MIN(data[*,*,k,*]),MAX(data[*,*,k,*])]
;    IF(ranges[0,k] LE 0.0 AND wrtXlog[k] EQ 1) THEN ranges[0,k] = 1d-8 * ranges[1,k]

    count=0
    tailLength = fix(3.0/(float(n_elements(styles))/928.0)^(.25)) ; length of a tail to put on each point which represents a galaxy when prev=1
    FOR ti=0,n_elements(time)-1 DO BEGIN  ;; loop over time
      count=count+1
      SETCT,1,n_elements(styles),2
      IF(strt[k] EQ 0) THEN $
        PLOT,[0],[0],COLOR=0,BACKGROUND=255,XSTYLE=1,YSTYLE=1,XTITLE=labels[0],YTITLE=labels[k], $ 
	XRANGE=ranges[*,0],YRANGE=ranges[*,k],ylog=wrtXlog[k],xlog=wrtXlog[0],CHARTHICK=chth,CHARSIZE=cs,THICK=lth,XTHICK=lth,YTHICK=lth ELSE $
        PLOT,findgen(1001)*(ranges[1,0]-ranges[0,0])/1000 + ranges[0,0], $
	  findgen(1001)*(ranges[1,0]-ranges[0,0])/1000 + ranges[0,0], $
          COLOR=0,BACKGROUND=255,XSTYLE=1,YSTYLE=1,XTITLE=labels[0],YTITLE=labels[k],XRANGE=ranges[*,0], $
          YRANGE=ranges[*,k],ylog=wrtXlog[k],xlog=wrtXlog[0],linestyle=2,CHARSIZE=cs,CHARTHICK=chth,THICK=lth,XTHICK=lth,YTHICK=lth
      XYOUTS,.2,.9,string(time[ti]),/NORMAL,COLOR=0,CHARSIZE=cs,CHARTHICK=chth
      FOR j=0,n_elements(data[0,0,0,*])-1 DO BEGIN ;; loop over models (4th column of data)	
        IF(n_elements(styles) GT 80) THEN IF(sv NE 3 AND sv NE 4) THEN setct,5,n_elements(styles),j ELSE setct,3,n_elements(styles),0
        
;        IF(n_elements(styles) GT 10) THEN setct,3,n_elements(styles),0	
        OPLOT, data[ti,*,0,j], data[ti,*,k,j], COLOR=colors[j],linestyle=styles[j],PSYM=psym,SYMSIZE=cs,THICK=lth
        IF(n_elements(prev) NE 0) THEN BEGIN
;          FOR ti2=MAX([0,ti-tailLength]),ti DO BEGIN ;; loop over previous time steps
;            OPLOT, data[ti2,*,0,j],data[ti2,*,k,j], COLOR=colors[j],PSYM=3,symsize=2
;          ENDFOR
          OPLOT,data[MAX([0,ti-tailLength]):ti,0,0,j],data[MAX([0,ti-tailLength]):ti,0,k,j], COLOR=colors[j],linestyle=0,THICK=1
        ENDIF
      ENDFOR


      IF(sv EQ 1) THEN MPEG_PUT,mpeg_id,WINDOW=1,FRAME=count,/ORDER
      IF(sv EQ 2) THEN WRITE_PNG, dn+'/frame_'+string(count,FORMAT="(I4.4)") + '.png',TVRD(TRUE=1)
      IF(sv EQ 3 || sv EQ 4) THEN dummy=cgSnapshot(filename=(dn+'/frame_'+STRING(count,FORMAT="(I4.4)")),/png,/true,/nodialog)
      IF(sv EQ 0) THEN wait,.05
    ENDFOR
    IF(sv EQ 1) THEN MPEG_SAVE,mpeg_id
    IF(sv EQ 1) THEN MPEG_CLOSE,mpeg_id
    IF(sv EQ 2 || sv EQ 3 || sv EQ 4) THEN spawn,("rm " + fn+".mpg") 
    IF(sv EQ 2 || sv EQ 3 || sv EQ 4) THEN spawn,("ffmpeg -f image2 -qscale 4 -i "+dn+"/frame_%04d.png " + fn + ".mpg")
    IF(sv EQ 2 || sv EQ 3 || sv EQ 4) THEN spawn,("rm -rf "+dn)
    set_plot,'x'
  ENDFOR
END

;; given an array whose first column indexes time, second column indexes different data sets
;;  third column indexes models, plus corresponding time
;; axis labels, colors, and styles, make a series of simple plots
PRO simplePlot,data,time,labels,colors,styles,name,sv
  FOR k=0,n_elements(labels)-1 DO BEGIN;; loop over y-axis variables to be plotted against time
    set_plot,'x'
    figureInit,name+"_"+labels[k],1,1

    FOR j=0,n_elements(data[0,0,*])-1 DO BEGIN
      IF(j EQ 0) THEN PLOT,time,data[*,k,j],COLOR=colors[j],BACKGROUND=255,linestyle=styles[j],XTITLE="time",YTITLE=labels[k],XSTYLE=1,YSTYLE=1
      IF(j NE 0) THEN OPLOT,time,data[*,k,j],COLOR=colors[j],linestyle=styles[j]
    ENDFOR

    figureClean,name+"_"+labels[k]
  ENDFOR
END

FUNCTION getElements,nvardim,i
  telements=(unpack(i,nVarDim))
  srtd=nVarDim[reverse(sort(nvardim))]
  elements=telements[reverse(sort(nvardim))]
  IF(n_elements(elements) LT 3) THEN BEGIN
    qelements=intarr(3)
    qelements[0:n_elements(elements)-1]=elements[0:n_elements(elements)-1]
    elements=qelements
  ENDIF

  RETURN,elements
END






;;; Meant to do an analysis of many runs at once, particularly when those correspond to different accr. histories
;;; expName is an experiment name, like one would specify in exper.py. This code assumes that you are 
;;;     1) in the gidget/analysis directory, and 2) you have a bunch of runs in a folder with names of the form
;;;      expName/expName<identifiers>_<filenames>, where identifiers can be anything as long as it is unique to each run
;;;      and <filenames> encompasses all the files output by the code, e.g. evolution.dat, radial.dat, etc.
;;; keys is an array which lets you specify which variable to plot from the list in wrtXyt. This is useful
;;;    for very large experiments, where even storing the modest-size arrays here which take a limited amount of
;;;    data for each run can become cumbersome. If you input an empty array, by default the code will analyze
;;;    all the variables
;;; N controls how many runs in the experiment to analyze. For large number runs, sometimes it's useful to just look
;;;    at a few runs. If N is larger than the number of runs in the experiment, all the runs are analyzed.
;;; sv- behaves like other instances of sv; 0 to just show the plots on the screen, 2 to save them as png's and 
;;;    subsequently movies. 4 saves movies in a format conducive to showing on a low-resolution projector.
PRO variability2,expName,keys,N,sv
  compile_opt idl2
  set_plot,'x'
  DEVICE,DECOMPOSED=0
  DEVICE,RETAIN=2

  proftimes=dblarr(5)
  proftimes[0]=systime(1)

  nameList2 = ListValidModels(expName,N)
  ctr=0

  ;; variables to plot- title, column index, log plot, name, y-range
  wrtXyt=['R','Col','Sig','Col_*','Sig_*','fg','Z','ColSFR','Q','Qg','Qst','fH2','ageAtz0','age','tdep','tvisc','tdepOverTvisc']
  wrtXyy=[9,10,11,12,13,17,22,14,12,24,23,48,31,32,35,36,37] ;; index
  wrtXyp=[1, 1, 1, 1, 1, 0, 0, 1, 0, 0, 0, 0, 1, 1, 1, 1, 1] ;; offset?
  wrtXyn=['r', 'col','sig','colst','sigst','fg','Z','colsfr','Q','Qg','Qst','fH2','ageAtz0','age','tdep','tvisc','tdepOverTvisc']
  wrtXyr=[[0,20],[.1,1000],[5,300],[.1,1000],[5,300],[0,1],[-1,1.0],$
    [1d-6,10],[1.5,5.0],[.5,50],[.5,50],[0,1],[1d9,14d9],[1d5,14d9],[1.0e8,1.0e10],[1.0e8,1.0e10],[.01,100]]
  wrtXyl=[0,1,1,1,1,0,0,1,0,1,1,0,0,0,1,1,1]

  IF(n_elements(keys) EQ 0) THEN keys=indgen(n_elements(wrtXyt)-1)+1

  dummy = where( keys EQ 17, n1)
  IF(n1 EQ 2) THEN n1=1

  ;; only plot the variables present in 'keys'	
  tk = [[0],keys]
  wrtXyt=wrtXyt[tk]
  wrtXyy=wrtXyy[tk]
  wrtXyp=wrtXyp[tk]
  wrtXyn=wrtXyn[tk]
  wrtXyr=wrtXyr[*,tk]
  wrtXyl=wrtXyl[tk]  

  ;; now loop over every model in the list - 
  ;; all we're doing here is reading in each model then freeing 
  ;; the associated memory
  ;; so that we can iterate over a very large number. For each model, 
  ;; record the data specified in the arrays above (e.g. yy)
  modelPtr=ReadModels([nameList2[0]])
  model = (*(modelPtr[0]))

  time = model.evArray[1,*]  ;; z is 

  ;; (# timesteps) x (nx) x (# of columns) x (# models)
  theData= dblarr(n_elements(model.dataCube[*,0,0]),n_elements(model.dataCube[0,*,0]),n_elements(wrtXyy),n_elements(nameList2))


  NVS = 21
  ;; (# timesteps) x (# pts/model frame = 1) x (one thing vs another = 20) x (# models)
  vsMdot = dblarr(n_elements(model.dataCube[*,0,0]),1,NVS,n_elements(nameList2))

;  theTData = dblarr(n_elements(model.dataCube[*,0,0]), n_elements(wrtTyy), n_elements(nameList2))

  proftimes[1]=systime(1)


  FOR i=0,n_elements(nameList2)-1 DO BEGIN ;; loop over every valid model
    IF(i MOD 50 EQ 0) THEN PRINT,"Processing model #",i," of ",n_elements(nameList2)


    ;; the number of colors necessary is srtd[0], 
    ;; which color set to use is elements[2]
    IF(i NE 0) THEN modelPtr=ReadModels([nameList2[i]])
    IF(i NE 0) THEN model = (*(modelPtr[0]))
    zi=nearest("redshift",1,model,0.0)
    offsets=[0,model.ncolstep,model.ncolstep+model.npostprocess]

    x = model.dataCube[0,*,0]

    ;; if this model has the appropriate number of time steps..
    ;;PRINT,"Number of time steps",n_elements(model.dataCube[*,0,0]),n_elements(theData[*,0,0,0])
    IF(n_elements(model.dataCube[*,0,0]) EQ n_elements(theData[*,0,0,0])) THEN BEGIN
      FOR k=0,n_elements(wrtXyy)-1 DO BEGIN	
        theData[*,*,k,i] = model.dataCube[*,*,wrtXyy[k]+offsets[wrtXyp[k]]-1]
      ENDFOR

      vsMdot[*,0,0,i] =  model.dataCube[*,model.nx-1,39-1]  ;; external accretion rate
      
;      FOR theT=0, n_elements(model.dataCube[*,0,0])-1 DO $
;        vsMdot[theT,0,1,i] = TOTAL(2*!pi*x[*]*x[*]*model.dlnx*model.dataCube[theT,*,model.ncolstep+14-1]*model.Radius*model.Radius)

      vsMdot[*,0,1,i] = model.evArray[10,*] ;; SFR [in the disk!]
;      vsMdot[*,0,2,i] = model.evArray[5,*]/model.evArray[6,*] * (1.0 - model.evArray[6,*]) ;; stellar mass

      FOR zi=0, n_elements(model.evArray[9,*])-1 DO BEGIN ; loop over redshift
        modelInfo = diskStats(model,z=model.evArray[9,zi])
        vsMdot[zi,0,3,i] = modelInfo[1] ;; peak radius of column density (kpc)
        vsMdot[zi,0,4,i] = modelInfo[2] ;; edge of SF region (kpc)
        vsMdot[zi,0,5,i] = modelInfo[3] ;; col @ r=8kpc (solar masses/pc^2)
        vsMdot[zi,0,6,i] = modelInfo[7] ;; sSFR (yr^-1)
        vsMdot[zi,0,7,i] = modelInfo[8] ;; gas mass in bulge (MSol)
        vsMdot[zi,0,8,i] = modelInfo[9] ;; stellar mass in bulge
        vsMdot[zi,0,9,i] = modelInfo[10] ;; total f_H2
        vsMdot[zi,0,10,i] = modelInfo[11] ;; mdot bulge gas
        vsMdot[zi,0,11,i] = modelInfo[12] ;; mdot bulge stars
        vsMdot[zi,0,2,i] = modelInfo[19] ;; stellar mass in disk + bulge
        vsMdot[zi,0,12,i] = modelInfo[8]/modelInfo[19] ;; B:T
        vsMdot[zi,0,13,i] = modelInfo[18] ;; SFR + mdotbulgeGas
        vsMdot[zi,0,14,i] = modelInfo[17] ;; efficiency
        vsMdot[zi,0,15,i] = alog10(modelInfo[16]) ;; metallicity
        vsMdot[zi,0,16,i] = modelInfo[5] ;; fG in SF region.
        vsMdot[zi,0,17,i] = (modelInfo[18] - modelInfo[11])/(modelInfo[18]+1.0d-10) ;; fraction of SF in the bulge
        vsMdot[zi,0,18,i] = modelInfo[20] ;; fgL
	vsMdot[zi,0,19,i] = alog10(modelInfo[21]) ;; ZL
	vsMdot[zi,0,20,i] = modelInfo[15] ;; fg
      ENDFOR

;      FOR kk=0,n_elements(wrtTyind)-1 DO BEGIN
;        theTData[*,kk,i] =;; model.evArray[wrtTyind[kk],*]
;      ENDFOR
      ctr = ctr+1
    ENDIF


;      PlotVsXInd,model,zi,model.ncolstep+9,yind[k]+offsets[yp[k]],OP(i),0,COLOR=elements[0],LINESTYLE=(elements[1]+fix(elements[1] GE 1)),THICK=1,XTITLE="r [kpc]",YTITLE=ytitle[k],YRANGE=yr[*,k],YSTYLE=1,XSTYLE=1


    IF(i EQ 0) THEN print,model.name,diskStats(model)
    ptr_free,modelPtr[0]
  ENDFOR

  proftimes[2]=systime(1)

  theData = (temporary(theData))[*,*,*,0:ctr-1]
;  theTData = temporary(theTData)[*,*,0:ctr-1]


  ;; having accumulated theData, let's do some analysis!
  sortdData = theData * 0.0
  sortdData[*,*,0,*] = theData[*,*,0,*] ;; don't sort radii..
  sortdVsMdot = vsMdot*0.0
  FOR j=0,n_elements(theData[*,0,0,0])-1 DO BEGIN ;; loop over time
    FOR k=1,n_elements(wrtXyy)-1 DO BEGIN ;; loop over variables
      FOR xx=0,n_elements(theData[0,*,0,0])-1 DO BEGIN ;; loop over x-coord
        sortdData[j,xx,k,*] = theData[j,xx,k,sort(theData[j,xx,k,*])]
      ENDFOR

    ENDFOR
    st = sort(vsMdot[0,0,0,*])
    FOR k2=0,n_elements(vsMdot[0,0,*,0])-1 DO BEGIN	;; loop over variables
      sortdVsMdot[j,0,k2,*] = vsMdot[j,0,k2,st]
    ENDFOR
  ENDFOR

  proftimes[3]=systime(1)

  intervals = dblarr(n_elements(theData[*,0,0,0]),  n_elements(theData[0,*,0,0]), n_elements(theData[0,0,*,0]), 5)
  intervals[*,*,*, 0]=sortdData[*,*,*, fix(.025*ctr)]
  intervals[*,*,*, 1]=sortdData[*,*,*, fix(.16*ctr)]
  intervals[*,*,*, 2]=sortdData[*,*,*, fix(.5*ctr)]
  intervals[*,*,*, 3]=sortdData[*,*,*, fix(.84*ctr)]
  intervals[*,*,*, 4]=sortdData[*,*,*, fix(.975*ctr)]

  expName2 = expName+'_'+strcompress(string(MIN([n_elements(nameList2),N])),/remove) ;; e.g. rk5_113


  IF(n_elements(nameList2) GT 50) THEN BEGIN
      setct,1,0,0
      simpleMovie,intervals,time,wrtXyn,[2,1,0,1,2],[2,2,0,2,2],wrtXyr,wrtXyl,expName2+"_intervals",sv,intarr(n_elements(wrtXyl))
  ENDIF


  IF(n_elements(nameList2) GT 104 AND sv NE 4) THEN BEGIN
    setct,3,n_elements(sortdData[0,0,0,*]),0
    simpleMovie,sortdData,time,wrtXyn,indgen(n_elements(sortdData[0,0,0,*])),intarr(n_elements(sortdData[0,0,0,*])),wrtXyr,wrtXyl,expName2+"_sorted",sv,intarr(n_elements(wrtXyl))
  ENDIF

  setct,3,n_elements(theData[0,0,0,*]),0
  IF(n_elements(nameList2) LT 105) THEN BEGIN 	
    simpleMovie,theData,time,wrtXyn,indgen(n_elements(theData[0,0,0,*])),intarr(n_elements(theData[0,0,0,*])),wrtXyr,wrtXyl,expName2+"_unsorted",sv,intarr(n_elements(wrtXyl))
  ENDIF
	

  setct,3,n_elements(vsMdot[0,0,0,*]),0
  IF(n1 EQ 1) THEN BEGIN
    simpleMovie, sortdVsMdot,time,['mdot','DiskSFR','Mst','rPeak','rHI','colsol','sSFR','BulgeGasMass','BulgeStMass','fH2','mdotBulgeGas','mdotBulgeStars',"BT","SFRplusMdot_b_gas","efficiency","Z","f_gInSF","DiskToTotalSF","fgL","ZL","fg"],$
      indgen(n_elements(vsMdot[0,0,0,*])), $
      intarr(n_elements(vsMdot[0,0,0,*])), $
      [[.03,500],[.3,60],[3d9,3d10],[0.2,20],[.2,22],[6,100],[3d-11,3d-8],[1d7,3d11],[-0.1,1.1],[-0.1,1.1],[1d-7,1d2],[1d-3,1d2],[0,1],[.3,100],[0,1],[-1,.5],[0,1],[0,1],[0,1],[-1,.5],[0,1]], $
      [1,1,0,1,0,1,1,0,0,0,1,1,0,1,0,0,0,0,0,0,1],expName2+"_vsmdot",sv,[1,1,0,0,0,0,0,0,0,0,1,1,0,1,0,0,0,0,0,0,0],PSYM=1,prev=1
  ENDIF

  ;; average mdot over a number of time steps nt
  nt = 40
  setct,3,n_elements(vsMdot[0,0,0,*]),0
  avgdVsMdot = sortdVsMdot[*,*,*,*]

  FOR ti=0,n_elements(time)-1 DO BEGIN
    FOR mm=0,n_elements(vsMdot[0,0,0,*])-1 DO BEGIN
      avgdVsMdot[ti,0,0,mm] = TOTAL(sortdVsMdot[MAX([0,ti-nt]):ti,0,0,mm]) / (ti - MAX([0,ti-nt]) + 1)
    ENDFOR
  ENDFOR
  IF(n1 EQ 1) THEN BEGIN
    simpleMovie, avgdVsMdot,time,['avgMdot','DiskSFR','Mst','rPeak','rHI','colsol','sSFR','BulgeGasMass','BulgeStMass','fH2','mdotBulgeGas','mdotBulgeStars',"BT","SFRplusMdot_b_gas","efficiency","Z","f_gInSF","DiskToTotalSF","fgL","ZL","fg"],$
      indgen(n_elements(vsMdot[0,0,0,*])), $
      intarr(n_elements(vsMdot[0,0,0,*])), $
      [[.03,500],[.3,60],[3d9,3d10],[0.2,20],[.2,22],[6,100],[3d-11,1d-8],[1d7,3d11],[-0.1,1.1],[-0.1,1.1],[1d-7,1d2],[1d-3,1d2],[0,1],[.3,100],[0,1],[-1,.5],[0,1],[0,1],[0,1],[-1,.5],[0,1]], $
      [1,1,0,1,0,1,1,0,0,0,1,1,0,1,0,0,0,0,0,0,1],expName2+"_vsavgmdot",sv,[1,1,0,0,0,0,0,0,0,0,1,1,0,1,0,0,0,0,0,0,0],PSYM=1,prev=1
  ENDIF


  ;; Plot these quantities vs. the star formation rate.
  setct,3,n_elements(vsMdot[0,0,0,*]),0
  vsSFR = sortdVsMdot[*,*,1:n_elements(sortdVsMdot[0,0,*,0])-1,*] ;; cut out the mdot slice of the array
  IF(n1 EQ 1) THEN BEGIN 
    simpleMovie, vsSFR, time, ['DiskSFR','Mst','rPeak','rHI','colsol','sSFR','BulgeGasMass','BulgeStMass','fH2','mdotBulgeGas','mdotBulgeStars',"BT","SFRplusMdot_b_gas","efficiency","Z","f_gInSF","DiskToTotalSF","fgL","ZL","fg"], $
      indgen(n_elements(vsMdot[0,0,0,*])), $
      intarr(n_elements(vsMdot[0,0,0,*])), $
      [[.3,60],[3d9,3d10],[0.2,20],[.2,22],[6,100],[3d-11,1d-8],[1d7,3d11],[-0.1,1.1],[-0.1,1.1],[1d-7,1d2],[1d-3,1d2],[0,1],[.3,100],[0,1],[-1,.5],[0,1],[0,1],[0,1],[0,1],[0,1]], $
      [1,0,1,0,1,1,0,0,0,1,1,0,1,0,0,0,0,0,0,1],expName2+"_vsSFR",sv,[1,0,0,0,0,0,0,0,0,1,1,0,1,0,0,0,0,0,0,0],PSYM=1,prev=1
  ENDIF


  ;; Now do a series of plots vs. M*
  vsMstar = sortdVsMdot[*,*,*,*]
  vsMstar[*,*,0,*] = vsMstar[*,*,2,*]
  vsMstar[*,*,2:19,*] =vsMstar[*,*,3:20,*]
  vsMstar=vsMstar[*,*,0:19,*]
  setct,3,n_elements(vsMstar[0,0,0,*]),0
  IF(n1 EQ 1) THEN BEGIN
    simpleMovie, vsMstar, time, ["Mst","DiskSFR","rPeak","rHI",'colsol','sSFR','BulgeGasMass','BulgeStMass','fH2','mdotBulgeGas','mdotBulgeStars',"BT","SFRplusMdot_b_gas","efficiency","Z","f_gInSF","DiskToTotalSF","fgL","ZL","fg"], $
      indgen(n_elements(vsMstar[0,0,0,*])), $
      intarr(n_elements(vsMstar[0,0,0,*])), $
      [[3d9,3d10],[.3,60],[0.2,20],[.2,22],[6,100],[3d-11,1d-8],[1d7,3d11],[-0.1,1.1],[-0.1,1.1],[1d-7,1d2],[1d-3,1d2],[0,1],[.3,100],[0,1],[-1,.5],[0,1],[0,1],[0,1],[0,1],[0,1]], $
      [1,1,1,0,1,1,0,0,0,1,1,0,1,0,0,0,0,0,0,1],expName2+"_vsMstar",sv,[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],PSYM=1,prev=1
  ENDIF

  STOP


  Mh = vsMdot[*,0,2,*]/(.18*vsMdot[*,0,14,*])
  zn = n_elements(Mh[*,0,0,0])
	
  ;; Plot the accretion rates.
  SETCT,3,n_elements(vsMdot[0,0,0,*]),0
  FIGUREInit,(expName2+'_accRates'),1,3,3
  yr=[MIN(sortdVsMdot[zn-1,0,0,*])*.5,MAX(sortdVsMdot[0,0,0,*])*2];[.01,1000];[MIN(sortdVsMdot[*,0,0,*]),MAX(sortdVsmdot[*,0,0,*])]
  Plot,time,sortdVsMdot[*,0,0,0],COLOR=0,BACKGROUND=255,YRANGE=yr,YLOG=1,XSTYLE=1,XTITLE="Time",YTITLE="Accretion Rate",CHARSIZE=3,THICK=4,CHARTHICK=2
  FOR m=1,n_elements(sortdVsMdot[0,0,0,*])-1 DO BEGIN
    setct,5,n_elements(sortdVsMdot[0,0,0,*]),m
    OPLOT,time,sortdVsMdot[*,0,0,m],COLOR=m,THICK=4
	
  ENDFOR
  FIGURECLEAN,(expName2+'_accRates'),1



  ;; Plot the halo mass
  SETCT,3,n_elements(vsMdot[0,0,0,*]),0
  FIGUREInit,(expName2+'_Mh'),1,3,3
  Plot,time,Mh[*,0,0,0],COLOR=0,BACKGROUND=255,YRANGE=[Min(Mh[zn-1,0,0,*])*.1,Max(Mh[zn-1,0,0,*])*2],YLOG=1,XSTYLE=1,XTITLE="Time",YTITLE="Halo Mass",CHARSIZE=3,THICK=4,CHARTHICK=2
  FOR m=1,n_elements(sortdVsMdot[0,0,0,*])-1 DO BEGIN
    setct,5,n_elements(sortdVsMdot[0,0,0,*]),m
    OPLOT,time,Mh[*,0,0,m],COLOR=m,THICK=4
	
  ENDFOR
  FIGURECLEAN,(expName2+'_Mh'),1



  FIGUREInit,(expName2+'_z0AccRates'),1,1,1
  cgHistoplot, alog10(sortdVsMdot[n_elements(sortdVsMdot[*,0,0,0])-1,0,0,*]), BinSize=.1
  FIGURECLEAN,(expName2+'_z0AccRates'),1
	
  proftimes[4]=systime(1)

  PRINT,proftimes[1]-proftimes[0]," seconds to check model validities and initialize"
  PRINT,proftimes[2]-proftimes[1]," seconds to read in data"
  PRINT,proftimes[3]-proftimes[2]," seconds to sort the data"
  PRINT,proftimes[4]-proftimes[3]," seconds to generate movies"

  STOP

END
